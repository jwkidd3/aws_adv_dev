# 🧪 Lab 5b — Orchestrating the Booking Saga with Step Functions

*Hands-On Lab · 50 min · Console + CLI · Day 3 — Distributed Orchestration*

---

## Objectives (3 min)

- Read and understand an Amazon States Language (ASL) definition that implements the saga pattern
- Deploy four Lambda stub functions and a Step Functions state machine using SAM
- Execute a **successful** booking flow and trace each state transition in the visual execution graph
- Execute a **failing** booking flow and observe the compensating `CancelReservation` transaction
- Understand the difference between orchestration (Step Functions) and choreography (EventBridge/SNS)

---

## Prerequisites (3 min)

- Lab 5a complete — `CloudAir-$USER_ID` DynamoDB table is active
- `~/.aws-adv-dev.env` sourced; `$USER_ID`, `$ACCT`, `$AWS_REGION` set
- SAM CLI installed in Cloud9 (`sam --version` should print `1.x` or later)

```bash
source ~/.aws-adv-dev.env
echo "USER_ID=$USER_ID  ACCT=$ACCT  REGION=$AWS_REGION"
sam --version
```

> **Starting fresh?** `bash ~/environment/aws-adv-dev/bootstrap.sh 5b` verifies env vars and confirms SAM CLI is available.

---

## Background — The Booking Saga (5 min)

> Read before opening any files.

A **saga** is a sequence of local transactions, each with a corresponding **compensating transaction** that undoes its effect if a later step fails. Unlike a two-phase commit (which holds database locks across services), a saga releases locks immediately after each step and relies on compensating actions to restore consistency.

The Cloud Air booking flow has three forward steps and one compensating step:

```
ReserveSeat  ──►  ChargePayment  ──►  ConfirmBooking  ──►  BookingConfirmed (Succeed)
     │                  │
     │ Catch: ANY        │ Catch: PaymentDeclinedError
     ▼                  ▼
BookingFailed     CancelReservation  ──►  BookingFailed (Fail)
```

**Why Step Functions over a Lambda calling other Lambdas?**

- **Visibility** — every state transition is logged; the visual execution graph shows exactly where a failure occurred without grep-ing CloudWatch logs
- **Retry logic** — `Retry` blocks handle transient Lambda errors (cold start timeouts, throttles) without custom code
- **Error routing** — `Catch` blocks declaratively route to compensation paths; no try/except spaghetti across services
- **Auditability** — execution history is a durable record of every input, output, and error across the entire workflow

---

## Step 1 — Review the ASL Definition (10 min)

> Open `~/environment/aws-adv-dev/lab5/booking-saga.asl.json` in the Cloud9 editor.

Work through each state in order:

| State | Type | On success | On failure |
|---|---|---|---|
| `ReserveSeat` | Task | → `ChargePayment` | → `BookingFailed` (direct, no seat was held) |
| `ChargePayment` | Task | → `ConfirmBooking` | → `CancelReservation` (release the seat hold) |
| `ConfirmBooking` | Task | → `BookingConfirmed` | → `CancelReservation` (payment charged — ideally also refund, but that is Lab 6) |
| `CancelReservation` | Task | → `BookingFailed` | retries 3× before propagating |
| `BookingConfirmed` | Succeed | — | — |
| `BookingFailed` | Fail | — | — |

Key ASL patterns to note:

```json
"ResultPath": "$.reservationResult"
```
`ResultPath` merges the Lambda response back into the execution state object under a named key rather than replacing the whole input. Without this, each Lambda would overwrite the previous step's output.

```json
"Catch": [
  {
    "ErrorEquals": ["States.ALL"],
    "ResultPath": "$.error",
    "Next": "CancelReservation"
  }
]
```
`ErrorEquals` matches the error names a `Catch` (or `Retry`) applies to. **`States.ALL` is a wildcard that must appear alone** — Step Functions rejects a definition that combines it with a specific name (e.g. `["PaymentDeclinedError", "States.ALL"]` fails schema validation). To route a specific error differently from the rest, use **separate `Catch` entries**: list the specific-name entry first (it takes precedence), then a final `["States.ALL"]` entry as the fallback. Here a single `["States.ALL"]` block sends *any* `ChargePayment` failure to the compensating `CancelReservation`.

```json
"Retry": [
  {
    "ErrorEquals": ["Lambda.ServiceException", "Lambda.AWSLambdaException"],
    "IntervalSeconds": 2,
    "MaxAttempts": 2,
    "BackoffRate": 2.0
  }
]
```
This handles transient Lambda infrastructure errors (throttles, cold-start timeouts) with exponential backoff — separate from business-logic errors handled by `Catch`.

---

## Step 2 — Review the Lambda Stubs (5 min)

> Open `~/environment/aws-adv-dev/lab5/handlers.py` in the Cloud9 editor.

Each handler:
- Logs its full input with `logger.info` — visible in CloudWatch Logs
- Returns a structured dict on success — merged into the execution state via `ResultPath`
- Raises a named exception when its own step-specific flag is truthy — Step Functions matches the exception class name against `ErrorEquals`

Each handler checks its own flag independently:
- `reserve_seat` checks `failReserve` — raises `SeatUnavailableError`
- `charge_payment` checks `failPayment` — raises `PaymentDeclinedError`
- `confirm_booking` checks `failConfirm` — raises a generic exception

This means setting `"failPayment": true` in the execution input causes `ReserveSeat` to succeed (it only looks at `failReserve`), then `ChargePayment` raises `PaymentDeclinedError` → `CancelReservation` compensation runs. Setting `"failReserve": true` fails at `ReserveSeat` with no compensation.

The `cancel_reservation` handler is intentionally idempotent — calling it twice with the same `reservationId` produces the same result. This is a saga requirement: compensating transactions must be safe to retry.

> You do not need to modify `handlers.py` for this lab. The step-specific flags in the execution input are sufficient to trigger each compensation path.

---

## Step 3 — Deploy with SAM (10 min)

```bash
source ~/.aws-adv-dev.env
cd ~/environment/aws-adv-dev/lab5

# --use-container builds in the python3.12 Docker image; Cloud9 ships only
# Python 3.9, so a native `sam build` fails the runtime check.
sam build --use-container

sam deploy \
  --stack-name cloudair-$USER_ID-saga \
  --parameter-overrides UserId=$USER_ID \
  --capabilities CAPABILITY_NAMED_IAM \
  --region $AWS_REGION \
  --no-confirm-changeset
```

> SAM packages the Lambda code from `handlers.py`, uploads it to the SAM deployment bucket (created automatically on first deploy), and calls CloudFormation to create the stack.

Wait for `Successfully created/updated stack`. Then capture the state machine ARN:

```bash
STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
  --stack-name cloudair-$USER_ID-saga \
  --query "Stacks[0].Outputs[?OutputKey=='StateMachineArn'].OutputValue" \
  --output text \
  --region $AWS_REGION)

echo "export STATE_MACHINE_ARN=$STATE_MACHINE_ARN" >> ~/.aws-adv-dev.env
source ~/.aws-adv-dev.env
echo "State machine: $STATE_MACHINE_ARN"
```

**Verify in the Console:**

1. Open **Step Functions → State machines** — find `cloudair-$USER_ID-booking-saga`
2. Click the state machine → **Definition** tab — review the visual graph; confirm all six states are visible
3. Open **Lambda → Functions** — confirm four `cloudair-$USER_ID-*` functions exist

---

## Step 4 — Execute the Happy Path (8 min)

Start an execution that succeeds (no `fail` flag):

```bash
source ~/.aws-adv-dev.env

EXECUTION_NAME="happy-$(date +%s)"

aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --name $EXECUTION_NAME \
  --input '{"flightId":"AA101","seatNumber":"14A","customerId":"CUST001","amount":299.00}' \
  --region $AWS_REGION \
  --output json | python3 -c "import sys,json; e=json.load(sys.stdin); print('Execution ARN:', e['executionArn'])"
```

**Inspect in the Console:**

1. **Step Functions → cloudair-$USER_ID-booking-saga → Executions** — click the execution name
2. **Graph view** — each state node turns green as execution proceeds
3. Click the `ConfirmBooking` state node → **Step output** panel — confirm `$.confirmResult.Payload.bookingId` is present
4. **Events** tab — review the full event timeline with timestamps and input/output for each state

**Check the final status from the CLI:**

```bash
EXEC_ARN=$(aws stepfunctions list-executions \
  --state-machine-arn $STATE_MACHINE_ARN \
  --status-filter SUCCEEDED \
  --region $AWS_REGION \
  --query "executions[0].executionArn" \
  --output text)

aws stepfunctions describe-execution \
  --execution-arn $EXEC_ARN \
  --region $AWS_REGION \
  --query "{status:status,start:startDate,stop:stopDate}" \
  --output table
```

Expected: `status = SUCCEEDED`.

---

## Step 5 — Execute the Failure Path (8 min)

Trigger a `PaymentDeclinedError` by setting `"failPayment": true` in the execution input. Each handler checks its own step-specific flag, so `ReserveSeat` (which checks `failReserve`) succeeds, then `ChargePayment` (which checks `failPayment`) raises `PaymentDeclinedError`. The state machine routes to `CancelReservation` (compensating transaction), then ends at `BookingFailed`.

```bash
source ~/.aws-adv-dev.env

FAIL_NAME="payment-fail-$(date +%s)"

aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --name $FAIL_NAME \
  --input '{"flightId":"AA101","seatNumber":"14A","customerId":"CUST001","amount":299.00,"failPayment":true}' \
  --region $AWS_REGION \
  --output json | python3 -c "import sys,json; e=json.load(sys.stdin); print('Execution ARN:', e['executionArn'])"
```

> `failPayment: true` is seen only by `ChargePayment` (which checks `event.get("failPayment")`); `ReserveSeat` checks `failReserve` and ignores it, so the seat is reserved successfully before the payment step raises `PaymentDeclinedError`.

**Inspect the compensation path in the Console:**

1. Open the new execution in **Step Functions**
2. **Graph view** — `ReserveSeat` is green, `ChargePayment` is red, `CancelReservation` is green, `BookingFailed` is the terminal state
3. Click the `ChargePayment` node → **Exception** tab — confirm `PaymentDeclinedError`
4. Click `CancelReservation` → **Step output** — confirm `$.cancelResult.Payload.status = "CANCELLED"`
5. Note that `ConfirmBooking` was never invoked — Step Functions short-circuited to the Catch handler

**Also trigger a ReserveSeat failure** (no compensation needed — no seat was held):

```bash
aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --name "reserve-fail-$(date +%s)" \
  --input '{"flightId":"DL305","seatNumber":"22C","customerId":"CUST001","amount":279.00,"failReserve":true}' \
  --region $AWS_REGION > /dev/null

# After ~5 seconds:
aws stepfunctions list-executions \
  --state-machine-arn $STATE_MACHINE_ARN \
  --status-filter FAILED \
  --region $AWS_REGION \
  --query "executions[*].{name:name,status:status}" \
  --output table
```

Observe that the execution ends directly at `BookingFailed` without invoking `CancelReservation` — there was nothing to compensate because `ReserveSeat` failed before creating a hold.

---

## Step 6 — Execution History and CloudWatch Logs (3 min)

```bash
source ~/.aws-adv-dev.env

# List all executions with their status
aws stepfunctions list-executions \
  --state-machine-arn $STATE_MACHINE_ARN \
  --region $AWS_REGION \
  --query "executions[*].{name:name,status:status,start:startDate}" \
  --output table
```

**View Lambda logs** (optional — requires 30 s for logs to arrive):

```bash
# Confirm CancelReservation was invoked in the payment-fail execution
aws logs filter-log-events \
  --log-group-name /aws/lambda/cloudair-$USER_ID-cancel-reservation \
  --filter-pattern "CancelReservation" \
  --region $AWS_REGION \
  --query "events[*].message" \
  --output text | head -5
```

---

## Discussion

**Orchestration vs choreography:**

Step Functions is an **orchestrator** — a central process that calls each participant and coordinates the overall workflow. An alternative is **choreography** — each service publishes events (e.g., to EventBridge) and subscribes to events from other services; there is no central coordinator.

| | Orchestration (Step Functions) | Choreography (EventBridge) |
|---|---|---|
| Visibility | Execution graph in console | Must correlate events by correlation ID |
| Coupling | Orchestrator knows all participants | Services are decoupled by event schema |
| Failure handling | Explicit Catch/Retry in ASL | Each service handles its own DLQ |
| Best for | Sequential, state-dependent workflows | Fanout, broadcast, loosely coupled reactions |

The booking saga is a good fit for orchestration — steps are strictly sequential, each step depends on the previous one's result, and the compensation path must be deterministic.

**ResultPath and data flow:**

Without `ResultPath`, each Task state replaces `$` (the entire execution input) with the Lambda response. Setting `"ResultPath": "$.someKey"` merges the response under that key while preserving all other fields. This is how `$customerId` from step 1 remains available in step 4 even though `ChargePayment` only returned `chargeId` and `amount`.

**Idempotency in compensating transactions:**

The `CancelReservation` handler must be **idempotent** — if Step Functions retries it after a timeout, calling it twice must not result in releasing two different seat holds. In a production system, the handler would check whether the reservation is already in `CANCELLED` state before performing the release.

---

## Success Criteria (2 min)

- ✅ Stack `cloudair-$USER_ID-saga` deployed with `CREATE_COMPLETE` status
- ✅ Four Lambda functions (`reserve-seat`, `charge-payment`, `confirm-booking`, `cancel-reservation`) exist
- ✅ Happy-path execution ends at `BookingConfirmed` (Succeed) with a `bookingId` in the output
- ✅ Payment-failure execution shows `ChargePayment` → `CancelReservation` → `BookingFailed` in the graph
- ✅ Reserve-failure execution ends at `BookingFailed` without invoking `CancelReservation`
- ✅ You can explain the role of `ResultPath` in preserving execution state across steps
