# 🧪 Lab 3b — Secrets Management & Rotation with Secrets Manager

*Hands-On Lab · 45 min · CLI + SDK · Day 1 — Configuration & Secrets*

## Objectives (3 min)

- Create a structured secret in AWS Secrets Manager for a database credential / API key under `cloudair/$USER_ID/db`
- Retrieve the secret value via the AWS CLI and via a boto3 Python script, parsing the returned JSON payload
- Understand client-side caching and why it matters for Lambda cold-start costs and rate-limit avoidance
- Enable automatic rotation using a managed rotation Lambda, observe the version staging labels (`AWSCURRENT` / `AWSPREVIOUS`), and verify the app continues to function after rotation
- Articulate precisely when to choose Secrets Manager over SSM Parameter Store SecureString

> This lab assumes the SSM parameters from Lab 3a exist. The `$USER_ID` environment variable must be set.

---

## Prerequisites (3 min)

- Lab 3a complete — `/cloudair/$USER_ID/` parameters exist in SSM Parameter Store
- `~/.aws-adv-dev.env` contains `$USER_ID`, `$ACCT`, and `$AWS_REGION`
- Cloud9 terminal open; repo cloned to `~/environment/aws-adv-dev`

```bash
source ~/.aws-adv-dev.env
echo "USER_ID=$USER_ID  ACCT=$ACCT  REGION=$AWS_REGION"
```

> **Starting fresh?** `bash ~/environment/aws-adv-dev/bootstrap.sh 3b` sources your env file, verifies Lab 3a parameters are present, and confirms the IAM role has `secretsmanager:*` permissions.

---

## Step 1 — Understand the Secret Structure (5 min)

Secrets Manager stores a secret as a **name** (path-style string) containing a **JSON string value**. By convention, each secret holds one logical credential as a JSON object:

```json
{
  "username":  "cloudair_app",
  "password":  "S3cur3P@ss!",
  "engine":    "mysql",
  "host":      "db.cloudair.internal",
  "port":      "3306",
  "dbname":    "bookings"
}
```

This structure is intentional:
- The **rotation Lambda** knows where each field is — it rotates only the `password` field while leaving `host`, `port`, and `dbname` intact
- Application code fetches the entire JSON blob in one API call, then picks the fields it needs
- Multiple versions of the blob can coexist under staging labels (`AWSCURRENT`, `AWSPREVIOUS`, `AWSPENDING`) so a rotation never hard-deletes the previous credential before the new one is confirmed working

**Contrast with SSM SecureString:** SSM stores a single scalar value per parameter. Storing a structured credential requires either multiple parameters or a hand-serialized JSON string — neither approach participates in managed rotation.

---

## Step 2 — Create the Secret via CLI (8 min)

```bash
source ~/.aws-adv-dev.env

# Build the secret value as a JSON string
SECRET_VALUE=$(cat <<EOF
{
  "username": "cloudair_app",
  "password": "InitialPass-$(date +%s)",
  "engine":   "mysql",
  "host":     "db-${USER_ID}.cloudair.internal",
  "port":     "3306",
  "dbname":   "bookings_${USER_ID}"
}
EOF
)

aws secretsmanager create-secret \
    --name "cloudair/$USER_ID/db" \
    --description "Cloud Air database credential for $USER_ID" \
    --secret-string "$SECRET_VALUE" \
    --region $AWS_REGION
```

> Secrets Manager enforces a **7-day waiting period** before a secret can be permanently deleted (configurable down to 0 days with `--force-delete-without-recovery` for test environments). This prevents accidental data loss in production — a deleted secret cannot be immediately recreated with the same name.

Capture the secret ARN for later steps:

```bash
SECRET_ARN=$(aws secretsmanager describe-secret \
    --secret-id "cloudair/$USER_ID/db" \
    --query "ARN" \
    --output text \
    --region $AWS_REGION)

echo "export SECRET_ARN=$SECRET_ARN" >> ~/.aws-adv-dev.env
source ~/.aws-adv-dev.env
echo "Secret ARN: $SECRET_ARN"
```

---

## Step 3 — Retrieve the Secret via CLI (5 min)

**Basic retrieval — current version:**

```bash
source ~/.aws-adv-dev.env

aws secretsmanager get-secret-value \
    --secret-id "cloudair/$USER_ID/db" \
    --region $AWS_REGION
```

The response includes `SecretString` (the JSON payload), `VersionId`, and `VersionStages` — an array that currently contains only `["AWSCURRENT"]`.

**Extract just the password field:**

```bash
aws secretsmanager get-secret-value \
    --secret-id "cloudair/$USER_ID/db" \
    --query "SecretString" \
    --output text \
    --region $AWS_REGION \
  | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['password'])"
```

**List all versions and their staging labels:**

```bash
aws secretsmanager list-secret-version-ids \
    --secret-id "cloudair/$USER_ID/db" \
    --query "Versions[*].{VersionId:VersionId,Stages:VersionStages}" \
    --output table \
    --region $AWS_REGION
```

At this point only one version exists, with stage `AWSCURRENT`.

---

## Step 4 — Read the Secret from Python with boto3 (8 min)

> Open `~/environment/aws-adv-dev/lab3/get_secret.py` in the Cloud9 editor and review the script before running.

```bash
cd ~/environment/aws-adv-dev/lab3
python3 get_secret.py
```

The script:
1. Reads `$USER_ID` from the environment to construct the secret name
2. Calls `get_secret_value` using the boto3 Secrets Manager client
3. Parses the `SecretString` JSON into a Python dict
4. Prints each field, masking the password after the first four characters
5. Demonstrates a simple **in-process cache** using a module-level dictionary — the secret is fetched at most once per Lambda execution environment (or per process lifetime in a long-running server)

Confirm the output shows all six fields (`username`, `password`, `engine`, `host`, `port`, `dbname`) with the password partially masked.

**Why cache?** Secrets Manager imposes a service quota of ~10,000 API calls per second per region. A high-traffic Lambda function invoked thousands of times per second would exhaust this limit and cause throttle errors on every cold start. The AWS-maintained `aws-secretsmanager-caching-python` library implements a TTL-based cache with automatic refresh — it is the recommended pattern for Lambda.

---

## Step 5 — Enable Automatic Rotation (10 min)

Secrets Manager can rotate a secret automatically on a schedule using a **rotation Lambda**. For database credentials, AWS provides managed rotation Lambda functions in the Secrets Manager console — you do not write the rotation logic yourself.

**For this lab environment** (there is no live RDS instance), you will configure rotation pointing at the same secret to demonstrate the version-staging mechanics without an actual database connection.

```bash
source ~/.aws-adv-dev.env

# Enable rotation — 30-day schedule, immediately rotate once
aws secretsmanager rotate-secret \
    --secret-id "cloudair/$USER_ID/db" \
    --rotation-rules AutomaticallyAfterDays=30 \
    --rotate-immediately \
    --region $AWS_REGION
```

> In a real deployment you would first create the rotation Lambda (or use a managed single-user/alternating-user Lambda from the Secrets Manager console) and pass its ARN via `--rotation-lambda-arn`. Without a rotation Lambda configured here, the `rotate-secret` call schedules the rotation but does not create a new version — which is the expected behaviour when no Lambda ARN is supplied.

**Observe what a completed rotation looks like** by manually creating a new version to simulate what the rotation Lambda would produce:

```bash
source ~/.aws-adv-dev.env

NEW_PASS="RotatedPass-$(date +%s)"

# Simulate the "set new version" step of the rotation Lambda
aws secretsmanager put-secret-value \
    --secret-id "cloudair/$USER_ID/db" \
    --secret-string "{\"username\":\"cloudair_app\",\"password\":\"$NEW_PASS\",\"engine\":\"mysql\",\"host\":\"db-${USER_ID}.cloudair.internal\",\"port\":\"3306\",\"dbname\":\"bookings_${USER_ID}\"}" \
    --version-stages AWSCURRENT \
    --region $AWS_REGION
```

Now inspect the version list again:

```bash
aws secretsmanager list-secret-version-ids \
    --secret-id "cloudair/$USER_ID/db" \
    --query "Versions[*].{VersionId:VersionId,Stages:VersionStages}" \
    --output table \
    --region $AWS_REGION
```

You should see two versions:
- One with `["AWSCURRENT"]` — the new rotated credential
- One with `["AWSPREVIOUS"]` — the previous credential, retained so any in-flight transactions using the old password can complete

Retrieve the current and previous passwords and confirm they differ:

```bash
source ~/.aws-adv-dev.env

echo "=== AWSCURRENT ==="
aws secretsmanager get-secret-value \
    --secret-id "cloudair/$USER_ID/db" \
    --version-stage AWSCURRENT \
    --query "SecretString" --output text \
    --region $AWS_REGION \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['password'])"

echo "=== AWSPREVIOUS ==="
aws secretsmanager get-secret-value \
    --secret-id "cloudair/$USER_ID/db" \
    --version-stage AWSPREVIOUS \
    --query "SecretString" --output text \
    --region $AWS_REGION \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['password'])"
```

---

## Step 6 — Wire the Secret into the Monolith (4 min)

Application code should **never** hard-code a database password. The pattern is: fetch the current secret at startup, parse it, build the connection string.

Review the pattern in `get_secret.py` — the `load_for_app()` function at the bottom returns a dict ready to pass to a database driver or an ORM's `create_engine()` call. In a containerised deployment this function runs once at process start; in Lambda it runs on cold start, with the module-level cache preventing repeat calls on warm invocations.

```bash
cd ~/environment/aws-adv-dev/lab3

# Demonstrate the app-wiring pattern
python3 - <<'PYEOF'
import os, sys
sys.path.insert(0, ".")
from get_secret import load_for_app

cfg = load_for_app()
print(f"Would connect to: {cfg['engine']}://{cfg['username']}:***@{cfg['host']}:{cfg['port']}/{cfg['dbname']}")
PYEOF
```

---

## Discussion

**Secrets Manager vs SSM Parameter Store SecureString — the decision matrix:**

| Concern | SSM SecureString | Secrets Manager |
|---------|-----------------|-----------------|
| Cost | Free (Standard tier) | ~$0.40/secret/month + $0.05/10k API calls |
| Structured credentials | Manual JSON serialisation | Native JSON secret value |
| Managed rotation | Not supported | Built-in, database-aware rotation Lambdas |
| Cross-account access | Via resource policy | Via resource policy |
| Version staging labels | Versions only (no labels) | `AWSCURRENT` / `AWSPREVIOUS` / `AWSPENDING` |
| Replication to other regions | Not supported | Native multi-region replication |
| Best fit | App config, feature flags, non-rotating API keys | Database passwords, OAuth tokens, any credential requiring rotation |

**The rotation lifecycle in detail:**

A managed single-user rotation Lambda executes four steps atomically:
1. **createSecret** — generate a new random password, store it under `AWSPENDING`
2. **setSecret** — apply the new password to the actual database (calls `ALTER USER`)
3. **testSecret** — open a test connection with `AWSPENDING` to confirm it works
4. **finishSecret** — promote `AWSPENDING` to `AWSCURRENT`, demote `AWSCURRENT` to `AWSPREVIOUS`

If any step fails, the rotation rolls back and the secret remains unchanged — your application never sees a broken credential.

**Caching in Lambda:**

The `aws-secretsmanager-caching-python` library (`pip install aws-secretsmanager-caching`) uses a TTL (default 1 hour) and refreshes the cache in the background. Install it in your Lambda deployment package and replace direct `get_secret_value` calls with `cache.get_secret_string(secret_name)`. This eliminates per-invocation API calls for warm Lambdas while ensuring credentials are refreshed within the TTL window after rotation.

---

## Success Criteria (3 min)

- ✅ Secret `cloudair/$USER_ID/db` exists in Secrets Manager with all six credential fields in the JSON payload
- ✅ `aws secretsmanager get-secret-value` returns the plaintext JSON and the `AWSCURRENT` version stage
- ✅ `python3 get_secret.py` prints all fields with the password partially masked — no exceptions
- ✅ At least two versions exist after the manual rotation simulation: one `AWSCURRENT`, one `AWSPREVIOUS`
- ✅ `AWSCURRENT` and `AWSPREVIOUS` passwords differ — confirming the rotation produced a new credential
- ✅ The app-wiring pattern in `get_secret.py` printed the connection string without hard-coding the password
