"""
Lab 5a — Three access-pattern queries against the CloudAir single table.

Access patterns demonstrated:
  AP-1: Get a specific flight on a specific date  (table primary key)
  AP-2: List all bookings for a customer          (GSI1, by customer)
  AP-3: List all bookings on a date range         (GSI1, by customer + date prefix)

Reads USER_ID and AWS_REGION from the environment.
"""

import os

import boto3
from boto3.dynamodb.conditions import Key

USER_ID    = os.environ.get("USER_ID", "user1")
TABLE_NAME = f"CloudAir-{USER_ID}"
REGION     = os.environ.get("AWS_REGION", "us-east-1")

dynamodb = boto3.resource("dynamodb", region_name=REGION)
table    = dynamodb.Table(TABLE_NAME)


# ---------------------------------------------------------------------------
# AP-1: Get a specific flight by flight ID + date
#       Uses the table's primary key directly (no GSI) — 1 x GetItem
# ---------------------------------------------------------------------------
def ap1_get_flight(flight_id: str, date: str) -> None:
    print(f"\n--- AP-1: Get flight {flight_id} on {date} ---")
    resp = table.get_item(
        Key={"PK": f"FLIGHT#{flight_id}", "SK": f"DATE#{date}"}
    )
    item = resp.get("Item")
    if item:
        print(f"  Route       : {item['origin']} -> {item['destination']}")
        print(f"  Departure   : {item['departureTime']}  Arrival: {item['arrivalTime']}")
        print(f"  Seats avail : {item['availableSeats']} / {item['totalSeats']}")
        print(f"  Base price  : ${item['basePrice']}")
    else:
        print("  Not found.")


# ---------------------------------------------------------------------------
# AP-2: List all bookings for a customer (any date)
#       Uses GSI1: GSI1PK = "CUSTOMER#<id>", SK begins_with "BOOKING#"
# ---------------------------------------------------------------------------
def ap2_bookings_by_customer(customer_id: str) -> None:
    print(f"\n--- AP-2: All bookings for customer {customer_id} ---")
    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=(
            Key("GSI1PK").eq(f"CUSTOMER#{customer_id}")
            & Key("GSI1SK").begins_with("BOOKING#")
        ),
    )
    items = resp["Items"]
    print(f"  {len(items)} booking(s) found:")
    for b in items:
        print(f"    {b['bookingId']}  flight={b['flightId']}  date={b['date']}"
              f"  status={b['status']}  seat={b['seatNumber']}")


# ---------------------------------------------------------------------------
# AP-3: Bookings for a customer within a specific date range
#       Uses GSI1 with a BETWEEN sort-key condition on GSI1SK
# ---------------------------------------------------------------------------
def ap3_bookings_by_date_range(customer_id: str, start: str, end: str) -> None:
    print(f"\n--- AP-3: Bookings for {customer_id} between {start} and {end} ---")
    resp = table.query(
        IndexName="GSI1",
        KeyConditionExpression=(
            Key("GSI1PK").eq(f"CUSTOMER#{customer_id}")
            & Key("GSI1SK").between(
                f"BOOKING#{start}",
                f"BOOKING#{end}~",   # tilde sorts after digits — inclusive upper bound
            )
        ),
    )
    items = resp["Items"]
    print(f"  {len(items)} booking(s) in range:")
    for b in items:
        print(f"    {b['bookingId']}  date={b['date']}  status={b['status']}")


def main() -> None:
    print(f"Table: {TABLE_NAME}  Region: {REGION}")

    # AP-1: known flight
    ap1_get_flight("AA101", "2024-09-15")

    # AP-2: all bookings for Alice (CUST001) — should see BK10001 + BK10002
    ap2_bookings_by_customer("CUST001")

    # AP-2: all bookings for Bob (CUST002) — should see BK10003 + BK10004
    ap2_bookings_by_customer("CUST002")

    # AP-3: Alice's bookings on 2024-09-15 only
    ap3_bookings_by_date_range("CUST001", "2024-09-15", "2024-09-15")

    print("\nAll access patterns executed successfully.")


if __name__ == "__main__":
    main()
