"""
worker.py
=========
SQS-consumer Lambda handler for Cloud Air booking notifications.

Design decisions
----------------
* **Idempotency guard** — each booking message carries a bookingId.  The
  handler checks a DynamoDB 'ProcessedBookings' table (created in Lab 6a)
  before doing real work, so replaying the same SQS message is safe.
* **Poison-message simulation** — if the message JSON contains
  ``"poison": true`` the handler raises ``ValueError``.  SQS will retry the
  message ``maxReceiveCount`` times (set on the queue), then move it to the
  DLQ so you can inspect it without blocking healthy messages.
* The function processes records one at a time so a single poison record does
  NOT silently skip the others.  In production you would use partial-batch
  failure reporting (``ReportBatchItemFailures``); that pattern is discussed
  in the Lab 6a Discussion section.
"""

import json
import os
import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

# Set via Lambda environment variable; defaults allow local testing.
PROCESSED_TABLE = os.environ.get("PROCESSED_TABLE", "ProcessedBookings")


def _is_duplicate(booking_id: str) -> bool:
    """Return True if this bookingId has already been processed."""
    table = dynamodb.Table(PROCESSED_TABLE)
    try:
        resp = table.get_item(
            Key={"bookingId": booking_id},
            ConsistentRead=True,
        )
        return "Item" in resp
    except ClientError as exc:
        # If the table doesn't exist yet (first deploy) treat as not-duplicate.
        if exc.response["Error"]["Code"] == "ResourceNotFoundException":
            return False
        raise


def _mark_processed(booking_id: str) -> None:
    """Write a processed-record entry so replays are skipped."""
    table = dynamodb.Table(PROCESSED_TABLE)
    table.put_item(
        Item={"bookingId": booking_id},
        ConditionExpression="attribute_not_exists(bookingId)",
    )


def process_booking(body: dict) -> None:
    """Business logic for a single BookingCreated message.

    Replace this stub with real downstream work (e.g. send email, update
    read-model, trigger payment).
    """
    booking_id = body["bookingId"]

    # --- Poison-message simulation ---
    if body.get("poison"):
        raise ValueError(f"Poison message detected for bookingId={booking_id}")

    # --- Idempotency check ---
    if _is_duplicate(booking_id):
        print(f"SKIP duplicate bookingId={booking_id}")
        return

    # --- Real work goes here ---
    print(
        f"PROCESSED bookingId={booking_id} userId={body.get('userId')} "
        f"flight={body.get('flightId')} status={body.get('status')}"
    )

    _mark_processed(booking_id)


def handler(event: dict, context) -> dict:
    """Lambda entry point — invoked by SQS trigger."""
    for record in event["Records"]:
        # SQS wraps the SNS notification in an extra envelope when the queue
        # is subscribed to an SNS topic (SNS → SQS fan-out).  Unwrap if needed.
        raw_body = record["body"]
        outer = json.loads(raw_body)

        if "Message" in outer:
            # SNS envelope — the real payload is in outer["Message"]
            body = json.loads(outer["Message"])
        else:
            body = outer

        process_booking(body)

    return {"statusCode": 200, "processed": len(event["Records"])}
