# Pipeline Architecture

## S3 Prefix Layout

```
pdf/                  ← STOXX source PDFs (90-day lifecycle)
raw-csv/              ← normalised CSVs ready for processing
  stoxx600_raw_<date>.csv
  msci_world_raw_<date>.csv          ← iShares CSV downloaded as-is
  msci_europe_hedged_raw_<date>.csv  ← iShares CSV downloaded as-is
processed-csv/        ← final output (canonical schema)
  stoxx600_holdings_<date>.csv
  msci_world_holdings_<date>.csv
  msci_europe_hedged_holdings_<date>.csv
```

## Lambda Chain

```
EventBridge (monthly, 1st 06:00 UTC)
  → Downloader    event payload: {"index_id": "stoxx600" | "msci_world"}
  → S3 put (pdf/ or raw-csv/)

S3 trigger on pdf/
  → Parser        STOXX only — PDF → raw-csv/stoxx600_raw_<date>.csv

S3 trigger on raw-csv/
  → Processor     dispatches on filename:
                    stoxx600_*           → CURRENCY_MAP lookup
                    msci_world_*         → reads Market Currency column directly
                    msci_europe_hedged_* → reads Market Currency column directly
  → S3 put (processed-csv/)

S3 trigger on processed-csv/
  → Uploader      → Google Sheets (SSM credentials)
```

## `pipeline/` Package

### `download.py`
- **`INDEXES: dict[str, IndexConfig]`** — registry of all supported indexes.  
  Each entry declares `url`, `filename` (with `{date}` placeholder), `prefix`, `mime_type`, `referer`.
- **`download(index_id: str) -> DownloadResult`** — fetches the source file, validates size, returns `(content, key, mime_type)`.
- Current indexes: `"stoxx600"` (PDF → `pdf/`), `"msci_world"` (iShares CSV → `raw-csv/`), `"msci_europe_hedged"` (iShares CSV → `raw-csv/`).

### `parse.py`
- **`parse_pdf(pdf_path: Path) -> list[dict]`** — STOXX only. Regex-extracts 600 rows from PDF. Raises `ValueError` if count ≠ 600.
- **`to_csv(records) -> str`** — serialises to canonical raw-csv format.
- Canonical fields: `Asset Name, Sector, Country, Weight (%)`.

### `process.py`
- **`process_records(records: list[dict]) -> list[dict]`** — STOXX: maps country → ISO 4217 via `CURRENCY_MAP`. Raises on unknown country.
- **`process_msci_world_csv(content: str) -> list[dict]`** — MSCI World: strips iShares BOM + 2-line header, filters `Asset Class == "Equity"`, reads `Market Currency` directly. Validates 1,200–1,600 rows.
- **`process_msci_europe_hedged_csv(content: str) -> list[dict]`** — MSCI Europe EUR Hedged (IMEAX): same iShares format. Validates 300–500 rows.
- **`to_csv(records) -> str`** — serialises to canonical processed-csv format.
- Canonical fields: `Asset Name, Currency, Sector, Weight (%), Country`.

## Local Runner

```bash
uv run python run_local.py --index <index_id> [--step download|parse|process] [--input <path>] [--output <dir>]
```

- Full pipeline (no `--step`): download → (parse if stoxx600) → process.
- MSCI World skips the parse step; the downloaded CSV goes straight to process.
- Output mirrors the S3 prefix layout under `./output/`.

## Adding a New Index

1. Add an `IndexConfig` entry to `INDEXES` in `pipeline/download.py`.  
   - If it's a structured CSV: set `prefix="raw-csv/"` and add a `process_<name>_csv()` branch in `pipeline/process.py` and `lambda_processor/handler.py`.  
   - If it's a PDF: set `prefix="pdf/"` and extend `lambda_parser/handler.py` with a new parse branch.
2. Add an EventBridge rule in `infra/stacks/pipeline_stack.py` with the appropriate `{"index_id": "..."}` payload.
3. Grant the downloader `bucket.grant_put` for the target prefix if it's new.
