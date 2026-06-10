# 🧪 Lab 1c — Test Permissions & Author IAM Policy

*Hands-On Lab · 45 min · Console + CLI · Day 1 — Environment Setup*

## Objectives (3 min)

- Observe an intentional "access denied" and read the error message
- Write a least-privilege policy for S3 delete scoped to your user prefix
- Attach the policy to your user
- Verify the new permission works end-to-end

## Prerequisites (3 min)

- Lab 1b complete — Cloud9 open, SDK smoke test passes
- `aws sts get-caller-identity` returns your assumed-role ARN

> **Starting fresh?** `bash ~/environment/aws-adv-dev/bootstrap.sh 1b` derives and exports `$USER_ID` / `$ACCT`.

## Step 1 — Test a Denied Call (7 min)

```bash
aws iam create-user \
    --user-name test-blocked-$USER_ID 
```

- Expected: `AccessDenied` — your role cannot create IAM users
- Read the full error; it names your role ARN and the action
- This is the safety net — even a misconfigured lab can't change IAM identities
- `$USER_ID` keeps the user name unique per student so names can't collide in the shared account

## Step 2 — Confirm the Gap You'll Fill (7 min)

```bash
# Create a throwaway bucket in your prefix ($USER_ID set by Lab 1b)
PROBE=student-$USER_ID-probe-$(date +%s)
aws s3 mb s3://$PROBE

# Try to delete it — fails with AccessDenied (no delete rights yet)
aws s3 rb s3://$PROBE
```

## Step 3 — Author the Policy (7 min)

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "s3:DeleteBucket",
      "s3:DeleteObject",
      "s3:ListBucket"
    ],
    "Resource": [
      "arn:aws:s3:::student-user1-*",
      "arn:aws:s3:::student-user1-*/*"
    ]
  }]
}
```

> Save as `student-allow-bucket-delete.json` — replace `user1` with your user.

## Step 4 — Attach to Your User (6 min)

1. Console → IAM → **Policies** → **Create policy** → JSON tab
2. Paste the JSON. Name: `StudentAllowBucketDelete-user1`
3. Attach to your user: IAM → Users → `user1` → **Add permissions** → **Attach policies directly**

> CLI alternative:

```bash
aws iam create-policy --policy-name StudentAllowBucketDelete-$USER_ID \
    --policy-document file://student-allow-bucket-delete.json   # (may itself fail; fall back to console)
```

## Step 5 — Verify (6 min)

```bash
# Retry the delete from Step 2 — now succeeds
aws s3 rb s3://$PROBE

# Confirm you still can't delete someone else's bucket
aws s3 rb s3://another-student-bucket
# → AccessDenied (exactly what we want)
```

## Discussion (3 min)

- Why scope the `Resource` to your prefix instead of `"*"`?
- What would need to change to run this in production?
- If the CLI succeeds but your SDK code fails with the same Cloud9 role — what's the most likely cause?

## Success Criteria (3 min)

- ✅ `iam:CreateUser` still fails — safety net works
- ✅ `StudentAllowBucketDelete-userN` exists and is attached
- ✅ You can delete buckets in your prefix
- ✅ You still can't delete buckets outside your prefix
