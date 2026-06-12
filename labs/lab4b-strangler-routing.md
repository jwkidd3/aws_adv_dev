# 🧪 Lab 4b — Strangler Routing: Proxy the Monolith

*Hands-On Lab · 45 min · Console + CLI · Day 2 — The Strangler Fig Pattern*

## Objectives (3 min)

- Configure the API Gateway HTTP API (from Lab 4a) as a **Strangler Facade**: route `/flights` to the extracted Lambda microservice and proxy everything else to the legacy Elastic Beanstalk monolith via an `HTTP_PROXY` catch-all integration
- Update the SAM stack to supply the real `MonolithUrl` parameter
- Verify that the extracted route hits Lambda while all other routes (`/`, `/bookings`, `/bookings/<id>`) still hit the EB monolith transparently
- Understand the anti-corruption layer concept: callers use one base URL for the entire API regardless of which backend serves each route
- Discuss weighted/canary cutover as the next step when the Strangler Fig is fully deployed

> After this lab, the facade URL (`$FLIGHTS_API_URL`) is the single entry point for Cloud Air. The EB monolith still handles most traffic. In Lab 5 and beyond, further routes are extracted until the monolith can be decommissioned.

---

## Prerequisites (3 min)

- Lab 4a complete — stack `cloudair-$USER_ID-flights` is `CREATE_COMPLETE`
- `$USER_ID`, `$BOOKINGS_TABLE`, `$EB_URL`, `$FLIGHTS_API_URL`, and `$AWS_REGION` exported in `~/.aws-adv-dev.env`

```bash
source ~/.aws-adv-dev.env
echo "USER_ID=$USER_ID"
echo "EB_URL=$EB_URL"
echo "FLIGHTS_API_URL=$FLIGHTS_API_URL"
```

> **Starting fresh?** `bash ~/environment/aws-adv-dev/bootstrap.sh 4b` sources your env file, verifies both the base stack and flights stack exist, and prints the values above.

---

## Step 1 — Understand the Strangler Facade Architecture (5 min)

Before touching any AWS resources, map out what you are building:

```
Client
  │
  ▼
API Gateway HTTP API  (cloudair-$USER_ID-flights — prod stage)
  │
  ├── GET  /flights          ──► FlightsFn (Lambda)   ← EXTRACTED
  ├── GET  /flights/{id}     ──► FlightsFn (Lambda)   ← EXTRACTED
  │
  └── ANY  /{proxy+}         ──► EB monolith (HTTP_PROXY)  ← LEGACY
              │
              ▼
        Elastic Beanstalk (cloudair-$USER_ID-env)
          GET  /
          POST /bookings
          GET  /bookings
          GET  /bookings/{id}
          GET  /flights        ← still there but no longer reached by clients
```

The `ANY /{proxy+}` catch-all already exists in the Flights HTTP API — it lives in the `FlightsApi.DefinitionBody` and was created back in Lab 4a, but pointing at the dummy `http://replace-me.invalid`. This step just redeploys with the **real** EB CNAME as `MonolithUrl`, so the same route now forwards to the live monolith. (It's in the managed definition deliberately, so it won't get dropped when Lab 7a regenerates the API to add the authorizer.)

> **Anti-corruption layer:** the facade URL never exposes the EB CNAME to clients. When the monolith is eventually decommissioned (or replaced route by route), only the API Gateway integrations change — no client code needs updating.

---

## Step 2 — Verify the Current Routing Behaviour (5 min)

Confirm that `/flights` already works via Lambda (as expected from Lab 4a):

```bash
source ~/.aws-adv-dev.env

curl -s "$FLIGHTS_API_URL/flights" | python3 -m json.tool
```

Now test a route that is **not** yet extracted. The `ANY /{proxy+}` catch-all already exists, but it still points at the dummy `http://replace-me.invalid` from Lab 4a, so the proxy can't reach a real backend:

```bash
curl -s -o /dev/null -w "%{http_code}\n" "$FLIGHTS_API_URL/"
```

You'll see a **`5xx`** (typically `503`) — API Gateway matched the catch-all route and tried to proxy to `replace-me.invalid`, which doesn't resolve. After Step 3 supplies the real `MonolithUrl`, this same request forwards to the monolith and returns its home-page JSON.

---

## Step 3 — Update the SAM Stack with the Real MonolithUrl (12 min)

The SAM CLI stores the previous deploy parameters in `samconfig.toml`. You only need to override `MonolithUrl`.

```bash
source ~/.aws-adv-dev.env
cd ~/environment/aws-adv-dev/lab4

# The EB_URL from lab2b is a hostname only (no http:// prefix); add it
MONOLITH_URL="http://$EB_URL"
echo "Monolith URL: $MONOLITH_URL"

sam deploy \
    --stack-name cloudair-$USER_ID-flights \
    --parameter-overrides \
        UserId=$USER_ID \
        BookingsTableName=$BOOKINGS_TABLE \
        MonolithUrl=$MONOLITH_URL \
    --region $AWS_REGION \
    --no-confirm-changeset
```

SAM computes a changeset — the only change is the proxy integration's `uri`, which moves from the dummy host to your real EB CNAME (the route itself already exists). The Lambda function and its `/flights` routes are unchanged, so the changeset is small.

> `--no-confirm-changeset` skips the interactive prompt. Appropriate here because you have already reviewed the changeset logic. In production pipelines, always review changesets before applying.

Wait for `UPDATE_COMPLETE` (approximately 1–2 minutes), then verify the update:

```bash
aws cloudformation describe-stacks \
    --stack-name cloudair-$USER_ID-flights \
    --query "Stacks[0].StackStatus" \
    --output text \
    --region $AWS_REGION
```

---

## Step 4 — Test the Strangler Facade End-to-End (10 min)

Use `$FLIGHTS_API_URL` as the single entry point for all requests:

**Extracted route — served by Lambda:**

```bash
source ~/.aws-adv-dev.env

# List flights — Lambda handler
curl -s "$FLIGHTS_API_URL/flights" | python3 -m json.tool

# Single flight — Lambda handler
curl -s "$FLIGHTS_API_URL/flights/CA101" | python3 -m json.tool
```

**Legacy routes — transparently proxied to the EB monolith:**

```bash
# Health check — proxied to EB /
curl -s "$FLIGHTS_API_URL/" | python3 -m json.tool

# List bookings — proxied to EB /bookings
curl -s "$FLIGHTS_API_URL/bookings" | python3 -m json.tool

# Create a booking — proxied to EB POST /bookings
curl -s -X POST "$FLIGHTS_API_URL/bookings" \
    -H "Content-Type: application/json" \
    -d '{"flightId": "CA202", "passengerName": "Grace Hopper"}' \
    | python3 -m json.tool
```

Confirm that the booking was written to DynamoDB (proving the proxy reached the monolith and the monolith wrote to DynamoDB):

```bash
aws dynamodb scan \
    --table-name $BOOKINGS_TABLE \
    --region $AWS_REGION \
    --query "Items[*].{id:bookingId.S,flight:flightId.S,passenger:passengerName.S}" \
    --output table
```

**Confirm Lambda is handling `/flights` (not EB):**

```bash
# Check Lambda invocation count increased
aws cloudwatch get-metric-statistics \
    --namespace AWS/Lambda \
    --metric-name Invocations \
    --dimensions Name=FunctionName,Value=cloudair-$USER_ID-flights \
    --start-time $(date -u -d '10 minutes ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || \
                  date -u -v-10M +%Y-%m-%dT%H:%M:%SZ) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
    --period 600 \
    --statistics Sum \
    --region $AWS_REGION \
    --output table
```

> If the proxy requests to the monolith return unexpected errors, check the EB health status first: `eb status --region $AWS_REGION` from `~/environment/aws-adv-dev/lab2/monolith`. A common issue is the EB instance going to sleep — a single request wakes it within 30 seconds.

---

## Step 5 — Inspect the Routing in the Console (5 min)

1. Open **API Gateway** in the AWS Console → **APIs** → select `cloudair-$USER_ID-flights`
2. Left nav → **Routes** — you should see:
   - `GET /flights`
   - `GET /flights/{flightId}`
   - `ANY /{proxy+}`
3. Click `GET /flights` → **Integration** — Integration type is **Lambda**, points to `cloudair-$USER_ID-flights`
4. Click `ANY /{proxy+}` → **Integration** — Integration type is **HTTP_PROXY**, URI is your EB URL
5. Left nav → **Stages** → `prod` → **Invoke URL** — this is `$FLIGHTS_API_URL`

Notice that the routes are evaluated in **specificity order**: a request to `/flights` matches the explicit route before the `/{proxy+}` wildcard. This is the routing logic that makes the Strangler Fig work without any application-level changes.

---

## Step 6 — Discuss Weighted and Canary Cutover (5 min)

> This step is a guided discussion — no AWS console changes required.

The current configuration is binary: `/flights` goes entirely to Lambda. A production Strangler Fig migration often uses **weighted routing** to shift traffic gradually:

| Strategy | Mechanism | When to use |
|----------|-----------|-------------|
| Weighted routing | API Gateway stage variables + two integrations, split by weight | Validate the new service handles production load before full cutover |
| Canary deployment | Lambda alias with weighted traffic between versions | Roll out a new version of the same microservice function |
| Feature flag | Route decision in application code (e.g. SSM param as a flag) | Hotswitch without a redeployment |

For the Strangler Fig specifically, the typical progression is:

1. Deploy the microservice behind the facade (Lab 4a)
2. Route 100% of traffic to the microservice via the facade (this lab)
3. Monitor error rates and latency — compare CloudWatch metrics for Lambda vs EB
4. Decommission the equivalent route from the monolith (a one-line delete in `application.py` + EB redeploy)
5. Repeat for the next route

The EB monolith still has a `/flights` route. It is never reached after this lab because the facade absorbs all `/flights` traffic. When you are confident in the microservice, you can remove the route from the monolith to reduce its scope — an explicit acknowledgement that the strangle is complete for that seam.

> In AWS, a more automated approach uses **Lambda weighted aliases** combined with **CodeDeploy linear/canary deployment configurations**. Lab 5b introduces CodeDeploy Lambda deployments.

---

## Discussion

- **Why HTTP_PROXY and not a custom integration?** HTTP_PROXY is a passthrough — API Gateway forwards the entire request (method, headers, body, query string) unchanged. A custom integration would require a mapping template. For a facade over an existing web app, passthrough is exactly what you want: the monolith sees the same request it would have seen from a direct client.
- **TLS between API Gateway and EB:** The HTTP_PROXY integration uses `http://` (plaintext) in this lab because EB `--single` does not provision a load balancer with an ACM certificate. In production, put an Application Load Balancer (with ACM cert) in front of EB and set the integration URI to `https://`.
- **The facade is the anti-corruption layer:** The monolith's data model, error codes, and response shapes are preserved behind the facade. The microservice uses the same response shape as the monolith's `/flights` route. As more routes are extracted, the anti-corruption layer ensures downstream consumers never know which backend served their request.
- **Cost profile change:** Before this lab, every `/flights` request hit an EC2 instance (running 24/7). After this lab, `/flights` is billed per-invocation at Lambda pricing. At classroom volumes this is near-zero; at production scale the savings are significant for bursty or low-traffic endpoints.

---

## Success Criteria (3 min)

- ✅ Stack `cloudair-$USER_ID-flights` updated to `UPDATE_COMPLETE` with the real `MonolithUrl`
- ✅ `GET $FLIGHTS_API_URL/flights` returns flight data and Lambda invocation count increments
- ✅ `GET $FLIGHTS_API_URL/` returns the EB health-check JSON (proxied transparently to the monolith)
- ✅ `POST $FLIGHTS_API_URL/bookings` returns HTTP 201 and the DynamoDB table contains the new booking
- ✅ API Gateway Console shows `GET /flights` → Lambda integration and `ANY /{proxy+}` → HTTP_PROXY integration
- ✅ Both `GET /flights` (Lambda) and `POST /bookings` (EB proxy) work through the single facade URL `$FLIGHTS_API_URL`
