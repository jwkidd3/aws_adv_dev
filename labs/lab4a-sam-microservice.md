# 🧪 Lab 4a — Strangle the Monolith: First Microservice with SAM

*Hands-On Lab · 50 min · SAM CLI · Day 2 — Microservices & Serverless*

## Objectives (3 min)

- Read and understand a SAM template before deploying it
- Build a Lambda deployment package with `sam build`
- Deploy the Flights microservice (Lambda + HTTP API) with `sam deploy --guided` into stack `cloudair-$USER_ID-flights`
- Smoke-test the new `/flights` endpoint with `curl`
- Inspect structured logs with `sam logs`
- Understand how this Lambda function will replace the `/flights` route in the EB monolith — the first cut of the Strangler Fig

> Lab 4b wires API Gateway as a facade in front of both this microservice and the legacy monolith so the extraction is invisible to callers.

---

## Prerequisites (3 min)

- Labs 2a and 2b complete — stack `cloudair-$USER_ID-base` is `CREATE_COMPLETE`, EB environment `cloudair-$USER_ID-env` is healthy
- `$USER_ID`, `$BOOKINGS_TABLE`, `$EB_URL`, and `$AWS_REGION` exported in `~/.aws-adv-dev.env`
- SAM CLI installed — verify with `sam --version` (expect 1.x or later)

```bash
source ~/.aws-adv-dev.env
echo "USER_ID=$USER_ID  TABLE=$BOOKINGS_TABLE  EB=$EB_URL"
sam --version
```

> **Starting fresh?** `bash ~/environment/aws-adv-dev/bootstrap.sh 4a` sources your env file, verifies the base stack and EB environment exist, and confirms the SAM CLI is on your PATH.

---

## Step 1 — Review the SAM Template (8 min)

> Open `~/environment/aws-adv-dev/lab4/template.yaml` in the Cloud9 editor (double-click it in the file tree).

Work through each section:

| Section | What it defines |
|---------|-----------------|
| `Parameters` | `UserId`, `BookingsTableName`, `MonolithUrl` — the last one is used in Lab 4b |
| `Globals` | python3.12 runtime, arm64 (Graviton), 15 s timeout, X-Ray active tracing, shared env vars |
| `FlightsApi` | `AWS::Serverless::HttpApi` — HTTP API with a `prod` stage; payload format version 2.0 |
| `FlightsFn` | `AWS::Serverless::Function` — the extracted Flights Lambda; DynamoDB read-only policy |
| `Events` | Two `HttpApi` events: `GET /flights` and `GET /flights/{flightId}` |
| `MonolithIntegration` / `MonolithCatchAllRoute` | Raw `AWS::ApiGatewayV2` resources for the `ANY /{proxy+}` HTTP_PROXY route — wired up in Lab 4b |
| `Outputs` | `FlightsApiUrl`, `FlightsFunctionArn`, `FlightsFunctionName` |

Key decisions to understand:

- **`DynamoDBReadPolicy`** — SAM policy template that grants `dynamodb:GetItem`, `Scan`, `Query`, `DescribeTable` on exactly the named table. No write permissions; the microservice is read-only.
- **`arm64` (Graviton)** — Lambda functions on arm64 are approximately 20% cheaper than x86_64 at equivalent performance. Python 3.12 on arm64 is fully supported.
- **`Tracing: Active`** — enables X-Ray tracing for every invocation. Used in Lab 7b.
- **`MonolithUrl` parameter defaults to `"REPLACE_WITH_EB_CNAME"`** — safe placeholder for Lab 4a; the HTTP_PROXY route will not function until a real URL is supplied.

Now open `~/environment/aws-adv-dev/lab4/src/app.py`:

```
GET /flights               → _list_flights()  → DynamoDB scan filtered by FLIGHT# pk prefix
GET /flights/{flightId}    → _get_flight()    → DynamoDB get_item by primary key
```

Note the **static sample fallback**: if the DynamoDB table has no `FLIGHT#` items yet, the handler returns the four sample flights so the endpoint is immediately testable without seeding data.

> The response shape always uses `{"statusCode": ..., "headers": {...}, "body": "..."}` — this is the HTTP API payload format v2.0 contract. Lambda must return this structure; API Gateway unwraps it into a real HTTP response.

---

## Step 2 — Build the Deployment Package (5 min)

```bash
source ~/.aws-adv-dev.env

cd ~/environment/aws-adv-dev/lab4

sam build
```

`sam build` reads `template.yaml`, finds the `CodeUri: src/` directive for `FlightsFn`, installs `requirements.txt` into a clean build directory (`.aws-sam/build/FlightsFn/`), and copies the handler. The result is a zip-ready artefact that matches the Lambda execution environment exactly.

```bash
# Inspect what was built
ls .aws-sam/build/FlightsFn/
```

You should see `app.py` and a `boto3/` package directory. Every dependency is vendored — Lambda does not have network access at runtime.

> `sam build` uses a Docker container by default when Docker is available, matching the exact Amazon Linux 2023 runtime layer. In Cloud9 without Docker you can add `--use-container` explicitly or omit it to build natively (Python 3.12 on Amazon Linux 2023 is ABI-compatible).

---

## Step 3 — Deploy the Stack with `sam deploy --guided` (15 min)

```bash
source ~/.aws-adv-dev.env
cd ~/environment/aws-adv-dev/lab4

sam deploy --guided
```

Answer each prompt as follows:

| Prompt | Value |
|--------|-------|
| Stack Name | `cloudair-$USER_ID-flights` (type it literally, e.g. `cloudair-user1-flights`) |
| AWS Region | `us-east-1` |
| Parameter UserId | your `$USER_ID` value (e.g. `user1`) |
| Parameter BookingsTableName | your `$BOOKINGS_TABLE` value (e.g. `Bookings-user1`) |
| Parameter MonolithUrl | press Enter to accept `REPLACE_WITH_EB_CNAME` — Lab 4b will update this |
| Confirm changes before deploy | `y` |
| Allow SAM CLI IAM role creation | `y` |
| Disable rollback | `n` |
| FlightsFn has no authentication — is this okay? | `y` |
| Save arguments to configuration file | `y` |
| SAM configuration file | press Enter (accept `samconfig.toml`) |
| SAM configuration environment | press Enter (accept `default`) |

SAM prints a **changeset** showing the resources it will create. Review it — you should see:

- `AWS::ApiGatewayV2::Api` (the HTTP API)
- `AWS::Lambda::Function` (the Flights function)
- `AWS::IAM::Role` (execution role with the DynamoDB read policy)
- `AWS::ApiGatewayV2::Integration`, `AWS::ApiGatewayV2::Route` (for both `/flights` and `/{proxy+}`)
- `AWS::ApiGatewayV2::Stage`

Confirm the deploy. SAM creates the stack and streams events — the process takes approximately 2–3 minutes.

```bash
# After the deploy completes, save the API URL
FLIGHTS_API_URL=$(aws cloudformation describe-stacks \
    --stack-name cloudair-$USER_ID-flights \
    --query "Stacks[0].Outputs[?OutputKey=='FlightsApiUrl'].OutputValue" \
    --output text \
    --region $AWS_REGION)

echo "export FLIGHTS_API_URL=$FLIGHTS_API_URL" >> ~/.aws-adv-dev.env
source ~/.aws-adv-dev.env
echo "Flights API: $FLIGHTS_API_URL"
```

> `samconfig.toml` records all your answers so future deploys only need `sam deploy` (no `--guided`). Commit this file to version control — it is safe to share (no secrets, only parameter names and stack config).

---

## Step 4 — Test the Endpoint (8 min)

```bash
source ~/.aws-adv-dev.env

# List all flights (DynamoDB or static fallback)
curl -s "$FLIGHTS_API_URL/flights" | python3 -m json.tool

# Filter by origin
curl -s "$FLIGHTS_API_URL/flights?origin=JFK" | python3 -m json.tool

# Filter by destination
curl -s "$FLIGHTS_API_URL/flights?destination=LAX" | python3 -m json.tool

# Retrieve a single flight by ID
curl -s "$FLIGHTS_API_URL/flights/CA101" | python3 -m json.tool

# Non-existent flight — expect HTTP 404
curl -s -o /dev/null -w "%{http_code}\n" "$FLIGHTS_API_URL/flights/XX999"
```

Compare the output of `GET /flights` via Lambda with the same route on the EB monolith:

```bash
# Monolith (EB) — still the original handler
curl -s "http://$EB_URL/flights" | python3 -m json.tool

# Microservice (Lambda) — new handler, same data shape
curl -s "$FLIGHTS_API_URL/flights" | python3 -m json.tool
```

Both routes should return the same four flights. The responses are intentionally identical — the microservice is a **drop-in replacement** for the monolith's `/flights` route. This is the anti-corruption layer principle: callers see no change.

> If you see `{"message":"Internal Server Error"}`, open the Lambda console → `cloudair-$USER_ID-flights` → **Monitor → View logs in CloudWatch** to read the Python traceback. Common cause: `BOOKINGS_TABLE` environment variable set to an incorrect table name.

---

## Step 5 — View Logs with `sam logs` (6 min)

```bash
source ~/.aws-adv-dev.env
cd ~/environment/aws-adv-dev/lab4

# Tail the last 5 minutes of logs
sam logs \
    --stack-name cloudair-$USER_ID-flights \
    --name FlightsFn \
    --region $AWS_REGION \
    --tail
```

Press **Ctrl+C** to stop tailing. Each log line is a structured JSON record (Lambda's built-in format) followed by the function's own `logger.info(...)` output. Locate:

- `START RequestId` / `END RequestId` / `REPORT` — Lambda platform lifecycle messages
- `Invoked — routeKey=GET /flights requestId=…` — from `app.py`
- `DynamoDB scan returned N flight items` or `No FLIGHT# items … returning static sample catalogue`

Retrieve logs for a specific time window:

```bash
sam logs \
    --stack-name cloudair-$USER_ID-flights \
    --name FlightsFn \
    --region $AWS_REGION \
    --start-time "10min ago"
```

> `sam logs` is a wrapper around CloudWatch Logs Insights. You can also query logs directly from the Lambda console (**Monitor** tab) or from **CloudWatch → Log groups → /aws/lambda/cloudair-$USER_ID-flights**.

---

## Discussion

- **Why extract `/flights` first?** It is the safest seam — a read-only, stateless handler with no side effects. Extracting a write path (like `POST /bookings`) requires careful dual-write or event-sourcing strategies. Start read-only, validate correctness, then tackle writes.
- **SAM vs raw CloudFormation:** SAM `Transform` expands `AWS::Serverless::Function` into 4–6 raw CloudFormation resources (Lambda function, IAM role, log group, event source mappings). The SAM template is far shorter. `sam build` + `sam deploy` also handles S3 artifact upload transparently — with `aws cloudformation deploy` you would manage that yourself.
- **HTTP API vs REST API:** API Gateway HTTP API (v2) costs ~70% less than REST API (v1), has lower latency, and uses payload format version 2.0. REST API offers more features (usage plans, caching, request validation). HTTP API is the right choice for a Lambda-backed microservice without those extras.
- **Twelve-Factor alignment:** The function reads its table name from `BOOKINGS_TABLE` environment variable (Factor III — config). The build artefact is self-contained (Factor VI — processes). Logs go to stdout → CloudWatch (Factor XI — logs).

---

## Success Criteria (3 min)

- ✅ `sam build` completes without error; `.aws-sam/build/FlightsFn/app.py` exists
- ✅ Stack `cloudair-$USER_ID-flights` is `CREATE_COMPLETE` in `us-east-1`
- ✅ `GET $FLIGHTS_API_URL/flights` returns JSON with a `flights` array and `count` field
- ✅ `GET $FLIGHTS_API_URL/flights?origin=JFK` returns only flights departing from JFK
- ✅ `GET $FLIGHTS_API_URL/flights/CA101` returns the CA101 flight object
- ✅ `GET $FLIGHTS_API_URL/flights/XX999` returns HTTP 404
- ✅ `sam logs` shows structured log output including `routeKey=GET /flights`
- ✅ `$FLIGHTS_API_URL` saved to `~/.aws-adv-dev.env`
