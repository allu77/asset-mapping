# Pipeline Architecture

## S3 Prefix Layout

```
pdf/                  ← STOXX source PDF (365-day lifecycle)
  stoxx600_raw_<date>.pdf
xls/                  ← iShares XLS/XLSX files (365-day lifecycle)
  msci_emerging_markets_raw_<date>.xls
  msci_europe_small_cap_value_weighted_raw_<date>.xlsx
  msci_usa_small_cap_value_weighted_raw_<date>.xlsx
  msci_world_ex_us_raw_<date>.xlsx
raw-csv/              ← normalised CSVs ready for processing (365-day lifecycle)
  <index_id>_raw_<date>.csv
processed-csv/        ← final output, canonical schema (365-day lifecycle)
  <index_id>_holdings_<date>.csv
```

## Lambda Chain

Every step is SQS-mediated. Each queue has a DLQ (14-day retention, max 3 receives) and a CloudWatch alarm that fires an SNS email when ≥1 message lands in the DLQ.

```
EventBridge (monthly, 28th 06:00 UTC) — one rule per index_id
  → DownloaderQueue (SQS)
  → Downloader Lambda    payload: {"index_id": "<id>"}
  → S3 put (pdf/, xls/, or raw-csv/)

S3 notification on pdf/* and xls/*
  → ParserQueue (SQS)
  → Parser Lambda        XLS/PDF → raw-csv/<index_id>_raw_<date>.csv

S3 notification on raw-csv/*
  → ProcessorQueue (SQS)
  → Processor Lambda     raw-csv → processed-csv/<index_id>_holdings_<date>.csv

S3 notification on processed-csv/*
  → UploaderQueue (SQS, batch_size=1, max_concurrency=2)
  → Uploader Lambda      → Google Sheets tab named <index_id> (SSM credentials)
                           (at most 2 concurrent uploads; each index writes its own tab)
```

**Redriving failures**: any step can be redriven by moving messages from its DLQ back to the main queue:
```bash
aws sqs start-message-move-task \
  --source-arn <DLQ-ARN> \
  --destination-arn <Queue-ARN>
```

## Registered Indexes

| index_id | Source format | Download prefix | Parse step |
|---|---|---|---|
| `stoxx600` | PDF | `pdf/` | yes |
| `msci_emerging_markets` | XLS | `xls/` | yes |
| `msci_europe_small_cap_value_weighted` | XLSX | `xls/` | yes |
| `msci_usa_small_cap_value_weighted` | XLSX | `xls/` | yes |
| `msci_world_ex_us` | XLSX | `xls/` | yes |
| `msci_world` | CSV | `raw-csv/` | no (direct to processor) |

## `pipeline/` Package

All classes use an auto-registry pattern (`__init_subclass__`). Submodules in `pipeline/downloaders/`, `pipeline/parsers/`, and `pipeline/processors/` are auto-imported at module load — no central registry edits needed.

### `download.py`

- **`Downloader`** — ABC. Subclasses declare `index_id`, `url`, `filename` (supports `{date}`), `prefix`, `mime_type`, `referer`.
- **`Downloader.create(index_id) -> Downloader`** — factory.
- **`Downloader.index_ids() -> list[str]`** — all registered IDs (used by CDK to generate EventBridge rules).
- **`Downloader.download() -> DownloadResult`** — fetches source, validates size (>10 KB), raises on 403.
- **`download(index_id) -> DownloadResult`** — convenience wrapper.
- **`DownloadResult`** — `(content: bytes, key: str, mime_type: str)`.

### `parse.py`

- **`Parser`** — ABC. Subclasses declare `index_id`, `fields` (raw-csv column order), implement `parse(src_path: Path) -> list[dict]`.
- **`Parser.create(index_id) -> Parser`** — factory.
- **`Parser.to_csv(records) -> str`** — serialises to raw-csv format using `fields`.

### `process.py`

- **`Processor`** — ABC. Subclasses declare `index_id`, override `preprocess`, `filter_row`, `validate`, implement `process_row(row) -> Holding`.
- **`Processor.create(index_id) -> Processor`** — factory.
- **`Processor.process(content: str) -> list[Holding]`** — preprocess → parse CSV → filter → map rows → validate weight sum.
- **`Processor.to_csv(holdings) -> str`** — serialises to canonical output format.
- **Canonical output fields**: `Asset Name, ISIN, Country, Currency, Sector, Weight (%)`.
- **`Holding`** — typed dataclass with `name`, `isin`, `country` (`Country` enum), `currency` (`Currency` enum), `sector` (`Sector` enum), `weight`.

### `upload.py`

- **`upload(csv_content, credentials_json, sheet_id, sheet_name) -> dict`** — clears `{sheet_name}!A:F`, then writes all rows starting at A1.
- Uses **`google.auth.transport.requests.AuthorizedSession`** (a `requests.Session` subclass) to call the Sheets REST API directly. Do **not** switch to `google-api-python-client` / `httplib2`: on Lambda, `httplib2` causes systematic 2–3 minute hangs and `SSLEOFError` during token refresh due to stale-connection retries in Lambda's network environment. `requests` handles connection lifecycle correctly and reduces upload time to a few seconds.

## Local Runner

```bash
uv run python run_local.py --index <index_id> [--step download|parse|process] [--input <path>] [--output <dir>]
```

- Full pipeline (no `--step`): download → (parse if index has a Parser) → process.
- Output mirrors the S3 prefix layout under `./output/`.

## Adding a New Index

1. **Add a downloader** — create `pipeline/downloaders/<index_id>.py` subclassing `Downloader`. Set `prefix="raw-csv/"` for CSV, `prefix="xls/"` for XLS/XLSX, `prefix="pdf/"` for PDF. The EventBridge trigger is generated automatically from `Downloader.index_ids()` — no CDK changes needed.

2. **Add a parser** (XLS/XLSX/PDF only) — create `pipeline/parsers/<index_id>.py` subclassing `Parser`. Implement `parse(src_path) -> list[dict]`. The Parser Lambda dispatches via `Parser.create(index_id)`.

3. **Add a processor** — create `pipeline/processors/<index_id>.py` subclassing `Processor`. Implement `process_row(row) -> Holding`. The Processor Lambda dispatches via `Processor.create(index_id)`.

4. **Grant S3 access** — if the new index uses a prefix not already covered (`pdf/`, `xls/`, `raw-csv/`), add `bucket.grant_put(downloader, "<prefix>/*")` in `pipeline_stack.py`.
