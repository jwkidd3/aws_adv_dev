# 🧪 Lab 2b — Deploy the Cloud Air Monolith on Elastic Beanstalk

*Hands-On Lab · 45 min · CLI + Console · Day 1 — Elastic Beanstalk & the Monolith*

## Objectives (3 min)

- Package and deploy the Cloud Air legacy Flask application to Elastic Beanstalk using the `eb` CLI
- Set environment variables on the EB environment so the app reads config from the right DynamoDB table
- Verify all four routes (`/`, `/flights`, `POST /bookings`, `GET /bookings`) work end-to-end
- Identify the monolith characteristics — a single deployable unit, all routes in one process — that the rest of the course breaks apart using the Strangler Fig pattern

> This is the **before** state. Every subsequent lab peels off one piece of this application until almost nothing is left in Elastic Beanstalk.

---

## Prerequisites (3 min)

- Lab 2a complete — stack `cloudair-$USER_ID-base` is `CREATE_COMPLETE`
- `$USER_ID`, `$BOOKINGS_TABLE`, `$AWS_REGION` exported in `~/.aws-adv-dev.env`
- Elastic Beanstalk CLI (`eb`) — **not preinstalled on the Cloud9 image**; install it once (command below)

```bash
source ~/.aws-adv-dev.env
echo "USER_ID=$USER_ID  TABLE=$BOOKINGS_TABLE"

# The EB CLI is not on the Cloud9 AL2023 image. Install it once — idempotent,
# safe to re-run, and the PATH line survives new terminals / Cloud9 restarts.
eb --version 2>/dev/null || {
  python3 -m pip install --user awsebcli 2>/dev/null \
    || python3 -m pip install --user --break-system-packages awsebcli
  grep -q '.local/bin' ~/.bashrc || echo 'export PATH=$HOME/.local/bin:$PATH' >> ~/.bashrc
  export PATH=$HOME/.local/bin:$PATH
}
eb --version   # expect EB CLI 3.x
```

> Same command for every student — the EB CLI install is machine-level, not
> scoped to your `userN`. If `python3 -m pip` reports
> `externally-managed-environment`, the `--break-system-packages` fallback above
> handles it (fine in a throwaway training environment).

> **Starting fresh?** `bash ~/environment/aws-adv-dev/bootstrap.sh 2b` sources your env file and sets the `BOOKINGS_TABLE` variable. It does **not** deploy the base stack or verify the `eb` CLI — Lab 2a must be completed first (`bash bootstrap.sh 2a` or the manual Lab 2a steps) before running this lab.

---

## Step 1 — Review the Monolith Source (6 min)

> Open `~/environment/aws-adv-dev/lab2/monolith/application.py` in the Cloud9 editor.

Notice the structure:

| Route | Method | What it does |
|-------|--------|--------------|
| `/` | GET | Health check / version info |
| `/flights` | GET | Returns hard-coded flight list (filter by `origin`/`destination` query params) |
| `/bookings` | POST | Validates input, writes a new booking item to DynamoDB, returns 201 |
| `/bookings` | GET | Queries DynamoDB `userId-index` GSI for all bookings owned by `$USER_ID` |
| `/bookings/<id>` | GET | Fetches a single booking by primary key |

**This is the monolith pattern:** one Python process, one deployment artifact, one process manager (Gunicorn). Flights and bookings logic share the same codebase, the same config, the same dependency set, and the same failure domain. When you deploy a new version — even changing one route — *everything* redeploys.

Also review:

- `requirements.txt` — Flask, boto3, and Gunicorn
- `Procfile` — tells Elastic Beanstalk to start Gunicorn on port 8000
- `.ebextensions/python.config` — sets `WSGIPath` and the default `AWS_REGION` env var

---

## Step 2 — Initialise the Elastic Beanstalk Application (6 min)

```bash
source ~/.aws-adv-dev.env

cd ~/environment/aws-adv-dev/lab2/monolith

eb init cloudair-$USER_ID \
    --platform "Python 3.11 running on 64bit Amazon Linux 2023" \
    --region $AWS_REGION \
    --no-interactive
```

This creates a `.elasticbeanstalk/config.yml` file that records the application name and default region. It does **not** create any AWS resources yet.

```bash
# Confirm the config was written
cat .elasticbeanstalk/config.yml
```

> `eb init` creates an **application** in Elastic Beanstalk (a logical container for environments and versions). The application name is `cloudair-$USER_ID`. Each student's application is independent — EB applications are regional, not global, so name collisions across students are possible but the prefix prevents them here.

---

## Step 3 — Create the Environment and Deploy (12 min)

```bash
source ~/.aws-adv-dev.env
cd ~/environment/aws-adv-dev/lab2/monolith

eb create cloudair-$USER_ID-env \
    --instance-type t3.micro \
    --single \
    --region $AWS_REGION \
    --envvars "USER_ID=$USER_ID,BOOKINGS_TABLE=$BOOKINGS_TABLE,AWS_REGION=$AWS_REGION"
```

Flag notes:
- `--single` — skips the load balancer and Auto Scaling group; uses a single EC2 instance. Appropriate for a classroom environment where we care about cost, not availability.
- `--envvars` — injects environment variables into the EB environment. The app reads `USER_ID` and `BOOKINGS_TABLE` at startup via `os.environ.get(...)`.

`eb create` packages the current directory as a zip, uploads it to S3, launches the environment, and streams events to the terminal. The process takes approximately 4–6 minutes.

While the environment provisions, switch to the Console:

1. **Elastic Beanstalk → Applications → cloudair-$USER_ID**
2. Click the environment name → **Events** tab — watch the EC2 instance launch, EB agent install, Gunicorn start
3. **Health** panel — wait until it shows **OK** (green)

> If the health status stays **Degraded** after deployment completes, check the **Logs** tab → **Request last 100 lines** — the most common cause is a missing Python dependency or an incorrect `WSGIPath`.

---

## Step 4 — Retrieve the Endpoint and Smoke-Test the API (8 min)

```bash
source ~/.aws-adv-dev.env
cd ~/environment/aws-adv-dev/lab2/monolith

# Get the environment URL
EB_URL=$(eb status --region $AWS_REGION | grep "CNAME" | awk '{print $2}')
echo "http://$EB_URL"
echo "export EB_URL=$EB_URL" >> ~/.aws-adv-dev.env
source ~/.aws-adv-dev.env
```

**Test each route:**

```bash
# Health check
curl -s http://$EB_URL/ | python3 -m json.tool

# List flights
curl -s "http://$EB_URL/flights" | python3 -m json.tool

# Filter flights by origin
curl -s "http://$EB_URL/flights?origin=JFK" | python3 -m json.tool

# Create a booking (POST)
curl -s -X POST http://$EB_URL/bookings \
    -H "Content-Type: application/json" \
    -d "{\"flightId\": \"CA101\", \"passengerName\": \"Ada Lovelace\"}" \
    | python3 -m json.tool

# List bookings (should show the one just created)
curl -s http://$EB_URL/bookings | python3 -m json.tool
```

> Save the `bookingId` from the POST response — use it to test the single-booking route:

```bash
BOOKING_ID="<paste bookingId here>"
curl -s http://$EB_URL/bookings/$BOOKING_ID | python3 -m json.tool
```

Confirm the DynamoDB item exists independently of the app:

```bash
aws dynamodb scan \
    --table-name $BOOKINGS_TABLE \
    --region $AWS_REGION \
    --query "Items[*].{id:bookingId.S,flight:flightId.S,passenger:passengerName.S,status:status.S}" \
    --output table
```

---

## Step 5 — Note the Monolith Characteristics (5 min)

In the Console, navigate to **Elastic Beanstalk → cloudair-$USER_ID-env → Configuration**.

Observe:

- **Software category:** a single Python process running Gunicorn with one `WSGIPath`. There is no way to scale the flights lookup independently of the bookings write path — they are the same process.
- **Capacity category:** `--single` means one EC2 instance. To handle more load you resize or add instances — but the entire monolith scales, not just the hot path.
- **Updates, monitoring, and logging:** one set of logs for the whole application. When you need to debug a booking failure you must grep through logs that contain flights, health checks, and every other route.

> These are the pain points the Strangler Fig pattern addresses. Lab 4a extracts the first route into a Lambda + API Gateway microservice. Lab 4b adds a proxy rule so the EB monolith still handles every path *except* the extracted one — without a cutover. The monolith shrinks incrementally.

---

## Discussion

- **Why Elastic Beanstalk as the starting point?** EB is the managed PaaS lift from "it works on my laptop" to "it runs on AWS". It provisions EC2, Auto Scaling, load balancers, and deploys your code with a single command. It is a realistic representation of the first cloud migration step (the **Replatform** R from the 6 Rs).
- **`eb` CLI vs `aws cloudformation deploy`:** Under the hood, every EB environment *is* a CloudFormation stack. Run `aws cloudformation list-stacks --query "StackSummaries[?starts_with(StackName, 'awseb')]"` to see it.
- **Environment variables vs SSM:** The monolith reads `BOOKINGS_TABLE` from the process environment. Lab 3 refactors this to read from SSM Parameter Store instead, making the config auditable, versioned, and shareable across environments without redeploying.

---

## Success Criteria (3 min)

- ✅ EB application `cloudair-$USER_ID` and environment `cloudair-$USER_ID-env` exist in `us-east-1`
- ✅ Environment health is **OK** (green) in the EB Console
- ✅ `GET /` returns JSON with `"version": "1.0.0-monolith"`
- ✅ `GET /flights` returns all 4 flights; `?origin=JFK` returns only `CA101`
- ✅ `POST /bookings` returns HTTP 201 with a `bookingId` UUID
- ✅ `GET /bookings` returns at least 1 booking; `GET /bookings/<id>` returns the specific item
- ✅ DynamoDB `Bookings-$USER_ID` table contains the new booking item (confirmed via CLI scan)
- ✅ `$EB_URL` saved to `~/.aws-adv-dev.env`
