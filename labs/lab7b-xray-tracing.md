# 🧪 Lab 7b — Observe Cloud Air with AWS X-Ray

*Hands-On Lab · 50 min · SDK + SAM · Day 3 — Security & Observability*

## Objectives (3 min)

- Enable X-Ray active tracing on the Flights Lambda and HTTP API via the SAM template
- Instrument boto3 calls using the `aws_xray_sdk` with `patch_all()`
- Add annotations (indexed, filterable) and metadata to traces
- Generate load and read the X-Ray service map and trace timeline
- Perform end-of-course teardown: delete all Lab 2–7 resources

> This lab is the final hands-on exercise. The Cleanup section at the end removes
> every resource created across all three days so the shared account stays clean.

---

## Prerequisites (3 min)

- Labs 4a–7a complete — `cloudair-$USER_ID-flights` stack deployed with Cognito JWT authorizer
- `~/.aws-adv-dev.env` exists with `$USER_ID`, `$ACCT`, `$AWS_REGION`, `$API_URL`, `$ID_TOKEN`
- **Python 3.12 installed** (Lab 1a Step 5) — the Flights function runs on the `python3.12` runtime, so the `sam build` in Step 4 needs `python3.12` on `PATH`. Verify with `python3.12 --version`; if missing, `sudo dnf install -y python3.12`.

```bash
source ~/.aws-adv-dev.env
echo "USER_ID=$USER_ID  API_URL=$API_URL"
```

> **Starting fresh?** `bash ~/environment/aws-adv-dev/bootstrap.sh 7b` deploys the full
> Flights + Cognito stack, seeds a valid `$ID_TOKEN`, and exports all required variables
> so you can instrument and generate traffic immediately.

---

## Step 1 — Add the X-Ray SDK to the Package (5 min)

```bash
source ~/.aws-adv-dev.env
cd ~/environment/aws-adv-dev/lab4/src

# Vendor the SDK into the deployment package directory.
# Use pip3 — Cloud9 AL2023 has no unversioned `pip`. The -t (target) install
# goes into ./ and is not PEP 668-managed, so no --break-system-packages needed.
pip3 install aws-xray-sdk -t .
```

Verify the SDK installed:

```bash
ls ~/environment/aws-adv-dev/lab4/src | grep xray
```

You should see the `aws_xray_sdk/` directory alongside your `app.py`.

---

## Step 2 — Swap in the Instrumented Handler (7 min)

The instrumented handler is at `~/environment/aws-adv-dev/lab7/xray_handler.py`.
Copy it over the existing `app.py`:

```bash
cp ~/environment/aws-adv-dev/lab7/xray_handler.py \
   ~/environment/aws-adv-dev/lab4/src/app.py
```

Open `~/environment/aws-adv-dev/lab4/src/app.py` in the Cloud9 editor and review
the three instrumentation primitives:

| Primitive | Effect in X-Ray |
|-----------|-----------------|
| `patch_all()` | Wraps every boto3 call as an automatic subsegment |
| `@xray_recorder.capture("get_flights")` | Creates a named span for the function |
| `xray_recorder.put_annotation(key, value)` | Indexed — filterable from the console |
| `xray_recorder.put_metadata(key, value)` | Not indexed — visible when you open a trace |

`patch_all()` must be called **before** any boto3 client is instantiated. The handler
imports it at module scope so it runs once per container, not once per invocation.

---

## Step 3 — Enable Active Tracing in the SAM Template (8 min)

Active tracing tells the Lambda service to emit trace segments to X-Ray for every
invocation. With HTTP API (API Gateway v2), X-Ray tracing is instrumented at the
Lambda level — the API Gateway layer itself does not emit a trace segment for HTTP
APIs (only REST APIs / API Gateway v1 support that). The trace therefore starts at
the Lambda function and flows to downstream services such as DynamoDB.

Open `~/environment/aws-adv-dev/lab4/template.yaml` in the editor and confirm (or add)
the following in `Globals`:

```yaml
Globals:
  Function:
    Runtime: python3.12
    Architectures: [arm64]
    Timeout: 15
    Tracing: Active          # <-- ensure this line is present
    Environment:
      Variables:
        BOOKINGS_TABLE: !Ref BookingsTableName
        POWERTOOLS_SERVICE_NAME: !Sub "cloudair-${UserId}-flights"
        LOG_LEVEL: INFO
```

> **Note:** `AWS::Serverless::HttpApi` (API Gateway v2 HTTP API) does **not** support
> a `TracingConfig` property — that property is only available on `AWS::Serverless::Api`
> (REST APIs). Do not add `TracingConfig` to `FlightsApi`. The `Tracing: Active` setting
> under `Globals.Function` is sufficient; it causes every Lambda invocation to emit a
> trace segment to X-Ray.

Grant the Lambda execution role permission to write to X-Ray:

```bash
source ~/.aws-adv-dev.env

# The role name is set by the SAM stack; find it from the function config
ROLE_NAME=$(aws lambda get-function-configuration \
    --function-name "cloudair-$USER_ID-flights" \
    --query "Role" --output text --region $AWS_REGION | \
    sed 's|.*/||')

aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess
```

---

## Step 4 — Redeploy with SAM (5 min)

```bash
source ~/.aws-adv-dev.env
cd ~/environment/aws-adv-dev/lab4

# Force a clean rebuild so the instrumented app.py is in the built template.
# A leftover .aws-sam cache can make SAM report "No changes to deploy".
rm -rf .aws-sam
sam build

sam deploy \
    --stack-name "cloudair-$USER_ID-flights" \
    --parameter-overrides \
        "UserId=$USER_ID" \
        "BookingsTableName=Bookings-$USER_ID" \
        "PoolId=$POOL_ID" \
        "AppClientId=$CLIENT_ID" \
    --no-confirm-changeset \
    --region $AWS_REGION
```

Confirm the function is using the updated code:

```bash
source ~/.aws-adv-dev.env
aws lambda get-function-configuration \
    --function-name "cloudair-$USER_ID-flights" \
    --query "[TracingConfig.Mode, LastModified]" \
    --output table --region $AWS_REGION
```

`TracingConfig.Mode` should be `Active`.

---

## Step 5 — Generate Load (5 min)

Send 25 authenticated requests to produce enough traces to populate the service map:

```bash
source ~/.aws-adv-dev.env

for i in $(seq 1 25); do
    curl -s -o /dev/null \
         -H "Authorization: $ID_TOKEN" \
         "$API_URL/flights"
done
echo "25 requests sent"
```

Send a couple of unauthenticated requests too — they will appear as `401` traces
on the API Gateway node, demonstrating how authorizer rejections are captured:

```bash
source ~/.aws-adv-dev.env
for i in 1 2 3; do
    curl -s -o /dev/null "$API_URL/flights"
done
```

---

## Step 6 — Read the Service Map and Traces (7 min)

1. Open the **CloudWatch** console → left nav → **X-Ray traces** → **Service map**
2. Wait 30–60 seconds after the requests for data to appear
3. Verify the graph shows: **Lambda → DynamoDB** (the trace originates at the Lambda
   function — HTTP API / API Gateway v2 does not emit its own trace segment, so there
   is no separate "API Gateway" node in the service map)
4. Click the **Lambda** node → observe the response-time histogram (p50/p99)
5. Click **View traces** → select any trace
6. In the trace timeline, expand the Lambda segment → find the `get_flights` subsegment
7. Click the DynamoDB subsegment — see the table name, operation, and latency

**Filter by annotation:**

In the X-Ray console **Traces** view, enter this filter expression:

```
annotation.tableName = "Bookings-<YOUR_USER_ID>"
```

(Replace `<YOUR_USER_ID>` with your actual value, e.g. `Bookings-user3`)

Only traces where your handler put that annotation are returned. This is the power
of indexed annotations vs unindexed metadata.

---

## Step 7 — View SAM Logs (2 min)

```bash
source ~/.aws-adv-dev.env

sam logs \
    --name FlightsFn \
    --stack-name "cloudair-$USER_ID-flights" \
    --tail \
    --region $AWS_REGION
```

Press `Ctrl+C` to stop tailing. Notice the Lambda log lines interleaved with the
X-Ray trace IDs (`_X_AMZN_TRACE_ID` in the environment). You can correlate a
CloudWatch log entry to its X-Ray trace using that ID.

---

## Cleanup — Remove All Course Resources (5 min)

This section deletes every resource created during the three-day course. Run these
commands in order; some depend on earlier ones completing first.

### Delete the Flights stack

```bash
source ~/.aws-adv-dev.env

# Use aws cloudformation delete-stack (not `sam delete`) so teardown does not
# depend on samconfig.toml or the SAM-managed artifact bucket being present —
# delete-stack reliably removes the Lambda, HTTP API, and Cognito authorizer.
aws cloudformation delete-stack \
    --stack-name "cloudair-$USER_ID-flights" \
    --region $AWS_REGION

aws cloudformation wait stack-delete-complete \
    --stack-name "cloudair-$USER_ID-flights" \
    --region $AWS_REGION
echo "Flights stack deleted."
```

### Delete Cognito user pool

```bash
source ~/.aws-adv-dev.env

# Delete the app client first, then the pool
aws cognito-idp delete-user-pool-client \
    --user-pool-id $POOL_ID \
    --client-id $CLIENT_ID \
    --region $AWS_REGION

aws cognito-idp delete-user-pool \
    --user-pool-id $POOL_ID \
    --region $AWS_REGION
```

### Delete EventBridge resources

```bash
source ~/.aws-adv-dev.env

# Remove targets before deleting the rule
aws events remove-targets \
    --rule "cloudair-$USER_ID-booking-created" \
    --event-bus-name "cloudair-$USER_ID" \
    --ids BookingQueueTarget \
    --region $AWS_REGION

aws events delete-rule \
    --name "cloudair-$USER_ID-booking-created" \
    --event-bus-name "cloudair-$USER_ID" \
    --region $AWS_REGION

# If you enabled Schema Discovery on the bus, EventBridge created a Schemas
# *discoverer* and a service-managed rule named "Schemas-events-event-bus-…".
# A managed rule cannot be removed with delete-rule and will block delete-event-bus.
# Delete the discoverer first — that removes its managed rule automatically.
BUS_ARN="arn:aws:events:$AWS_REGION:$ACCT:event-bus/cloudair-$USER_ID"
for D in $(aws schemas list-discoverers --region $AWS_REGION \
            --query "Discoverers[?SourceArn=='$BUS_ARN'].DiscovererId" --output text); do
    aws schemas delete-discoverer --discoverer-id "$D" --region $AWS_REGION
done

# Belt-and-suspenders: force-delete any rule still attached to the bus
# (handles the managed Schemas rule if the discoverer was already gone).
for R in $(aws events list-rules --event-bus-name "cloudair-$USER_ID" \
            --region $AWS_REGION --query "Rules[].Name" --output text); do
    aws events delete-rule --name "$R" --event-bus-name "cloudair-$USER_ID" \
        --force --region $AWS_REGION
done

aws events delete-archive \
    --archive-name "cloudair-$USER_ID-archive" \
    --region $AWS_REGION

aws events delete-event-bus \
    --name "cloudair-$USER_ID" \
    --region $AWS_REGION
```

> **Why the extra steps?** Lab 6b's optional "Discover schemas" action turns on
> Schema Discovery for the bus, which silently adds a managed rule. You can't
> delete an event bus while any rule remains, and a *managed* rule rejects a plain
> `delete-rule`. Deleting the discoverer (or `delete-rule --force`) clears it.

### Delete SQS queues and SNS topic

```bash
source ~/.aws-adv-dev.env

aws sqs delete-queue --queue-url $QUEUE_URL --region $AWS_REGION
aws sqs delete-queue --queue-url $DLQ_URL   --region $AWS_REGION

aws sns unsubscribe --subscription-arn $SUBSCRIPTION_ARN --region $AWS_REGION
aws sns delete-topic --topic-arn $TOPIC_ARN --region $AWS_REGION
```

### Delete worker Lambda and DynamoDB tables

```bash
source ~/.aws-adv-dev.env

aws lambda delete-function \
    --function-name "cloudair-$USER_ID-worker" \
    --region $AWS_REGION

aws dynamodb delete-table \
    --table-name "ProcessedBookings-$USER_ID" \
    --region $AWS_REGION

# Lab 5a single-table (CloudAir-$USER_ID)
aws dynamodb delete-table \
    --table-name "CloudAir-$USER_ID" \
    --region $AWS_REGION 2>/dev/null || true
```

### Delete worker IAM role (Lab 6a)

```bash
source ~/.aws-adv-dev.env

# Detach managed policies before deleting the role
aws iam detach-role-policy \
    --role-name "CloudAirWorkerRole-$USER_ID" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaSQSQueueExecutionRole \
    2>/dev/null || true

aws iam detach-role-policy \
    --role-name "CloudAirWorkerRole-$USER_ID" \
    --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess \
    2>/dev/null || true

aws iam delete-role \
    --role-name "CloudAirWorkerRole-$USER_ID" \
    2>/dev/null || true
```

### Delete Secrets Manager secret (Lab 3b)

```bash
source ~/.aws-adv-dev.env

aws secretsmanager delete-secret \
    --secret-id "cloudair/$USER_ID/db" \
    --force-delete-without-recovery \
    --region $AWS_REGION 2>/dev/null || true
```

### Delete extra SSM parameters (Lab 3a)

```bash
source ~/.aws-adv-dev.env

# Delete parameters under /cloudair/$USER_ID/ that were added by Lab 3a
# (base-stack parameters under this path are removed when the base CloudFormation
# stack is deleted in the next step — these commands handle any extras)
PARAM_NAMES=$(aws ssm get-parameters-by-path \
    --path "/cloudair/$USER_ID" \
    --query "Parameters[].Name" \
    --output text \
    --region $AWS_REGION 2>/dev/null)

if [ -n "$PARAM_NAMES" ]; then
    aws ssm delete-parameters \
        --names $PARAM_NAMES \
        --region $AWS_REGION 2>/dev/null || true
fi
```

### Delete the booking saga SAM stack (Lab 5b)

```bash
source ~/.aws-adv-dev.env

# Delete the saga stack — removes the state machine, all 4 Lambda stubs, and the
# IAM role. delete-stack (not `sam delete`) for the same reliability reason as above.
aws cloudformation delete-stack \
    --stack-name "cloudair-$USER_ID-saga" \
    --region $AWS_REGION

aws cloudformation wait stack-delete-complete \
    --stack-name "cloudair-$USER_ID-saga" \
    --region $AWS_REGION
echo "Saga stack deleted."
```

### Delete the CloudFormation base stack (Lab 2a) and Elastic Beanstalk environment (Lab 2b)

```bash
source ~/.aws-adv-dev.env

# Elastic Beanstalk — terminate environment first, then delete application
aws elasticbeanstalk terminate-environment \
    --environment-name "cloudair-$USER_ID-env" \
    --region $AWS_REGION 2>/dev/null || true

# Wait for termination before deleting the application (~3 min)
echo "Waiting for EB environment termination (this takes ~3 minutes)..."
aws elasticbeanstalk wait environment-terminated \
    --environment-names "cloudair-$USER_ID-env" \
    --region $AWS_REGION 2>/dev/null || true

aws elasticbeanstalk delete-application \
    --application-name "cloudair-$USER_ID" \
    --terminate-env-by-force \
    --region $AWS_REGION 2>/dev/null || true

# CloudFormation base stack — this deletes S3, DynamoDB, and SSM parameters
aws cloudformation delete-stack \
    --stack-name "cloudair-$USER_ID-base" \
    --region $AWS_REGION

aws cloudformation wait stack-delete-complete \
    --stack-name "cloudair-$USER_ID-base" \
    --region $AWS_REGION
echo "Base stack deleted."
```

### Final verification

```bash
source ~/.aws-adv-dev.env

echo "=== Remaining CloudFormation stacks ==="
aws cloudformation list-stacks \
    --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
    --query "StackSummaries[?contains(StackName,\`$USER_ID\`)].StackName" \
    --output text --region $AWS_REGION

echo "=== Remaining Lambda functions ==="
aws lambda list-functions \
    --query "Functions[?contains(FunctionName,\`$USER_ID\`)].FunctionName" \
    --output text --region $AWS_REGION

echo "=== Remaining DynamoDB tables ==="
aws dynamodb list-tables \
    --query "TableNames[?contains(@,\`$USER_ID\`)]" \
    --output text --region $AWS_REGION
```

All three queries should return empty output. Well done — Cloud Air is fully deployed,
observed, secured, and cleaned up.

---

## Discussion

**X-Ray sampling:** By default, X-Ray samples 1 request per second per host plus 5%
of additional requests. For low-traffic APIs this means near-100% sampling. In
production, custom sampling rules let you sample 100% of errors and a configurable
fraction of healthy requests to manage cost.

**Annotations vs Metadata:** Annotations are indexed by X-Ray and support filter
expressions in the console and API. Metadata is stored in the trace document but
not indexed — use it for large payloads (full request bodies, DynamoDB responses)
you want to inspect on specific traces but never query across all traces.

**Service map vs Traces:** The service map is an aggregated view — one node per
unique service, with latency and error rate statistics. The Traces view gives you
individual request timelines. Start with the service map to identify bottlenecks,
then drill into individual traces to understand root cause.

**CloudWatch ServiceLens:** The ServiceLens page in CloudWatch stitches together
the X-Ray service map with CloudWatch metrics and logs into a single pane. It also
surfaces Contributor Insights anomaly detection on the same view.

---

## Success Criteria (3 min)

- ✅ `aws-xray-sdk` installed into `lab4/src/` and `app.py` uses `patch_all()` + annotations
- ✅ SAM template has `Tracing: Active` under `Globals.Function` (no API-level TracingConfig needed for HTTP API)
- ✅ `AWSXRayDaemonWriteAccess` attached to the Flights Lambda execution role
- ✅ 25 authenticated requests generated and visible in X-Ray traces
- ✅ Service map shows Lambda → DynamoDB topology (trace originates at Lambda for HTTP API)
- ✅ At least one annotation filter query returned matching traces
- ✅ All course resources deleted — SAM stacks (flights + saga), Cognito pool, EventBridge bus, SQS/SNS, Lambda worker, DynamoDB tables, EB environment, and base CloudFormation stack
