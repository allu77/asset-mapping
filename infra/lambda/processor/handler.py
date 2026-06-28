import os
from datetime import date

import boto3

from pipeline.process import Processor

S3_BUCKET = os.environ["S3_BUCKET"]
s3 = boto3.client("s3")


def handler(event, context):
    if event.get("Event") == "s3:TestEvent":
        return
    src_key = event["Records"][0]["s3"]["object"]["key"]
    today = date.today().isoformat()
    # key format: raw-csv/{index_id}_raw_{date}.csv
    index_id = src_key.split("/")[-1].split("_raw_")[0]
    content = s3.get_object(Bucket=S3_BUCKET, Key=src_key)["Body"].read().decode()
    processor = Processor.create(index_id)
    processed = processor.process(content)
    out_key = f"processed-csv/{index_id}_holdings_{today}.csv"
    s3.put_object(Bucket=S3_BUCKET, Key=out_key, Body=processor.to_csv(processed).encode(), ContentType="text/csv")
    return {"bucket": S3_BUCKET, "key": out_key, "count": len(processed)}
