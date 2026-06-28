#!/usr/bin/env python3
"""
Redrive failed events from DLQs back to their target Lambda functions.

Usage:
  uv run python redrive.py                           # interactive: all queues
  uv run python redrive.py --queue parser            # interactive: parser DLQ only
  uv run python redrive.py --index_id msci_world     # search all DLQs by index_id
  uv run python redrive.py --all                     # non-interactive: redrive all
  uv run python redrive.py --all --queue downloader  # redrive all in one queue
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from typing import NamedTuple

import boto3
from botocore.exceptions import ClientError

STACK_NAME = "AssetMapping"
QUEUE_NAMES = ["downloader", "parser", "processor", "uploader"]
_VISIBILITY_HOLD = 120  # seconds to hold messages while we process them


class _Event(NamedTuple):
    queue_name: str
    index_id: str | None
    timestamp: str
    payload: dict
    receipt_handle: str
    dlq_url: str
    fn_name: str


def _extract_index_id(queue_name: str, payload: dict) -> str | None:
    try:
        if queue_name == "downloader":
            return payload.get("index_id")
        key = payload["Records"][0]["s3"]["object"]["key"]
        filename = key.split("/")[-1]
        if queue_name == "parser":
            return filename.rsplit(".", 1)[0].rsplit("_", 1)[0].removesuffix("_raw")
        if queue_name == "processor":
            return filename.split("_raw_")[0]
        if queue_name == "uploader":
            return filename.split("_holdings_")[0]
    except (KeyError, IndexError):
        pass
    return None


def _discover(stack_name: str, queues: list[str]) -> dict[str, dict]:
    cf = boto3.client("cloudformation")
    try:
        paginator = cf.get_paginator("list_stack_resources")
        all_resources: list[dict] = []
        for page in paginator.paginate(StackName=stack_name):
            all_resources.extend(page["StackResourceSummaries"])
    except ClientError as exc:
        print(f"Error reading CloudFormation stack {stack_name!r}: {exc}", file=sys.stderr)
        sys.exit(1)

    def _find(prefix: str, rtype: str) -> str | None:
        # CDK appends a hash to logical IDs, so match by prefix + resource type
        for r in all_resources:
            if r["ResourceType"] == rtype and r["LogicalResourceId"].startswith(prefix):
                return r["PhysicalResourceId"]
        return None

    result = {}
    for name in queues:
        cap = name.capitalize()
        dlq_url = _find(f"{cap}DLQ", "AWS::SQS::Queue")
        fn_name = _find(cap, "AWS::Lambda::Function")
        if dlq_url and fn_name:
            result[name] = {"dlq_url": dlq_url, "fn_name": fn_name}
        else:
            print(f"Warning: could not find resources for {name!r} in stack {stack_name!r}", file=sys.stderr)
    return result


def _poll_queue(queue_name: str, dlq_url: str, fn_name: str, index_id_filter: str | None) -> list[_Event]:
    sqs = boto3.client("sqs")
    events: list[_Event] = []
    seen: set[str] = set()

    for _ in range(10):
        resp = sqs.receive_message(
            QueueUrl=dlq_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=0,
            VisibilityTimeout=_VISIBILITY_HOLD,
            AttributeNames=["SentTimestamp"],
        )
        msgs = [m for m in resp.get("Messages", []) if m["MessageId"] not in seen]
        if not msgs:
            break
        for msg in msgs:
            seen.add(msg["MessageId"])
            body = json.loads(msg["Body"])
            # Support both the Lambda async failure envelope and raw events (legacy format)
            payload = body.get("requestPayload", body)
            timestamp = body.get("timestamp", "")
            if not timestamp:
                sent_ms = int(msg.get("Attributes", {}).get("SentTimestamp", 0))
                if sent_ms:
                    timestamp = datetime.fromtimestamp(sent_ms / 1000, tz=timezone.utc).isoformat()

            index_id = _extract_index_id(queue_name, payload)
            if index_id_filter and index_id != index_id_filter:
                sqs.change_message_visibility(
                    QueueUrl=dlq_url, ReceiptHandle=msg["ReceiptHandle"], VisibilityTimeout=0
                )
                continue
            events.append(_Event(
                queue_name=queue_name,
                index_id=index_id,
                timestamp=timestamp,
                payload=payload,
                receipt_handle=msg["ReceiptHandle"],
                dlq_url=dlq_url,
                fn_name=fn_name,
            ))
    return events


def _release(events: list[_Event]) -> None:
    sqs = boto3.client("sqs")
    for ev in events:
        sqs.change_message_visibility(
            QueueUrl=ev.dlq_url, ReceiptHandle=ev.receipt_handle, VisibilityTimeout=0
        )


def _invoke(ev: _Event) -> bool:
    lam = boto3.client("lambda")
    sqs = boto3.client("sqs")
    try:
        resp = lam.invoke(
            FunctionName=ev.fn_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(ev.payload).encode(),
        )
        if resp.get("FunctionError"):
            error = resp["Payload"].read().decode()
            print(f"FAILED (Lambda error: {error})")
            sqs.change_message_visibility(
                QueueUrl=ev.dlq_url, ReceiptHandle=ev.receipt_handle, VisibilityTimeout=0
            )
            return False
        sqs.delete_message(QueueUrl=ev.dlq_url, ReceiptHandle=ev.receipt_handle)
        return True
    except Exception as exc:
        print(f"FAILED ({exc})")
        sqs.change_message_visibility(
            QueueUrl=ev.dlq_url, ReceiptHandle=ev.receipt_handle, VisibilityTimeout=0
        )
        return False


def _print_table(events: list[_Event]) -> None:
    print(f"\n{'#':<4} {'Queue':<12} {'Index ID':<40} {'Failed At'}")
    print("-" * 80)
    for i, ev in enumerate(events, 1):
        print(f"{i:<4} {ev.queue_name:<12} {ev.index_id or '?':<40} {ev.timestamp}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description="Redrive failed DLQ events to their Lambda functions")
    ap.add_argument("--all", action="store_true", help="Non-interactive: redrive every matching event")
    ap.add_argument("--queue", choices=QUEUE_NAMES, help="Scope to a single DLQ")
    ap.add_argument("--index_id", help="Filter events by index_id")
    args = ap.parse_args()

    queues = [args.queue] if args.queue else QUEUE_NAMES
    resources = _discover(STACK_NAME, queues)
    if not resources:
        print("No resources found. Is the stack deployed?")
        sys.exit(1)

    print("Polling DLQs...")
    all_events: list[_Event] = []
    for name in queues:
        res = resources.get(name)
        if res:
            all_events.extend(_poll_queue(name, res["dlq_url"], res["fn_name"], args.index_id))

    if not all_events:
        print("No failed events found.")
        return

    if args.all:
        for ev in all_events:
            print(f"Redriving {ev.queue_name}/{ev.index_id or '?'}... ", end="", flush=True)
            print("OK" if _invoke(ev) else "")
        return

    # Interactive mode
    _print_table(all_events)

    if len(all_events) == 1:
        ev = all_events[0]
        print(f"Single event found ({ev.queue_name}/{ev.index_id or '?'}). Redriving automatically...")
        print("OK" if _invoke(ev) else "")
        return

    raw = input("Enter number(s) to redrive (e.g. 1,3), 'a' for all, or 'q' to quit: ").strip()

    if raw.lower() in ("q", ""):
        print("Cancelled.")
        _release(all_events)
        return

    if raw.lower() == "a":
        chosen = all_events
        unchosen: list[_Event] = []
    else:
        indices: set[int] = set()
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit() and 1 <= int(part) <= len(all_events):
                indices.add(int(part) - 1)
            else:
                print(f"Ignoring invalid selection: {part!r}")
        chosen = [all_events[i] for i in sorted(indices)]
        unchosen = [ev for i, ev in enumerate(all_events) if i not in indices]

    _release(unchosen)

    for ev in chosen:
        print(f"Redriving {ev.queue_name}/{ev.index_id or '?'}... ", end="", flush=True)
        print("OK" if _invoke(ev) else "")


if __name__ == "__main__":
    main()
