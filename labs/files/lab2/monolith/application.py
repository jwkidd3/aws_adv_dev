"""
Cloud Air — Legacy Monolith
============================
All routes live in a single Flask application: home, flight search,
booking creation, and booking retrieval. This is the "before" state
that the course gradually decomposes into microservices.

Environment variables (read on startup):
  USER_ID          — student identifier, used to scope the DynamoDB table
  BOOKINGS_TABLE   — DynamoDB table name (default: Bookings-<USER_ID>)
  AWS_REGION       — AWS region (default: us-east-1)
"""

import os
import uuid
import logging
from datetime import datetime

import boto3
from flask import Flask, jsonify, request, abort

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cloudair")

# ── Config (12-Factor: read from environment) ─────────────────────────────────
USER_ID = os.environ.get("USER_ID", "user1")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
BOOKINGS_TABLE = os.environ.get("BOOKINGS_TABLE", f"Bookings-{USER_ID}")

log.info("Starting Cloud Air monolith: table=%s region=%s", BOOKINGS_TABLE, AWS_REGION)

# ── AWS clients ───────────────────────────────────────────────────────────────
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(BOOKINGS_TABLE)

# ── Fake flight data (would be a DB query in production) ─────────────────────
FLIGHTS = [
    {"flightId": "CA101", "origin": "JFK", "destination": "LAX",
     "departure": "08:00", "arrival": "11:30", "price": 299},
    {"flightId": "CA202", "origin": "LAX", "destination": "ORD",
     "departure": "13:00", "arrival": "19:15", "price": 189},
    {"flightId": "CA303", "origin": "ORD", "destination": "MIA",
     "departure": "07:30", "arrival": "11:45", "price": 149},
    {"flightId": "CA404", "origin": "MIA", "destination": "SEA",
     "departure": "15:00", "arrival": "20:30", "price": 349},
]

# ── Flask application ─────────────────────────────────────────────────────────
app = Flask(__name__)


@app.route("/")
def index():
    """Health check / welcome endpoint."""
    return jsonify({
        "service": "Cloud Air Monolith",
        "version": "1.0.0-monolith",
        "status": "running",
        "user": USER_ID,
        "note": "This is the legacy monolith — all routes in one deployable unit.",
    })


@app.route("/flights")
def list_flights():
    """
    Return available flights, with optional origin/destination query params.
    In the monolith this is a simple in-memory filter; later labs move this to
    a dedicated microservice backed by a purpose-built data store.
    """
    origin = request.args.get("origin", "").upper()
    destination = request.args.get("destination", "").upper()

    results = FLIGHTS
    if origin:
        results = [f for f in results if f["origin"] == origin]
    if destination:
        results = [f for f in results if f["destination"] == destination]

    log.info("GET /flights origin=%s destination=%s → %d results", origin, destination, len(results))
    return jsonify({"flights": results, "count": len(results)})


@app.route("/bookings", methods=["POST"])
def create_booking():
    """
    Create a new booking and persist it to DynamoDB.
    Expected JSON body: { "flightId": "CA101", "passengerName": "Alice" }
    """
    body = request.get_json(silent=True)
    if not body:
        abort(400, description="Request body must be JSON.")

    flight_id = body.get("flightId")
    passenger_name = body.get("passengerName")
    if not flight_id or not passenger_name:
        abort(400, description="flightId and passengerName are required.")

    # Validate the flight exists (in a real service: query flights DB)
    flight = next((f for f in FLIGHTS if f["flightId"] == flight_id), None)
    if not flight:
        abort(404, description=f"Flight {flight_id!r} not found.")

    booking_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat() + "Z"

    item = {
        "bookingId": booking_id,
        "userId": USER_ID,
        "flightId": flight_id,
        "passengerName": passenger_name,
        "origin": flight["origin"],
        "destination": flight["destination"],
        "price": str(flight["price"]),   # DynamoDB: use strings for decimals in demo
        "status": "CONFIRMED",
        "createdAt": created_at,
    }

    table.put_item(Item=item)
    log.info("POST /bookings → created bookingId=%s flightId=%s", booking_id, flight_id)

    return jsonify({"bookingId": booking_id, "status": "CONFIRMED", "createdAt": created_at}), 201


@app.route("/bookings")
def list_bookings():
    """
    Return all bookings for this student's USER_ID.
    Uses a GSI query rather than a full scan — still in the same monolith,
    but designed so the access pattern carries over to the microservice.
    """
    try:
        response = table.query(
            IndexName="userId-index",
            KeyConditionExpression=boto3.dynamodb.conditions.Key("userId").eq(USER_ID),
        )
        bookings = response.get("Items", [])
    except Exception as exc:
        log.error("DynamoDB query failed: %s", exc)
        abort(500, description="Could not retrieve bookings.")

    log.info("GET /bookings → %d bookings for userId=%s", len(bookings), USER_ID)
    return jsonify({"bookings": bookings, "count": len(bookings)})


@app.route("/bookings/<booking_id>")
def get_booking(booking_id):
    """Retrieve a single booking by its ID."""
    response = table.get_item(Key={"bookingId": booking_id})
    item = response.get("Item")
    if not item:
        abort(404, description=f"Booking {booking_id!r} not found.")

    log.info("GET /bookings/%s → found", booking_id)
    return jsonify(item)


# ── Error handlers ────────────────────────────────────────────────────────────
@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(500)
def http_error(exc):
    return jsonify({"error": exc.description, "status": exc.code}), exc.code


# ── Entry point (local dev only; EB uses Gunicorn via Procfile) ───────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
