# Instructor / Account Setup

One-time-per-account setup for the shared **Developing on AWS** training account.
Run from a machine with admin credentials for the account (not from a student
Cloud9).

## What it provisions

`setup-account.sh` is idempotent and **dry-run by default**:

```bash
./setup-account.sh            # print every action, change nothing
./setup-account.sh --apply    # create / attach for real
```

| # | Resource | Purpose |
|---|----------|---------|
| 1 | `RestrictToUsEast1` (managed policy) | Denies every regional action where `aws:RequestedRegion != us-east-1`. Global services (IAM, STS, Route 53, CloudFront, WAF, Shield, Organizations, billing) are excluded so the labs keep working. |
| 2 | `LabRole` (+ instance profile) | The shared role students attach to their Cloud9 EC2 in Lab 1a. Trusts `ec2.amazonaws.com`; carries `PowerUserAccess` + an inline policy for the IAM writes the labs need (create/delete roles & policies, instance profiles, `PassRole` to Lambda/API Gateway) + the region lock. |
| 3 | `students` group | `AdministratorAccess` **+** `RestrictToUsEast1` attached; every `userN` enrolled. Net effect: each student is a **full administrator scoped to us-east-1** (admin everywhere in-region; denied in other regions; global services still work). Students are admins by design — isolated by the `USER_ID` naming convention, not by IAM. |

Root and the `admins` group are left untouched (root is never bound by an IAM
policy anyway, so you can't lock yourself out).

## Why an IAM policy and not an SCP

This account is the **management account** of its AWS Organization, and SCPs do
**not** restrict the management account. So the region lock is enforced with IAM
policies (on the `students` group and `LabRole`) rather than a Service Control
Policy. If you ever move the students into a dedicated *member* account, the same
`restrict-region-us-east-1.json` document can be reused as an SCP there.

## Files

- `setup-account.sh` — the idempotent setup runner
- `restrict-region-us-east-1.json` — the region-lock policy document (also valid as an SCP in a member account)

## Verifying

After `--apply`:

```bash
# Region lock attached?
aws iam list-attached-group-policies --group-name students
aws iam list-attached-role-policies  --role-name LabRole

# Negative test as a student: this should be DENIED
aws ec2 describe-instances --region us-west-2      # AccessDenied (RequestedRegion)
aws ec2 describe-instances --region us-east-1      # works
```
