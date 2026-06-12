"""
xray_handler.py
===============
Cloud Air Flights Lambda handler instrumented with the AWS X-Ray SDK.

Drop-in replacement for the lab4/src/app.py handler produced in Lab 4a.
Copy this file to ~/environment/aws-adv-dev/lab4/src/app.py and redeploy
with SAM (see Lab 7b instructions).

Key instrumentation points
--------------------------
1. ``patch_all()``  — monkey-patches every boto3 client so DynamoDB calls
   appear as automatic subsegments in X-Ray with latency, status, and
   request/response metadata.
2. ``@xray_recorder.capture("get_flights")`` — wraps the business-logic
   function in a named subsegment visible in the X-Ray trace timeline.
3. ``xray_recorder.put_annotation()`` — adds indexed key/value pairs that
   you can filter on in the X-Ray console (e.g. find all traces where
   userId=user3 AND statusCode=500).
4. ``xray_recorder.put_metadata()`` — attaches arbitrary data to the trace
   that is NOT indexed (useful for large payloads you want to inspect but
   not filter on).
"""

import json
import os

import boto3
from aws_xray_sdk.core import patch_all, xray_recorder

# Instrument all boto3 calls BEFORE creating any clients.
patch_all()

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
TABLE_NAME = os.environ.get("BOOKINGS_TABLE", "Bookings-user1")


@xray_recorder.capture("get_flights")
def _get_flights(table_name: str) -> list:
    """Scan the Flights partition and return all items.

    The @capture decorator creates a named subsegment in the trace so you
    can see exactly how long the DynamoDB scan took independently of the
    Lambda initialisation overhead.
    """
    table = dynamodb.Table(table_name)
    response = table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr("PK").begins_with("FLIGHT#")
    )
    return response.get("Items", [])


def handler(event: dict, context) -> dict:
    """Lambda entry point for GET /flights."""
    user_id = (event.get("requestContext") or {}).get("identity", {}).get(
        "user", "anonymous"
    )
    method = (event.get("requestContext") or {}).get("http", {}).get("method", "GET")

    # IMPORTANT: in Lambda the function runs inside an X-Ray *facade* segment that
    # cannot be mutated — calling put_annotation/put_metadata on it raises
    # FacadeSegmentMutationException. Annotations and metadata must target a
    # SUBSEGMENT. Open one for the whole request; the values are then indexed and
    # filterable in the X-Ray console (e.g. annotation.tableName = "Bookings-...").
    with xray_recorder.in_subsegment("get_flights_request") as subsegment:
        subsegment.put_annotation("userId", user_id)
        subsegment.put_annotation("httpMethod", method)
        subsegment.put_annotation("tableName", TABLE_NAME)
        subsegment.put_metadata("rawEvent", event)  # metadata is NOT indexed

        try:
            flights = _get_flights(TABLE_NAME)
            subsegment.put_annotation("flightCount", len(flights))
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"flights": flights}),
            }
        except Exception as exc:  # noqa: BLE001
            subsegment.put_annotation("error", str(exc)[:200])
            return {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "internal error"}),
            }
