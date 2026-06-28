import os

import boto3

from pipeline.download import download

S3_BUCKET = os.environ["S3_BUCKET"]
s3 = boto3.client("s3")


def handler(event, context):
    index_id = event["index_id"]
    result = download(index_id)
    s3.put_object(Bucket=S3_BUCKET, Key=result.key, Body=result.content, ContentType=result.mime_type)
    return {"bucket": S3_BUCKET, "key": result.key, "size": len(result.content)}
