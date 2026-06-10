"""
Lab 5a — Create the CloudAir single-table design in DynamoDB.

Creates table  CloudAir-$USER_ID  with:
  - Primary key  : PK (S) + SK (S)
  - GSI          : GSI1  on GSI1PK (S) + GSI1SK (S), projection ALL

Reads USER_ID from the environment (set by ~/.aws-adv-dev.env).
Waits until the table status reaches ACTIVE before exiting.
"""

import os
import sys
import time

import boto3
from botocore.exceptions import ClientError

USER_ID    = os.environ.get("USER_ID", "user1")
TABLE_NAME = f"CloudAir-{USER_ID}"
REGION     = os.environ.get("AWS_REGION", "us-east-1")

client = boto3.client("dynamodb", region_name=REGION)


def create_table() -> None:
    print(f"Creating table: {TABLE_NAME} in {REGION} …")
    try:
        client.create_table(
            TableName=TABLE_NAME,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "PK",     "AttributeType": "S"},
                {"AttributeName": "SK",     "AttributeType": "S"},
                {"AttributeName": "GSI1PK", "AttributeType": "S"},
                {"AttributeName": "GSI1SK", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "GSI1",
                    "KeySchema": [
                        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            Tags=[
                {"Key": "Project", "Value": "CloudAir"},
                {"Key": "Owner",   "Value": USER_ID},
            ],
        )
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "ResourceInUseException":
            print(f"Table {TABLE_NAME} already exists — continuing.")
        else:
            raise


def wait_active() -> None:
    print("Waiting for ACTIVE status …", end="", flush=True)
    waiter = client.get_waiter("table_exists")
    waiter.wait(
        TableName=TABLE_NAME,
        WaiterConfig={"Delay": 5, "MaxAttempts": 24},
    )
    desc = client.describe_table(TableName=TABLE_NAME)
    status = desc["Table"]["TableStatus"]
    gsi_count = len(desc["Table"].get("GlobalSecondaryIndexes", []))
    print(f" done.  status={status}  GSIs={gsi_count}")


def main() -> None:
    create_table()
    wait_active()
    print(f"\nTable ready: {TABLE_NAME}")
    print("Next step: python3 bulk_load.py")


if __name__ == "__main__":
    main()
