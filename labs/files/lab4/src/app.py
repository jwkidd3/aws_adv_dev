"""
Cloud Air Flights Microservice — Lambda handler (python3.12)
HTTP API payload format version 2.0

Handles:
  GET /flights               — list all available flights (filtered by optional
                               query params: origin, destination, date)
  GET /flights/{flightId}    — retrieve a single flight by ID

The handler reads from the DynamoDB Bookings table created in Lab 2a.
If no flight items exist in the table it returns a static sample catalogue so
students can test the endpoint before seeding data.

Environment variables (injected by SAM / CloudFormation):
  BOOKINGS_TABLE   — DynamoDB table name  (required)
  LOG_LEVEL        — Python logging level (default: INFO)
"""

import json
import logging
import os
import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logger = logging.getLogger(__name__)
logger.setLevel(LOG_LEVEL)

# ── DynamoDB client (module-level — reused across warm invocations) ────────────
TABLE_NAME = os.environ["BOOKINGS_TABLE"]
_ddb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
table = _ddb.Table(TABLE_NAME)

# ── Static sample flights (fallback when the table has no flight items) ────────
SAMPLE_FLIGHTS = [
    {
        "flightId": "CA101",
        "origin": "JFK",
        "destination": "LAX",
        "departure": "2026-07-15T08:00:00Z",
        "arrival": "2026-07-15T11:30:00Z",
        "aircraft": "Boeing 737",
        "seatsAvailable": 42,
        "priceUsd": 289.00,
    },
    {
        "flightId": "CA202",
        "origin": "LAX",
        "destination": "ORD",
        "departure": "2026-07-15T13:00:00Z",
        "arrival": "2026-07-15T18:45:00Z",
        "aircraft": "Airbus A320",
        "seatsAvailable": 18,
        "priceUsd": 199.00,
    },
    {
        "flightId": "CA303",
        "origin": "ORD",
        "destination": "JFK",
        "departure": "2026-07-16T07:00:00Z",
        "arrival": "2026-07-16T10:15:00Z",
        "aircraft": "Boeing 737",
        "seatsAvailable": 55,
        "priceUsd": 159.00,
    },
    {
        "flightId": "CA404",
        "origin": "JFK",
        "destination": "MIA",
        "departure": "2026-07-16T15:30:00Z",
        "arrival": "2026-07-16T18:45:00Z",
        "aircraft": "Airbus A319",
        "seatsAvailable": 7,
        "priceUsd": 129.00,
    },
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ok(body: dict | list, status: int = 200) -> dict:
    """Return a well-formed HTTP API v2 response."""
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def _err(message: str, status: int = 500) -> dict:
    """Return a well-formed HTTP API v2 error response."""
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": message}),
    }


def _fetch_flights_from_ddb(origin: str | None, destination: str | None) -> list[dict]:
    """
    Scan the DynamoDB table for items with pk prefix 'FLIGHT#'.
    Returns an empty list if the table contains no flight items, which
    triggers the static sample fallback in the caller.
    """
    filter_expr = Attr("pk").begins_with("FLIGHT#")

    if origin:
        filter_expr = filter_expr & Attr("origin").eq(origin.upper())
    if destination:
        filter_expr = filter_expr & Attr("destination").eq(destination.upper())

    try:
        response = table.scan(FilterExpression=filter_expr)
        items = response.get("Items", [])
        # Handle DynamoDB pagination
        while "LastEvaluatedKey" in response:
            response = table.scan(
                FilterExpression=filter_expr,
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))
        logger.info("DynamoDB scan returned %d flight items", len(items))
        return items
    except ClientError as exc:
        logger.error("DynamoDB scan failed: %s", exc.response["Error"]["Message"])
        raise


def _fetch_flight_by_id(flight_id: str) -> dict | None:
    """
    Retrieve a single flight item from DynamoDB by its primary key.
    Returns None if the item does not exist.
    """
    try:
        response = table.get_item(Key={"pk": f"FLIGHT#{flight_id}", "sk": "METADATA"})
        return response.get("Item")
    except ClientError as exc:
        logger.error("DynamoDB get_item failed: %s", exc.response["Error"]["Message"])
        raise


# ── Route handlers ─────────────────────────────────────────────────────────────

def _list_flights(event: dict) -> dict:
    """Handle GET /flights — return all flights, with optional query-string filters."""
    params = event.get("queryStringParameters") or {}
    origin = params.get("origin")
    destination = params.get("destination")

    logger.info(
        "list_flights called — origin=%s destination=%s",
        origin,
        destination,
    )

    try:
        flights = _fetch_flights_from_ddb(origin, destination)
    except ClientError:
        return _err("Could not retrieve flights from the database.", 502)

    if not flights:
        # Table has no flight items yet — return the static sample catalogue
        logger.warning("No FLIGHT# items in DynamoDB; returning static sample catalogue")
        if origin or destination:
            flights = [
                f for f in SAMPLE_FLIGHTS
                if (not origin or f["origin"] == origin.upper())
                and (not destination or f["destination"] == destination.upper())
            ]
        else:
            flights = SAMPLE_FLIGHTS

    return _ok(
        {
            "flights": flights,
            "count": len(flights),
            "source": "dynamodb" if flights is not SAMPLE_FLIGHTS else "static-sample",
        }
    )


def _get_flight(flight_id: str) -> dict:
    """Handle GET /flights/{flightId} — return a single flight or 404."""
    logger.info("get_flight called — flightId=%s", flight_id)

    try:
        item = _fetch_flight_by_id(flight_id)
    except ClientError:
        return _err("Could not retrieve flight from the database.", 502)

    if item is None:
        # Fall back to static sample for demo purposes
        item = next((f for f in SAMPLE_FLIGHTS if f["flightId"] == flight_id), None)

    if item is None:
        return _err(f"Flight '{flight_id}' not found.", 404)

    return _ok(item)


# ── Main handler ───────────────────────────────────────────────────────────────

def handler(event: dict, context) -> dict:
    """
    Lambda entry point.

    HTTP API v2 event shape:
      event["routeKey"]            — e.g. "GET /flights"
      event["pathParameters"]      — e.g. {"flightId": "CA101"}
      event["queryStringParameters"] — e.g. {"origin": "JFK"}
    """
    route_key = event.get("routeKey", "")
    path_params = event.get("pathParameters") or {}

    logger.info(
        "Invoked — routeKey=%s requestId=%s",
        route_key,
        event.get("requestContext", {}).get("requestId", "n/a"),
    )

    if route_key == "GET /flights":
        return _list_flights(event)

    if route_key == "GET /flights/{flightId}":
        flight_id = path_params.get("flightId", "")
        if not flight_id:
            return _err("Missing flightId path parameter.", 400)
        return _get_flight(flight_id)

    logger.warning("Unhandled routeKey: %s", route_key)
    return _err(f"Route '{route_key}' is not handled by this function.", 404)
