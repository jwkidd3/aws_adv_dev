# 🧪 Lab 3a — Twelve-Factor Config with SSM Parameter Store

*Hands-On Lab · 45 min · CLI + SDK · Day 2 — Configuration & Secrets*

## Objectives (3 min)

- Create String and SecureString parameters in SSM Parameter Store under the `/cloudair/$USER_ID/` hierarchy using the AWS CLI
- Retrieve individual parameters and an entire path subtree with `get-parameter` and `get-parameters-by-path`
- Read parameters from Python using the boto3 SSM client, with automatic KMS decryption
- Wire the retrieved config values into the Cloud Air monolith as environment variables — demonstrating Twelve-Factor **Factor III: Config in the Environment**
- Understand the practical differences between SSM parameter tiers, data types, and the hierarchy naming convention

> Lab 3b builds directly on this foundation: it moves the database credential you create here into Secrets Manager and adds automatic rotation.

---

## Prerequisites (3 min)

- Lab 2a complete — stack `cloudair-$USER_ID-base` is in `CREATE_COMPLETE` state and `~/.aws-adv-dev.env` contains `$USER_ID`, `$ACCT`, and `$AWS_REGION`
- Cloud9 terminal open; repo cloned to `~/environment/aws-adv-dev`

```bash
source ~/.aws-adv-dev.env
echo "USER_ID=$USER_ID  ACCT=$ACCT  REGION=$AWS_REGION"
```

> **Starting fresh?** `bash ~/environment/aws-adv-dev/bootstrap.sh 3a` sets `$USER_ID`, `$ACCT`, and `$AWS_REGION` in `~/.aws-adv-dev.env` and verifies the Lab 2a stack is present.

---

## Step 1 — Examine the Sample Parameter Definitions (5 min)

> Open `~/environment/aws-adv-dev/lab3/params.json` in the Cloud9 editor.

This file defines four parameters the lab will load — three `String` values that describe application topology, and one `SecureString` value (an API key) that should never appear in plaintext in source control or logs.

| Parameter name (suffix) | Type | Purpose |
|-------------------------|------|---------|
| `/flights_table` | String | DynamoDB table name |
| `/assets_bucket` | String | S3 assets bucket name |
| `/region` | String | Preferred AWS region for SDK clients |
| `/ext_api_key` | SecureString | Third-party API key — encrypted at rest |

The naming hierarchy `/cloudair/$USER_ID/<key>` does three things simultaneously:
- **Isolates** each student's parameters so 20 students share one account without collision
- **Groups** all Cloud Air parameters under a common path, making `get-parameters-by-path` the natural retrieval pattern
- **Models** a real multi-environment convention — production teams extend the pattern to `/myapp/prod/<key>` vs `/myapp/staging/<key>`

---

## Step 2 — Create the Parameters via CLI (10 min)

Source your environment, then create each parameter. The `--overwrite` flag makes the commands safe to re-run.

```bash
source ~/.aws-adv-dev.env

# Derive resource names written by Lab 2a (or fall back to defaults)
FLIGHTS_TABLE=${BOOKINGS_TABLE:-"Bookings-$USER_ID"}
ASSETS_BUCKET=${ASSETS_BUCKET:-"cloudair-$USER_ID-assets"}

# String parameters
aws ssm put-parameter \
    --name "/cloudair/$USER_ID/flights_table" \
    --value "$FLIGHTS_TABLE" \
    --type String \
    --description "DynamoDB bookings table for $USER_ID" \
    --overwrite \
    --region $AWS_REGION

aws ssm put-parameter \
    --name "/cloudair/$USER_ID/assets_bucket" \
    --value "$ASSETS_BUCKET" \
    --type String \
    --description "S3 assets bucket for $USER_ID" \
    --overwrite \
    --region $AWS_REGION

aws ssm put-parameter \
    --name "/cloudair/$USER_ID/region" \
    --value "$AWS_REGION" \
    --type String \
    --description "Preferred region for SDK clients" \
    --overwrite \
    --region $AWS_REGION

# SecureString parameter — encrypted with the account's default SSM KMS key
aws ssm put-parameter \
    --name "/cloudair/$USER_ID/ext_api_key" \
    --value "cloudair-demo-$(date +%s)" \
    --type SecureString \
    --description "External partner API key — do not log" \
    --overwrite \
    --region $AWS_REGION
```

> `SecureString` parameters are encrypted at rest using KMS. By default SSM uses the AWS-managed key `alias/aws/ssm`. You can specify `--key-id alias/my-custom-key` to use a customer-managed KMS key — required by many compliance frameworks (PCI-DSS, HIPAA).

Confirm all four parameters were created:

```bash
aws ssm get-parameters-by-path \
    --path "/cloudair/$USER_ID" \
    --query "Parameters[*].{Name:Name,Type:Type,Version:Version}" \
    --output table \
    --region $AWS_REGION
```

---

## Step 3 — Retrieve Parameters via CLI (5 min)

**Single parameter — plaintext String:**

```bash
aws ssm get-parameter \
    --name "/cloudair/$USER_ID/flights_table" \
    --query "Parameter.Value" \
    --output text \
    --region $AWS_REGION
```

**Single SecureString — without decryption (default):**

```bash
aws ssm get-parameter \
    --name "/cloudair/$USER_ID/ext_api_key" \
    --query "Parameter.{Value:Value,Type:Type}" \
    --output json \
    --region $AWS_REGION
```

> The value is returned as a KMS ciphertext blob — it is not plaintext. This is what an application without KMS `Decrypt` permission would receive.

**Single SecureString — with decryption:**

```bash
aws ssm get-parameter \
    --name "/cloudair/$USER_ID/ext_api_key" \
    --with-decryption \
    --query "Parameter.Value" \
    --output text \
    --region $AWS_REGION
```

**Entire path subtree with decryption:**

```bash
aws ssm get-parameters-by-path \
    --path "/cloudair/$USER_ID" \
    --with-decryption \
    --query "Parameters[*].{Name:Name,Value:Value,Type:Type}" \
    --output table \
    --region $AWS_REGION
```

Note that `get-parameters-by-path` paginates automatically via the CLI but returns a `NextToken` when called via the SDK — the Python script in the next step handles this correctly.

---

## Step 4 — Read Parameters from Python with boto3 (10 min)

> Open `~/environment/aws-adv-dev/lab3/load_config.py` in the Cloud9 editor and read through it before running.

```bash
cd ~/environment/aws-adv-dev/lab3
python3 load_config.py
```

The script reads `$USER_ID` from the environment, constructs the SSM path, calls `get_parameters_by_path` in a pagination loop, decrypts SecureString values in-place, and prints a clean key→value table. Confirm:

- All four parameters appear in the output
- The `ext_api_key` value is the plaintext value you stored (not a ciphertext blob) — proving the SDK honoured `WithDecryption=True`
- The script logs a warning (not a crash) if `$USER_ID` is unset, then falls back to a safe default

---

## Step 5 — Wire Config into the Monolith (8 min)

The Cloud Air monolith already reads its configuration from environment variables (see `lab2/monolith/application.py`, lines 27–29). All that remains is to populate those variables from SSM at startup time.

A real 12-Factor deployment would populate the environment in the process manager (EB's `.env` configuration, ECS task-definition environment, or a Lambda environment block). In Cloud9 you will export the values directly:

```bash
source ~/.aws-adv-dev.env

# Load all /cloudair/$USER_ID/* params into shell variables
while IFS=$'\t' read -r name value; do
    # Uppercase and turn '-' into '_' so names like 'assets-bucket' (created by
    # the Lab 2a base stack under this same path) become valid shell variables.
    key=$(basename "$name" | tr 'a-z-' 'A-Z_')
    export "$key=$value"
    echo "Exported: $key"
done < <(aws ssm get-parameters-by-path \
    --path "/cloudair/$USER_ID" \
    --with-decryption \
    --query "Parameters[*].[Name,Value]" \
    --output text \
    --region $AWS_REGION)

# The SSM parameter is stored as 'flights_table', which the loop exports as
# FLIGHTS_TABLE.  The monolith reads BOOKINGS_TABLE, so alias it here:
export BOOKINGS_TABLE=$FLIGHTS_TABLE

# Verify the table name came through
echo "FLIGHTS_TABLE=$FLIGHTS_TABLE"
echo "BOOKINGS_TABLE=$BOOKINGS_TABLE"
echo "ASSETS_BUCKET=$ASSETS_BUCKET"
```

Then start the monolith and hit it:

```bash
cd ~/environment/aws-adv-dev/lab2/monolith
pip3 install -q --user -r requirements.txt \
    || pip3 install -q --user --break-system-packages -r requirements.txt
python3 application.py &
sleep 2
curl -s http://localhost:5000/ | python3 -m json.tool
curl -s http://localhost:5000/flights | python3 -m json.tool
kill %1   # stop the background Flask process
```

The `/` health-check response includes `"user": "$USER_ID"` — confirming the process inherited the SSM-sourced config.

---

## Step 6 — Explore History and Versions (4 min)

SSM keeps a full version history of every parameter. Update the region parameter and observe:

```bash
source ~/.aws-adv-dev.env

# Intentionally write a "wrong" value to create a new version
aws ssm put-parameter \
    --name "/cloudair/$USER_ID/region" \
    --value "eu-west-1" \
    --type String \
    --overwrite \
    --region $AWS_REGION

# Show all versions
aws ssm get-parameter-history \
    --name "/cloudair/$USER_ID/region" \
    --query "Parameters[*].{Version:Version,Value:Value,LastModifiedDate:LastModifiedDate}" \
    --output table \
    --region $AWS_REGION

# Retrieve a specific older version by appending :<version> to the name
aws ssm get-parameter \
    --name "/cloudair/$USER_ID/region:1" \
    --query "Parameter.Value" \
    --output text \
    --region $AWS_REGION

# Restore the correct value
aws ssm put-parameter \
    --name "/cloudair/$USER_ID/region" \
    --value "$AWS_REGION" \
    --type String \
    --overwrite \
    --region $AWS_REGION
```

> SSM retains up to 100 versions per parameter (Standard tier). This audit trail is the compliance story: you can answer *"what was this config value last Tuesday at 14:32?"* without any additional tooling.

---

## Discussion

**Why not hard-code config in `application.py`?**
Hard-coded values end up in source control, in Docker image layers, and in every log statement that prints them. A stolen repository leaks production credentials. Factor III separates *what the code does* from *where it runs* — the same artifact deploys to dev, staging, and prod by varying only the environment.

**String vs SecureString — when to use which?**
Use `String` for non-sensitive topology data (table names, queue URLs, feature flags). Use `SecureString` for anything that grants access: passwords, API keys, OAuth tokens. If the value belongs to an external service or has a natural expiry/rotation requirement, consider Secrets Manager (Lab 3b) instead.

**SSM Parameter Store vs environment variable files (`.env`)**
A `.env` file must be provisioned on every instance/container at deploy time, creating a distribution problem. SSM is a network API: every instance reads it at startup, and a config change propagates the next time a process restarts — no re-provisioning required.

**Advanced: Parameter Store Advanced tier and policies**
Advanced-tier parameters (>4 KB, up to 8 KB) support **parameter policies** — TTL expiry and notification-on-change via EventBridge. This is how platform teams enforce credential rotation: a policy triggers an SNS alert if the value has not been updated within 90 days.

---

## Success Criteria (3 min)

- ✅ Four parameters exist under `/cloudair/$USER_ID/` — three `String`, one `SecureString`
- ✅ `aws ssm get-parameters-by-path --with-decryption` returns all four with plaintext values
- ✅ `python3 load_config.py` prints all parameters without error; `ext_api_key` is plaintext
- ✅ The monolith started successfully with SSM-sourced environment variables and returned `USER_ID` in the health-check response
- ✅ `get-parameter-history` shows at least two versions of the `region` parameter
