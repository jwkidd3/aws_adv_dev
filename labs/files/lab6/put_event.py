"""
put_event.py
============
Put a BookingCreated event onto the Cloud Air custom EventBridge bus.

Usage:
    python put_event.py <event_bus_name> <booking_id> [user_id]

The event detail follows the Cloud Air schema:
  source       : cloudair.bookings
  detail-type  : BookingCreated
  detail       : { bookingId, userId, flightId, status }

EventBridge rules that match source=cloudair.bookings AND
detail-type=BookingCreated will route this event to their configured targets
(Lambda, SQS, Step Functions, etc.).
"""

import json
import sys
import boto3

events_client = boto3.client("events", region_name="us-east-1")


def put_booking_event(
    bus_name: str,
    booking_id: str,
    user_id: str = "user1",
    flight_id: str = "CA-2501",
) -> str:
    """Put a single BookingCreated event and return the EventId."""
    detail = {
        "bookingId": booking_id,
        "userId": user_id,
        "flightId": flight_id,
        "status": "CONFIRMED",
    }

    response = events_client.put_events(
        Entries=[
            {
                "Source": "cloudair.bookings",
                "DetailType": "BookingCreated",
                "Detail": json.dumps(detail),
                "EventBusName": bus_name,
            }
        ]
    )

    entries = response.get("Entries", [])
    if not entries:
        raise RuntimeError("put_events returned no entries")

    entry = entries[0]
    if "ErrorCode" in entry:
        raise RuntimeError(
            f"put_events failed: {entry['ErrorCode']} — {entry.get('ErrorMessage')}"
        )

    event_id = entry["EventId"]
    print(
        f"Event sent   bus={bus_name}  bookingId={booking_id}  EventId={event_id}"
    )
    return event_id


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python put_event.py <event_bus_name> <booking_id> [user_id]")
        sys.exit(1)

    _bus = sys.argv[1]
    _booking_id = sys.argv[2]
    _user_id = sys.argv[3] if len(sys.argv) > 3 else "user1"

    put_booking_event(_bus, _booking_id, _user_id)
