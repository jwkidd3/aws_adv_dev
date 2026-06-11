"""
Lab 5b — Lambda stub handlers for the Cloud Air booking saga.

Each handler is a separate Lambda function (separate entries in template.yaml).
Entry points:
  handlers.reserve_seat      — ReserveSeat state
  handlers.charge_payment    — ChargePayment state
  handlers.confirm_booking   — ConfirmBooking state
  handlers.cancel_reservation — CancelReservation (compensating transaction)

Simulating failure:
  Each handler checks its own step-specific flag:
    {"failReserve": true}  — triggers SeatUnavailableError in reserve_seat
    {"failPayment": true}  — triggers PaymentDeclinedError in charge_payment
    {"failConfirm": true}  — triggers a generic error in confirm_booking
  The Step Functions Catch block then routes to the compensating path.
"""

import json
import logging
import uuid

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Custom exception classes — Step Functions matches these by name in Catch
# ---------------------------------------------------------------------------

class SeatUnavailableError(Exception):
    """Raised when the requested seat cannot be reserved."""


class PaymentDeclinedError(Exception):
    """Raised when the payment processor declines the charge."""


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def reserve_seat(event: dict, context) -> dict:
    """
    Reserve a seat on the requested flight.

    Input keys (all optional for demo purposes):
      flightId    : str  — e.g. "AA101"
      seatNumber  : str  — e.g. "14A"
      failReserve : bool — set True to simulate SeatUnavailableError
    """
    logger.info("ReserveSeat input: %s", json.dumps(event))

    if event.get("failReserve"):
        raise SeatUnavailableError(
            f"Seat {event.get('seatNumber', '??')} is no longer available "
            f"on flight {event.get('flightId', '??')}"
        )

    reservation_id = f"RSV-{uuid.uuid4().hex[:8].upper()}"
    logger.info("Seat reserved — reservationId=%s", reservation_id)

    return {
        "status": "RESERVED",
        "reservationId": reservation_id,
        "flightId":      event.get("flightId", "AA101"),
        "seatNumber":    event.get("seatNumber", "14A"),
    }


def charge_payment(event: dict, context) -> dict:
    """
    Charge the customer for the booking.

    Reads reservationResult from the merged event (Step Functions ResultPath).
    Input keys:
      customerId   : str   — e.g. "CUST001"
      amount       : float — e.g. 299.00
      failPayment  : bool  — set True to simulate PaymentDeclinedError
    """
    logger.info("ChargePayment input: %s", json.dumps(event))

    if event.get("failPayment"):
        raise PaymentDeclinedError(
            f"Payment declined for customer {event.get('customerId', '??')}: "
            "card issuer rejected the transaction."
        )

    charge_id = f"CHG-{uuid.uuid4().hex[:8].upper()}"
    amount     = event.get("amount", 299.00)
    logger.info("Payment charged — chargeId=%s  amount=%.2f", charge_id, amount)

    return {
        "status":   "CHARGED",
        "chargeId": charge_id,
        "amount":   amount,
    }


def confirm_booking(event: dict, context) -> dict:
    """
    Write the final confirmed booking record.

    Input keys:
      customerId  : str
      flightId    : str
      failConfirm : bool — set True to simulate a generic States.ALL error
    """
    logger.info("ConfirmBooking input: %s", json.dumps(event))

    if event.get("failConfirm"):
        # Raise a plain Exception — Step Functions catches it as States.TaskFailed
        raise Exception("Booking confirmation service temporarily unavailable.")

    booking_id = f"BK-{uuid.uuid4().hex[:8].upper()}"
    logger.info("Booking confirmed — bookingId=%s", booking_id)

    return {
        "status":    "CONFIRMED",
        "bookingId": booking_id,
        "message":   "Your Cloud Air booking is confirmed. Have a great flight!",
    }


def cancel_reservation(event: dict, context) -> dict:
    """
    Compensating transaction: release the seat hold created by ReserveSeat.

    This handler should never fail permanently — it retries on transient errors.
    Idempotent: calling it multiple times on the same reservationId is safe.
    """
    logger.info("CancelReservation input: %s", json.dumps(event))

    reservation_result = event.get("reservationResult", {})
    # reservationResult is nested under Payload when using arn:aws:states:::lambda:invoke
    if "Payload" in reservation_result:
        reservation_result = reservation_result["Payload"]

    reservation_id = reservation_result.get("reservationId", "UNKNOWN")
    logger.info("Releasing seat hold — reservationId=%s", reservation_id)

    return {
        "status":        "CANCELLED",
        "reservationId": reservation_id,
        "message":       "Seat hold released. No charge applied.",
    }
