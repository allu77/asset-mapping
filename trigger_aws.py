"""
Trigger the AWS pipeline by invoking the Downloader Lambda directly.

Usage:
    uv run python trigger_aws.py --index stoxx600
    uv run python trigger_aws.py --all
"""
import argparse
import json
import sys

import boto3

from pipeline.download import Downloader

STACK_NAME = "AssetMapping"


def _get_downloader_fn_name() -> str:
    cf = boto3.client("cloudformation")
    paginator = cf.get_paginator("list_stack_resources")
    for page in paginator.paginate(StackName=STACK_NAME):
        for r in page["StackResourceSummaries"]:
            if (
                r["ResourceType"] == "AWS::Lambda::Function"
                and r["LogicalResourceId"].startswith("Downloader")
            ):
                return r["PhysicalResourceId"]
    raise RuntimeError(f"Downloader Lambda not found in CloudFormation stack '{STACK_NAME}'")


def main() -> None:
    parser = argparse.ArgumentParser(description="Trigger the AWS pipeline for one or all indexes")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--index", choices=Downloader.index_ids(), metavar="INDEX_ID",
                       help=f"Index to trigger ({', '.join(Downloader.index_ids())})")
    group.add_argument("--all", action="store_true", help="Trigger all indexes")
    args = parser.parse_args()

    index_ids = Downloader.index_ids() if args.all else [args.index]

    print(f"Resolving Downloader Lambda in stack '{STACK_NAME}'...")
    try:
        fn_name = _get_downloader_fn_name()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Function: {fn_name}\n")

    lam = boto3.client("lambda")
    for index_id in index_ids:
        lam.invoke(
            FunctionName=fn_name,
            InvocationType="Event",
            Payload=json.dumps({"index_id": index_id}).encode(),
        )
        print(f"Triggered  {index_id}")


if __name__ == "__main__":
    main()
