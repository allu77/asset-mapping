import json
import logging
import os

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from pipeline.upload import upload

S3_BUCKET = os.environ["S3_BUCKET"]
SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
CREDENTIALS_PARAM = os.environ["GOOGLE_CREDENTIALS_PARAM"]

s3_client = boto3.client("s3")
ssm_client = boto3.client("ssm")

credentials_json = ssm_client.get_parameter(Name=CREDENTIALS_PARAM, WithDecryption=True)["Parameter"]["Value"]

def handler(event, context):
    failures = []
    for record in event["Records"]:
        try:
            s3_event = json.loads(record["body"])
            if s3_event.get("Event") == "s3:TestEvent":
                continue
            src_key = s3_event["Records"][0]["s3"]["object"]["key"]
            # e.g. "processed-csv/stoxx600_holdings_2026-05-01.csv" → "stoxx600"
            index_id = src_key.split("/")[-1].split("_holdings_")[0]

            logger.info("Reading file %s", src_key)
            csv_content = s3_client.get_object(Bucket=S3_BUCKET, Key=src_key)["Body"].read().decode("utf-8")

            logger.info("Uploading data from %s to Google Sheet", src_key)
            upload(csv_content, credentials_json, SHEET_ID, index_id)
            logger.info("Upload complete")
        except Exception:
            logger.exception("Failed to process record %s", record.get("messageId"))
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}
