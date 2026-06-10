"""
Lab 5a — Bulk-load items.json into the CloudAir-$USER_ID table.

Uses boto3 batch_writer which handles:
  - automatic chunking to DynamoDB's 25-item limit per BatchWriteItem call
  - automatic retry of UnprocessedItems

Reads USER_ID and AWS_REGION from the environment.
Run after create_table.py.
"""

import json
import os
from decimal import Decimal
from pathlib import Path

import boto3

USER_ID    = os.environ.get("USER_ID", "user1")
TABLE_NAME = f"CloudAir-{USER_ID}"
REGION     = os.environ.get("AWS_REGION", "us-east-1")

ITEMS_FILE = Path(__file__).parent / "items.json"


def decimal_convert(obj):
    """Convert float values from JSON into Decimal for DynamoDB."""
    if isinstance(obj, list):
        return [decimal_convert(i) for i in obj]
    if isinstance(obj, dict):
        return {k: decimal_convert(v) for k, v in obj.items()}
    if isinstance(obj, float):
        return Decimal(str(obj))
    return obj


def load_items() -> list[dict]:
    raw = json.loads(ITEMS_FILE.read_text())
    return decimal_convert(raw)


def main() -> None:
    items = load_items()
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table    = dynamodb.Table(TABLE_NAME)

    print(f"Loading {len(items)} items into {TABLE_NAME} …")
    with table.batch_writer() as writer:
        for item in items:
            writer.put_item(Item=item)

    print(f"Done. {len(items)} items written to {TABLE_NAME}.")
    print("Next step: python3 queries.py")


if __name__ == "__main__":
    main()
