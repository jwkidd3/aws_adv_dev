# 🧪 Lab 1b — First SDK Call in Cloud9

*Hands-On Lab · 30 min · SDK · Day 1 — Environment Setup*

## Objectives (2 min)

- Run your first SDK program from inside Cloud9
- See the credential provider chain pick up the instance's credentials
- Create a persistent session file for shell variables

## Prerequisites (3 min)

- Lab 1a complete — Cloud9 open, `~/environment/aws-adv-dev/lab1` folder exists

> **Starting fresh?** `bash ~/environment/aws-adv-dev/bootstrap.sh 1b` derives `$USER_ID` from your caller identity and exports it to `~/.aws-adv-dev.env`.

## Step 1 — Review smoke_test.py (7 min)

> Open `~/environment/aws-adv-dev/lab1/smoke_test.py` in the Cloud9 editor. It's the tiniest SDK program that proves your credentials are live:

- Imports `boto3` (installed in Lab 1a Step 5)
- Calls `sts:GetCallerIdentity` and prints the ARN
- Calls `s3:ListBuckets` and prints bucket names

> No `aws configure`, no access keys in the code — the SDK finds the Cloud9 instance's credentials via the provider chain.

## Step 2 — Run It (6 min)

```bash
cd ~/environment/aws-adv-dev/lab1
python3 smoke_test.py
```

> Expected output: your IAM user ARN plus the names of any buckets the account owns.

## Step 3 — CLI Smoke Tests (5 min)

```bash
aws s3 ls
aws dynamodb list-tables
aws lambda list-functions
```

- Lists should return (most will be empty — you haven't created anything yet).
- Some calls may fail with `AccessDenied` — you'll test denies in Lab 1c.

## Step 4 — Create the Session File (7 min)

> Every lab after this one saves variables to `~/.aws-adv-dev.env`. Set it up once — in the Cloud9 terminal:

```bash
cat > ~/.aws-adv-dev.env <<'EOF'
export AWS_REGION=us-east-1
export USER_ID=user1    # *** SET THIS TO YOUR ASSIGNED USER (user2, user3, …) ***
EOF

# Capture your account ID once — every other lab uses it
ACCT=$(aws sts get-caller-identity --query Account --output text)
echo "export ACCT=$ACCT" >> ~/.aws-adv-dev.env

echo 'source ~/.aws-adv-dev.env' >> ~/.bashrc
source ~/.aws-adv-dev.env
echo "You are $USER_ID in $AWS_REGION (account $ACCT)"
```

> This one is small enough for a terminal heredoc. Re-source with `source ~/.aws-adv-dev.env` if you open a new terminal.

> ⚠️ **Use your own `USER_ID`.** The whole class shares one AWS account; your user ID is what keeps your buckets, table, and stack separate from everyone else's. If you skip this, `bootstrap.sh` refuses to run rather than collide on shared names.

## Success Criteria (2 min)

- ✅ SDK program runs from Cloud9 and prints your IAM user ARN
- ✅ CLI lists S3, DynamoDB, Lambda successfully (mostly empty)
- ✅ `~/.aws-adv-dev.env` created and auto-sourced from `.bashrc`
- ✅ `$USER_ID` is set to your assigned user
