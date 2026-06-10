"""
publish_booking.py
==================
Publish a BookingCreated event to the Cloud Air SNS topic.

Usage:
    python publish_booking.py <topic_arn> <booking_id>

The message body is JSON with a 'bookingId' and 'userId' field.
SNS delivers the message to every subscribed endpoint — including
the cloudair-<USER_ID>-bookings SQS queue you wired up in Lab 6a.
"""

import json
import sys
import uuid
import boto3

sns = boto3.client("sns", region_name="us-east-1")


def publish_booking(topic_arn: str, booking_id: str, user_id: str = "user1") -> str:
    """Publish a BookingCreated notification to SNS.

    Returns the MessageId assigned by SNS.
    """
    payload = {
        "bookingId": booking_id,
        "userId": user_id,
        "flightId": "CA-2501",
        "status": "CONFIRMED",
        "eventType": "BookingCreated",
    }

    response = sns.publish(
        TopicArn=topic_arn,
        Message=json.dumps(payload),
        Subject="BookingCreated",
        MessageAttributes={
            "eventType": {
                "DataType": "String",
                "StringValue": "BookingCreated",
            }
        },
    )
    message_id = response["MessageId"]
    print(f"Published BookingCreated  bookingId={booking_id}  MessageId={message_id}")
    return message_id


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python publish_booking.py <topic_arn> <booking_id> [user_id]")
        sys.exit(1)

    _topic_arn = sys.argv[1]
    _booking_id = sys.argv[2]
    _user_id = sys.argv[3] if len(sys.argv) > 3 else "user1"

    publish_booking(_topic_arn, _booking_id, _user_id)
