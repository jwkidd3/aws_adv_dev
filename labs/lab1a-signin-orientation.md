# 🧪 Lab 1a — Sign In & Create Your Cloud9 Environment

*Hands-On Lab · 30 min · Console · Day 1 — Environment Setup*

## Objectives & Access (2 min)

- Sign into the class account
- Create your own Cloud9 IDE (m5.large, SSH)
- Attach `LabRole` and turn off managed temporary credentials
- Clone the course repo and verify the files landed

> **Console:** `https://kiddcorp.signin.aws.amazon.com/console`
> **User:** `user1`, `user2`, … assigned at class start · **Region:** `us-east-1`

## Step 1 — Sign In (2 min)

1. Open the console URL in an incognito window
2. Sign in with your assigned user and password
3. Top-right region selector → **US East (N. Virginia) us-east-1**

## Step 2 — Create Your Cloud9 Environment (10 min)

1. Console search → **Cloud9** → **Create environment**
2. Name: `aws-adv-dev-user1` (replace with your user)
3. Environment type: **New EC2 instance**
4. Instance type: **m5.large**
5. Platform: **Amazon Linux 2023**
6. Timeout: **30 minutes**
7. Connection: **Secure Shell (SSH)** ← not SSM
8. Network: default VPC, any public subnet
9. **Create** — provisioning takes ~3 min

## Step 3 — Attach LabRole to Your Cloud9 EC2 (5 min)

> By default Cloud9 uses **AWS Managed Temporary Credentials** (AMTC), which block several IAM, STS, and Lambda calls our labs need. We fix this by pointing the underlying EC2 at the pre-provisioned `LabRole` and turning AMTC off.

1. Open the **EC2** console → **Instances**
2. Find the instance named `aws-cloud9-aws-adv-dev-userN-…` — that's the EC2 behind your Cloud9
3. Select it → **Actions** → **Security** → **Modify IAM role**
4. Choose `LabRole` → **Update IAM role**

## Step 4 — Disable Managed Credentials in Cloud9 (2 min)

1. Back in the Cloud9 IDE, top-left gear icon → **Preferences**
2. Left panel → **AWS Settings** → **Credentials**
3. Toggle **AWS managed temporary credentials** to **OFF**
4. Close the Preferences tab

> With AMTC off, the SDK/CLI fall through to IMDS and pick up `LabRole`'s credentials — no `aws configure`, no keys on disk. If the Cloud9 instance is stopped and restarted, AMTC stays off; if you delete and recreate the Cloud9, redo both steps.

## Step 5 — Smoke Test & Install boto3 (3 min)

> In the Cloud9 terminal (bottom pane):

```bash
aws --version
aws sts get-caller-identity
# Arn: arn:aws:sts::...:assumed-role/LabRole/i-0abc…
# ← confirms you're now running as LabRole, not AMTC

# boto3 isn't on the default AL2023 image — install once
pip3 install --user boto3
python3 -c "import boto3; print(boto3.__version__)"
```

> If the ARN still shows `user/user1` or an AMTC session, redo Step 4 — Cloud9 sometimes needs a second toggle. `--user` installs boto3 into `~/.local`, which is on Python's default import path.

## Step 6 — Clone the Course Repo & Verify (3 min)

```bash
cd ~/environment
git clone https://github.com/jwkidd3/aws_adv_dev
cp -r aws_adv_dev/labs/files ./aws-adv-dev

# Verify — raise your hand if any line shows MISS
cd ~/environment/aws-adv-dev
for f in lab1/smoke_test.py \
         lab2/base-stack.yaml lab2/monolith/application.py \
         lab3/load_config.py lab3/get_secret.py lab3/params.json \
         lab4/template.yaml lab4/src/app.py \
         lab5/create_table.py lab5/items.json lab5/booking-saga.asl.json \
         lab5/handlers.py lab5/template.yaml \
         lab6/publish_booking.py lab6/worker.py lab6/put_event.py \
         lab7/xray_handler.py bootstrap.sh; do
  [ -f "$f" ] && echo "OK   $f" || echo "MISS $f"
done
chmod +x ~/environment/aws-adv-dev/bootstrap.sh
```

> `bootstrap.sh` is the "catch me up" script — if you ever fall behind, `bash ~/environment/aws-adv-dev/bootstrap.sh <labId>` creates-or-reuses every resource that lab needs. Each subsequent lab has a reminder.

## Success Criteria (2 min)

- ✅ Cloud9 `aws-adv-dev-userN` created on **m5.large** with **SSH**
- ✅ Underlying EC2 instance has `LabRole` attached and AMTC is off
- ✅ `aws sts get-caller-identity` returns an `assumed-role/LabRole/…` ARN
- ✅ All 7 verify lines show `OK`

> Class conventions — shown now, enforced in later labs:

- **Resource prefix:** everything you create starts with your user — `student-user1-*`, `Items-user1`, `lab4-user1`. IAM enforces this; off-prefix actions return `AccessDenied`.
- **Editor vs. terminal:** source/config files are authored in the Cloud9 editor; commands ≤ ~5 lines go into the terminal.
