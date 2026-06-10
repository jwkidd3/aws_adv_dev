# 🧪 Lab 6a — Resilience & Scale: Decouple with SQS + SNS

*Hands-On Lab · 50 min · SDK + CLI · Day 3 — Resilience & Event-Driven Decoupling*

## Objectives (3 min)

- Create an SNS topic and an SQS queue (with a DLQ) using the AWS CLI and boto3
- Subscribe the SQS queue to the SNS topic to create a fan-out channel
- Publish a `BookingCreated` message to SNS and consume it from SQS
- Force a poison message into the DLQ by exceeding the max-receive-count
- Discuss at-least-once delivery semantics and idempotency design

> Lab 6b (EventBridge) builds on the same booking-event concept. Keep all resources
> alive until the end of Day 3.

---

## Prerequisites (3 min)

- Labs 1a–4b complete; `cloudair-$USER_ID-flights` Lambda and SAM stack deployed
- `~/.aws-adv-dev.env` exists with `$USER_ID`, `$ACCT`, and `$AWS_REGION`

```bash
source ~/.aws-adv-dev.env
echo "USER_ID=$USER_ID  ACCT=$ACCT  REGION=$AWS_REGION"
```

> **Starting fresh?** `bash ~/environment/aws-adv-dev/bootstrap.sh 6a` restores
> the env file and verifies the repo is present so you can proceed from Step 1.

---

## Step 1 — Create the DLQ (5 min)

A dead-letter queue receives messages that fail processing after `maxReceiveCount`
attempts. Create it first so you can reference its ARN when creating the main queue.

```bash
source ~/.aws-adv-dev.env

DLQ_URL=$(aws sqs create-queue \
    --queue-name "cloudair-$USER_ID-bookings-dlq" \
    --attributes '{"MessageRetentionPeriod":"1209600"}' \
    --query QueueUrl --output text \
    --region $AWS_REGION)

DLQ_ARN=$(aws sqs get-queue-attributes \
    --queue-url $DLQ_URL \
    --attribute-names QueueArn \
    --query "Attributes.QueueArn" --output text \
    --region $AWS_REGION)

echo "DLQ_URL=$DLQ_URL"
echo "DLQ_ARN=$DLQ_ARN"
echo "export DLQ_URL=$DLQ_URL"   >> ~/.aws-adv-dev.env
echo "export DLQ_ARN=$DLQ_ARN"   >> ~/.aws-adv-dev.env
```

`MessageRetentionPeriod` of 14 days (1 209 600 s) gives you enough time to inspect
and replay failed messages without losing them.

---

## Step 2 — Create the Main Queue (5 min)

Attach the DLQ via a `RedrivePolicy`. `maxReceiveCount: 3` means a message that
is received (but not deleted) three times is moved to the DLQ automatically.

```bash
source ~/.aws-adv-dev.env

QUEUE_URL=$(aws sqs create-queue \
    --queue-name "cloudair-$USER_ID-bookings" \
    --attributes "{
        \"VisibilityTimeout\": \"30\",
        \"MessageRetentionPeriod\": \"86400\",
        \"RedrivePolicy\": \"{\\\"deadLetterTargetArn\\\":\\\"$DLQ_ARN\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"
    }" \
    --query QueueUrl --output text \
    --region $AWS_REGION)

QUEUE_ARN=$(aws sqs get-queue-attributes \
    --queue-url $QUEUE_URL \
    --attribute-names QueueArn \
    --query "Attributes.QueueArn" --output text \
    --region $AWS_REGION)

echo "QUEUE_URL=$QUEUE_URL"
echo "export QUEUE_URL=$QUEUE_URL" >> ~/.aws-adv-dev.env
echo "export QUEUE_ARN=$QUEUE_ARN" >> ~/.aws-adv-dev.env
```

---

## Step 3 — Create the SNS Topic and Subscribe the Queue (8 min)

```bash
source ~/.aws-adv-dev.env

# Create the topic
TOPIC_ARN=$(aws sns create-topic \
    --name "cloudair-$USER_ID-bookings" \
    --query TopicArn --output text \
    --region $AWS_REGION)

echo "export TOPIC_ARN=$TOPIC_ARN" >> ~/.aws-adv-dev.env
echo "TOPIC_ARN=$TOPIC_ARN"

# Subscribe the SQS queue to the topic
SUBSCRIPTION_ARN=$(aws sns subscribe \
    --topic-arn $TOPIC_ARN \
    --protocol sqs \
    --notification-endpoint $QUEUE_ARN \
    --query SubscriptionArn --output text \
    --region $AWS_REGION)

echo "Subscription: $SUBSCRIPTION_ARN"
```

SNS must be permitted to write to the SQS queue. Apply the resource-based policy:

```bash
source ~/.aws-adv-dev.env

aws sqs set-queue-attributes \
    --queue-url $QUEUE_URL \
    --attributes "{
        \"Policy\": \"{
            \\\"Version\\\": \\\"2012-10-17\\\",
            \\\"Statement\\\": [{
                \\\"Effect\\\": \\\"Allow\\\",
                \\\"Principal\\\": {\\\"Service\\\": \\\"sns.amazonaws.com\\\"},
                \\\"Action\\\": \\\"sqs:SendMessage\\\",
                \\\"Resource\\\": \\\"$QUEUE_ARN\\\",
                \\\"Condition\\\": {
                    \\\"ArnEquals\\\": {\\\"aws:SourceArn\\\": \\\"$TOPIC_ARN\\\"}
                }
            }]
        }\"
    }" \
    --region $AWS_REGION
```

> SQS resource policies are JSON strings embedded inside the `--attributes`
> JSON — the inner quotes need to be escaped. If the inline escaping is hard to
> read, write the policy to a file and use `file://` instead.

---

## Step 4 — Publish a Booking Message (7 min)

Use the helper script at `~/environment/aws-adv-dev/lab6/publish_booking.py`:

```bash
source ~/.aws-adv-dev.env
cd ~/environment/aws-adv-dev/lab6

python publish_booking.py $TOPIC_ARN "BK-$(date +%s)" $USER_ID
```

Open the file in the Cloud9 editor and review:

- `sns.publish()` sends to the topic ARN — SNS fans out to all subscribers
- `MessageAttributes` lets downstream consumers filter without reading the body
- The payload includes `bookingId`, `userId`, `flightId`, and `status`

Verify the message arrived in the queue:

```bash
source ~/.aws-adv-dev.env

aws sqs get-queue-attributes \
    --queue-url $QUEUE_URL \
    --attribute-names ApproximateNumberOfMessages \
    --query "Attributes.ApproximateNumberOfMessages" \
    --output text \
    --region $AWS_REGION
```

The count should be `1`.

---

## Step 5 — Consume (Receive + Delete) the Message (7 min)

Receiving a message makes it invisible for `VisibilityTimeout` seconds (30 s here).
You must explicitly delete it to acknowledge successful processing.

```bash
source ~/.aws-adv-dev.env

# Receive — returns up to 1 message, waits up to 5 s for one to arrive
MSG=$(aws sqs receive-message \
    --queue-url $QUEUE_URL \
    --max-number-of-messages 1 \
    --wait-time-seconds 5 \
    --region $AWS_REGION)

echo $MSG | python3 -m json.tool

RECEIPT=$(echo $MSG | python3 -c "
import json,sys
msgs = json.load(sys.stdin).get('Messages',[])
print(msgs[0]['ReceiptHandle'] if msgs else '')
")

# Delete the message to acknowledge processing
if [ -n "$RECEIPT" ]; then
    aws sqs delete-message \
        --queue-url $QUEUE_URL \
        --receipt-handle "$RECEIPT" \
        --region $AWS_REGION
    echo "Message deleted (acknowledged)"
else
    echo "No message received"
fi
```

Inspect the message body — notice it is a JSON envelope from SNS containing a
`Message` field with the actual booking payload.

---

## Step 6 — Deploy the Worker Lambda (8 min)

The worker at `~/environment/aws-adv-dev/lab6/worker.py` processes booking messages
with an idempotency guard backed by a DynamoDB table.

**Create the idempotency table:**

```bash
source ~/.aws-adv-dev.env

aws dynamodb create-table \
    --table-name "ProcessedBookings-$USER_ID" \
    --attribute-definitions AttributeName=bookingId,AttributeType=S \
    --key-schema AttributeName=bookingId,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region $AWS_REGION

aws dynamodb wait table-exists \
    --table-name "ProcessedBookings-$USER_ID" \
    --region $AWS_REGION
```

**Package and deploy the worker function:**

```bash
source ~/.aws-adv-dev.env
cd ~/environment/aws-adv-dev/lab6

zip worker.zip worker.py

# Create the execution role (if it doesn't already exist from a prior lab)
ROLE_ARN=$(aws iam get-role \
    --role-name "CloudAirWorkerRole-$USER_ID" \
    --query "Role.Arn" --output text 2>/dev/null || \
  aws iam create-role \
    --role-name "CloudAirWorkerRole-$USER_ID" \
    --assume-role-policy-document '{
        "Version":"2012-10-17",
        "Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},
                      "Action":"sts:AssumeRole"}]}' \
    --query "Role.Arn" --output text)

aws iam attach-role-policy \
    --role-name "CloudAirWorkerRole-$USER_ID" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaSQSQueueExecutionRole

aws iam attach-role-policy \
    --role-name "CloudAirWorkerRole-$USER_ID" \
    --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess

# Wait for IAM propagation
sleep 10

WORKER_ARN=$(aws lambda create-function \
    --function-name "cloudair-$USER_ID-worker" \
    --runtime python3.12 \
    --role $ROLE_ARN \
    --handler worker.handler \
    --zip-file fileb://worker.zip \
    --environment "Variables={PROCESSED_TABLE=ProcessedBookings-$USER_ID}" \
    --timeout 30 \
    --query FunctionArn --output text \
    --region $AWS_REGION)

aws lambda wait function-active \
    --function-name "cloudair-$USER_ID-worker" \
    --region $AWS_REGION

echo "Worker ARN: $WORKER_ARN"
echo "export WORKER_ARN=$WORKER_ARN" >> ~/.aws-adv-dev.env
```

**Wire the SQS queue as the Lambda event source:**

```bash
source ~/.aws-adv-dev.env

aws lambda create-event-source-mapping \
    --function-name "cloudair-$USER_ID-worker" \
    --event-source-arn $QUEUE_ARN \
    --batch-size 5 \
    --region $AWS_REGION
```

---

## Step 7 — Simulate a Poison Message and Inspect the DLQ (7 min)

The worker raises `ValueError` when the message body contains `"poison": true`.
After three receive attempts SQS routes it to the DLQ.

Publish the poison message directly to the queue (bypassing SNS to keep it simple):

```bash
source ~/.aws-adv-dev.env

aws sqs send-message \
    --queue-url $QUEUE_URL \
    --message-body '{"bookingId":"BK-POISON","userId":"user0","poison":true}' \
    --region $AWS_REGION
```

Watch Lambda attempt and fail — SQS will re-drive to the DLQ after three invocations.
This takes 1–2 minutes. Then confirm the poison message landed in the DLQ:

```bash
source ~/.aws-adv-dev.env

aws sqs get-queue-attributes \
    --queue-url $DLQ_URL \
    --attribute-names ApproximateNumberOfMessages \
    --query "Attributes.ApproximateNumberOfMessages" \
    --output text \
    --region $AWS_REGION

# Peek at it without consuming it
aws sqs receive-message \
    --queue-url $DLQ_URL \
    --max-number-of-messages 1 \
    --visibility-timeout 0 \
    --region $AWS_REGION | python3 -m json.tool
```

---

## Discussion

**At-least-once delivery:** SQS guarantees every message is delivered *at least* once.
Under network partitions or Lambda timeouts a message may be re-delivered. Your
`worker.py` guards against this with a conditional DynamoDB write — if `bookingId`
already exists the write is rejected and processing is skipped.

**Idempotency patterns:** This lab uses a DynamoDB idempotency table. Other common
approaches include UUID de-dup in the message envelope (SNS `MessageDeduplicationId`
on FIFO topics) and conditional writes to the target data store.

**Partial batch failure:** With `batch-size 5`, if one record in a batch fails,
Lambda reports the entire batch as failed and all five messages become re-drivable.
The production pattern is to enable `ReportBatchItemFailures` and return
`batchItemFailures` so only the offending records are retried.

**SNS fan-out:** Every new subscriber (email, Lambda, HTTP endpoint, another SQS queue)
added to the topic receives every message without any change to the publisher.
This is the core benefit of the SNS + SQS pattern over point-to-point queues.

---

## Success Criteria (3 min)

- ✅ SQS queue `cloudair-$USER_ID-bookings` exists with a DLQ attached (maxReceiveCount 3)
- ✅ SNS topic `cloudair-$USER_ID-bookings` exists with the SQS queue as a subscriber
- ✅ `publish_booking.py` successfully published a `BookingCreated` message
- ✅ Message received and deleted from the queue via CLI
- ✅ Worker Lambda `cloudair-$USER_ID-worker` deployed with SQS event-source mapping
- ✅ Poison message (`"poison": true`) landed in the DLQ after three failed attempts
- ✅ `ProcessedBookings-$USER_ID` DynamoDB table exists for idempotency tracking
