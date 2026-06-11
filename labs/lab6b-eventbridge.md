# 🧪 Lab 6b — Event-Driven Cloud Air with EventBridge

*Hands-On Lab · 50 min · Console + CLI · Day 3 — Resilience & Event-Driven Decoupling*

## Objectives (3 min)

- Create a custom EventBridge event bus `cloudair-$USER_ID`
- Publish a `BookingCreated` event using boto3 and the AWS CLI
- Create an event rule with a pattern that matches `source = cloudair.bookings`
- Route matched events to a target (SQS queue from Lab 6a)
- Verify end-to-end delivery and examine the event envelope
- Explore the Schema Registry and discuss archive/replay + choreography vs orchestration

> This lab assumes the SQS queue `cloudair-$USER_ID-bookings` from Lab 6a still exists.
> That queue becomes a second target, demonstrating how EventBridge fans out to multiple
> consumers independently of SNS.

---

## Prerequisites (3 min)

- Lab 6a complete — SQS queue `cloudair-$USER_ID-bookings` deployed
- `~/.aws-adv-dev.env` exists with `$USER_ID`, `$ACCT`, `$AWS_REGION`, `$QUEUE_ARN`

```bash
source ~/.aws-adv-dev.env
echo "USER_ID=$USER_ID  QUEUE_ARN=$QUEUE_ARN"
```

> **Starting fresh?** `bash ~/environment/aws-adv-dev/bootstrap.sh 6b` recreates the
> SQS queue and sets all required env vars so you can proceed from Step 1.

---

## Step 1 — Create the Custom Event Bus (5 min)

The default `default` event bus receives events from AWS services. A custom bus
isolates your application events and gives you fine-grained control over which
accounts and rules can publish or subscribe.

```bash
source ~/.aws-adv-dev.env

BUS_ARN=$(aws events create-event-bus \
    --name "cloudair-$USER_ID" \
    --query EventBusArn --output text \
    --region $AWS_REGION)

echo "Event bus ARN: $BUS_ARN"
echo "export BUS_ARN=$BUS_ARN" >> ~/.aws-adv-dev.env
```

Open the EventBridge console → **Event buses** and confirm `cloudair-$USER_ID`
appears alongside the `default` and `aws.partner` buses.

---

## Step 2 — Grant the Queue Permission to Receive Events (5 min)

EventBridge needs `sqs:SendMessage` permission on the target queue, just as SNS
did in Lab 6a. The condition locks delivery to events originating from your bus only.

```bash
source ~/.aws-adv-dev.env

aws sqs set-queue-attributes \
    --queue-url $QUEUE_URL \
    --attributes "{
        \"Policy\": \"{
            \\\"Version\\\": \\\"2012-10-17\\\",
            \\\"Statement\\\": [
                {
                    \\\"Sid\\\": \\\"AllowSNS\\\",
                    \\\"Effect\\\": \\\"Allow\\\",
                    \\\"Principal\\\": {\\\"Service\\\": \\\"sns.amazonaws.com\\\"},
                    \\\"Action\\\": \\\"sqs:SendMessage\\\",
                    \\\"Resource\\\": \\\"$QUEUE_ARN\\\",
                    \\\"Condition\\\": {\\\"ArnEquals\\\": {\\\"aws:SourceArn\\\": \\\"$TOPIC_ARN\\\"}}
                },
                {
                    \\\"Sid\\\": \\\"AllowEventBridge\\\",
                    \\\"Effect\\\": \\\"Allow\\\",
                    \\\"Principal\\\": {\\\"Service\\\": \\\"events.amazonaws.com\\\"},
                    \\\"Action\\\": \\\"sqs:SendMessage\\\",
                    \\\"Resource\\\": \\\"$QUEUE_ARN\\\",
                    \\\"Condition\\\": {\\\"ArnEquals\\\": {\\\"aws:SourceArn\\\": \\\"$BUS_ARN\\\"}}
                }
            ]
        }\"
    }" \
    --region $AWS_REGION
```

> This merges the SNS and EventBridge permissions into a single queue policy.
> SQS allows only one policy document per queue — any `set-queue-attributes` call
> with a `Policy` key **replaces** the existing policy entirely.

---

## Step 3 — Create the Event Rule (8 min)

An EventBridge rule evaluates every event on the bus and routes matching ones to
targets. The pattern file at `~/environment/aws-adv-dev/lab6/event-pattern.json`
matches events where `source` is `cloudair.bookings` and `detail-type` is
`BookingCreated`.

Review the pattern:

```bash
cat ~/environment/aws-adv-dev/lab6/event-pattern.json
```

Create the rule:

```bash
source ~/.aws-adv-dev.env

RULE_ARN=$(aws events put-rule \
    --name "cloudair-$USER_ID-booking-created" \
    --event-bus-name "cloudair-$USER_ID" \
    --event-pattern file://~/environment/aws-adv-dev/lab6/event-pattern.json \
    --state ENABLED \
    --description "Route BookingCreated events to the bookings SQS queue" \
    --query RuleArn --output text \
    --region $AWS_REGION)

echo "Rule ARN: $RULE_ARN"
echo "export RULE_ARN=$RULE_ARN" >> ~/.aws-adv-dev.env
```

---

## Step 4 — Add the SQS Queue as a Target (7 min)

```bash
source ~/.aws-adv-dev.env

aws events put-targets \
    --rule "cloudair-$USER_ID-booking-created" \
    --event-bus-name "cloudair-$USER_ID" \
    --targets "[{
        \"Id\": \"BookingQueueTarget\",
        \"Arn\": \"$QUEUE_ARN\"
    }]" \
    --region $AWS_REGION
```

A rule can have up to five targets. Each target can also apply an **input
transformer** to reshape the event before delivery — useful when a downstream
service expects a different JSON structure.

In the Console, navigate to **EventBridge → Rules → cloudair-$USER_ID-booking-created**
and confirm the `cloudair-$USER_ID-bookings` SQS queue is listed under **Targets**.

---

## Step 5 — Publish a BookingCreated Event (7 min)

Use the helper script at `~/environment/aws-adv-dev/lab6/put_event.py`:

```bash
source ~/.aws-adv-dev.env
cd ~/environment/aws-adv-dev/lab6

python3 put_event.py "cloudair-$USER_ID" "BK-$(date +%s)" $USER_ID
```

Open `put_event.py` in the editor. Notice:

- `Source` is `cloudair.bookings` — matches the rule pattern exactly
- `DetailType` is `BookingCreated`
- `EventBusName` targets your custom bus, not the `default` bus

Alternatively, send the same event via the CLI:

```bash
source ~/.aws-adv-dev.env

aws events put-events \
    --entries "[{
        \"Source\": \"cloudair.bookings\",
        \"DetailType\": \"BookingCreated\",
        \"Detail\": \"{\\\"bookingId\\\":\\\"BK-CLI-001\\\",\\\"userId\\\":\\\"$USER_ID\\\",\\\"flightId\\\":\\\"CA-2501\\\",\\\"status\\\":\\\"CONFIRMED\\\"}\",
        \"EventBusName\": \"cloudair-$USER_ID\"
    }]" \
    --region $AWS_REGION
```

A `FailedEntryCount` of `0` in the response means the event was accepted.

---

## Step 6 — Verify Target Invocation (5 min)

Check that the SQS queue received the event:

```bash
source ~/.aws-adv-dev.env

aws sqs get-queue-attributes \
    --queue-url $QUEUE_URL \
    --attribute-names ApproximateNumberOfMessages \
    --query "Attributes.ApproximateNumberOfMessages" \
    --output text \
    --region $AWS_REGION
```

Peek at a message to compare the EventBridge envelope to the SNS envelope from Lab 6a:

```bash
aws sqs receive-message \
    --queue-url $QUEUE_URL \
    --max-number-of-messages 1 \
    --visibility-timeout 0 \
    --region $AWS_REGION | python3 -m json.tool
```

Key differences from the SNS envelope:
- No outer `Type: Notification` wrapper
- `source`, `detail-type`, `detail`, `time`, and `id` are top-level fields
- `id` is an EventBridge-assigned UUID — useful for correlating logs

---

## Step 7 — Explore Schema Registry and Archive/Replay (5 min)

**Schema Registry (Console only):**

1. EventBridge console → **Schemas → Discovered schemas**
2. If schema discovery is not yet enabled on your bus, click **Discover schemas**
   and enable it on `cloudair-$USER_ID`
3. After Step 5 put-events, a schema for `cloudair.bookings@BookingCreated` should
   appear within ~60 seconds
4. Click it — EventBridge inferred the JSON shape; you can download a language binding

**Archive:**

```bash
source ~/.aws-adv-dev.env

aws events create-archive \
    --archive-name "cloudair-$USER_ID-archive" \
    --event-source-arn $BUS_ARN \
    --event-pattern file://~/environment/aws-adv-dev/lab6/event-pattern.json \
    --retention-days 7 \
    --region $AWS_REGION
```

An archive lets you replay historical events into any bus — invaluable for
re-running a downstream consumer after a bug fix without re-publishing from
the source application.

---

## Discussion

**Choreography vs Orchestration:** In Lab 5b you used Step Functions to
*orchestrate* the booking flow — one central state machine knew every step.
EventBridge implements *choreography*: the booking service fires an event and
walks away; any number of services subscribe independently. Neither pattern is
universally superior — orchestration gives you a single place to observe and
debug; choreography gives you loose coupling and independent scalability.

**Custom bus vs default bus:** Mixing application events with AWS service events
on the `default` bus creates noise and makes rule management harder. Custom buses
also support resource-based policies for cross-account delivery — a pattern used
in enterprise event meshes.

**Input Transformers:** EventBridge can reshape the event JSON before it reaches
a target. For example, you could extract only `detail.bookingId` and send a
minimal payload to an SQS queue consumed by a legacy system that expects a flat
JSON string.

**EventBridge Pipes (advanced):** Pipes connect a source (SQS, DynamoDB Streams,
Kinesis) to a target with optional filtering and enrichment Lambda in between —
all without custom consumer code.

---

## Success Criteria (3 min)

- ✅ Custom event bus `cloudair-$USER_ID` exists in EventBridge
- ✅ Rule `cloudair-$USER_ID-booking-created` matches `source=cloudair.bookings` + `detail-type=BookingCreated`
- ✅ SQS queue `cloudair-$USER_ID-bookings` is a target of the rule
- ✅ `put_event.py` published a `BookingCreated` event with `FailedEntryCount=0`
- ✅ SQS queue contains at least one EventBridge-originated message
- ✅ EventBridge envelope inspected and compared to the SNS envelope from Lab 6a
- ✅ Archive `cloudair-$USER_ID-archive` created on the custom bus
