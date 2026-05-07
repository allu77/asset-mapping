"""
Local pipeline runner. Mirrors the AWS Lambda chain using local files.

Usage:
    uv run python run_local.py --index stoxx600                    # full pipeline
    uv run python run_local.py --index msci_world --step download
    uv run python run_local.py --index stoxx600 --step parse   --input output/pdf/STOXX_2026-05-01.pdf
    uv run python run_local.py --index stoxx600 --step process --input output/raw-csv/stoxx600_raw_2026-05-01.csv
    uv run python run_local.py --index stoxx600 --step upload  --input output/processed-csv/stoxx600_holdings_2026-05-01.csv --credentials /path/to/creds.json

Output is written to ./output/ mirroring S3 prefixes:
    output/pdf/STOXX_<date>.pdf
    output/raw-csv/stoxx600_raw_<date>.csv  (or IWDA_<date>.csv for msci_world)
    output/processed-csv/STOXX_holdings_<date>.csv
"""
import argparse
import os
from pathlib import Path

from pipeline.download import Downloader, download
from pipeline.parse import Parser
from pipeline.process import Processor


def run_download(index_id: str, output_dir: Path) -> Path:
    result = download(index_id)
    path = output_dir / result.key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(result.content)
    print(f"Downloaded → {path}")
    return path


def run_parse(input_path: Path, output_dir: Path, index_id: str) -> Path:
    from datetime import date
    today = date.today().isoformat()
    parser = Parser.create(index_id)
    records = parser.parse(input_path)
    csv_path = output_dir / "raw-csv" / f"{index_id}_raw_{today}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(parser.to_csv(records), encoding="utf-8")
    print(f"Parsed {len(records)} records → {csv_path}")
    return csv_path


def run_process(raw_csv_path: Path, output_dir: Path, index_id: str) -> Path:
    from datetime import date
    today = date.today().isoformat()
    content = raw_csv_path.read_text(encoding="utf-8")
    processor = Processor.create(index_id)
    processed = processor.process(content)
    out_path = output_dir / "processed-csv" / f"{index_id}_holdings_{today}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(processor.to_csv(processed), encoding="utf-8")
    print(f"Processed {len(processed)} records → {out_path}")
    return out_path


def run_upload(processed_csv_path: Path, credentials_path: Path, index_id: str) -> None:
    from pipeline.upload import upload
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise SystemExit("GOOGLE_SHEET_ID environment variable is required for --step upload")
    csv_content = processed_csv_path.read_text(encoding="utf-8")
    credentials_json = credentials_path.read_text(encoding="utf-8")
    result = upload(csv_content, credentials_json, sheet_id, index_id)
    print(f"Uploaded {result['rows_written']} rows → sheet {result['sheet_id']} (tab: {index_id})")


def main():
    parser = argparse.ArgumentParser(description="Run index holdings pipeline locally")
    parser.add_argument("--index", required=True, choices=Downloader.index_ids(),
                        help="Index to process")
    parser.add_argument("--step", choices=["download", "parse", "process", "upload"],
                        help="Run a single step (default: all steps)")
    parser.add_argument("--input", type=Path,
                        help="Input file path for --step parse, process, or upload")
    parser.add_argument("--credentials", type=Path, default=Path("credentials.json"),
                        help="Service account JSON for --step upload (default: credentials.json)")
    parser.add_argument("--output", type=Path, default=Path("output"),
                        help="Output directory (default: output/)")
    args = parser.parse_args()

    output_dir = args.output

    if args.step == "download":
        run_download(args.index, output_dir)
        return

    if args.step == "parse":
        if not args.input:
            parser.error("--input is required for --step parse")
        run_parse(args.input, output_dir, args.index)
        return

    if args.step == "process":
        if not args.input:
            parser.error("--input is required for --step process")
        run_process(args.input, output_dir, args.index)
        return

    if args.step == "upload":
        if not args.input:
            parser.error("--input is required for --step upload")
        if not args.credentials:
            parser.error("--credentials is required for --step upload")
        run_upload(args.input, args.credentials, args.index)
        return

    # Full pipeline
    downloaded_path = run_download(args.index, output_dir)
    if args.index in [ "stoxx600", "msci_usa_small_cap_value_weighted", "msci_europe_small_cap_value_weighted", "msci_emerging_markets" ]:
        downloaded_path = run_parse(downloaded_path, output_dir, args.index)
    processed_path = run_process(downloaded_path, output_dir, args.index)
    run_upload(processed_path, args.credentials, args.index)


if __name__ == "__main__":
    main()
