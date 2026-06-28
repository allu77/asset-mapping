import os
from datetime import date
from pathlib import Path

import boto3

from pipeline.parse import Parser

S3_BUCKET = os.environ["S3_BUCKET"]
s3 = boto3.client("s3")


def handler(event, context):
    if event.get("Event") == "s3:TestEvent":
        return
    src_key = event["Records"][0]["s3"]["object"]["key"]
    today = date.today().isoformat()
    # key formats:
    #   pdf/{index_id}_{date}.pdf  → strip ext, strip _date
    #   xls/{index_id}_raw_{date}.xls → strip ext, strip _date, strip _raw
    index_id = src_key.split("/")[-1].rsplit(".", 1)[0].rsplit("_", 1)[0].removesuffix("_raw")
    ext = Path(src_key).suffix
    tmp = Path(f"/tmp/{index_id}_{today}{ext}")
    s3.download_file(S3_BUCKET, src_key, str(tmp))
    parser = Parser.create(index_id)
    records = parser.parse(tmp)
    out_key = f"raw-csv/{index_id}_raw_{today}.csv"
    s3.put_object(Bucket=S3_BUCKET, Key=out_key, Body=parser.to_csv(records).encode(), ContentType="text/csv")
    return {"bucket": S3_BUCKET, "key": out_key, "count": len(records)}
