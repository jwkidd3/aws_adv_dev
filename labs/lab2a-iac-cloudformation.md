# 🧪 Lab 2a — Infrastructure as Code: the Cloud Air Baseline

*Hands-On Lab · 45 min · Console + CLI · Day 1 — Infrastructure as Code*

## Objectives (3 min)

- Read and understand a CloudFormation template before deploying it
- Validate a template using the CLI (`aws cloudformation validate-template`)
- Deploy a stack with `aws cloudformation deploy` using a parameter override
- Inspect stack outputs, resources, and events in the Console and CLI
- Introduce the concept of **drift detection** — what happens when someone manually changes a resource outside CloudFormation

> Lab 2b uses the DynamoDB table this stack creates. Do not delete the stack until the end of Day 1.

---

## Prerequisites (3 min)

- Lab 1b complete — `~/.aws-adv-dev.env` exists and `$USER_ID` is set
- Cloud9 terminal open; repo cloned to `~/environment/aws-adv-dev`

```bash
source ~/.aws-adv-dev.env
echo "USER_ID=$USER_ID  ACCT=$ACCT  REGION=$AWS_REGION"
```

> **Starting fresh?** `bash ~/environment/aws-adv-dev/bootstrap.sh 2a` sets `$USER_ID`, `$ACCT`, and `$AWS_REGION` in `~/.aws-adv-dev.env` and verifies the repo is present.

---

## Step 1 — Review the Template (8 min)

> Open `~/environment/aws-adv-dev/lab2/base-stack.yaml` in the Cloud9 editor (double-click it in the file tree).

Work through each top-level section:

| Section | What it defines |
|---------|-----------------|
| `Parameters` | `UserId` — student-scoped name prefix; `Environment` — dev/test/prod tag |
| `Resources` | S3 bucket `cloudair-<UserId>-assets`, DynamoDB table `Bookings-<UserId>`, three SSM parameters |
| `Outputs` | Bucket name/ARN, table name/ARN/stream ARN, SSM path prefix — all exported for cross-stack use |

Key things to note in the template:

- **`!Sub "cloudair-${UserId}-assets"`** — intrinsic function that interpolates the parameter into the bucket name. Every resource is scoped to your `UserId` so 20 students can run the same template simultaneously without collisions.
- **`BillingMode: PAY_PER_REQUEST`** on the DynamoDB table — no capacity planning required for a classroom environment; you pay only for the reads/writes you actually perform.
- **SSM parameters** under `/cloudair/<UserId>/…` — the running Flask app will read its config from here rather than from environment variables baked into a config file (Twelve-Factor Factor III).
- **`StreamViewType: NEW_AND_OLD_IMAGES`** on the table — streams are enabled now so Lab 6 can attach a consumer without a stack update.

---

## Step 2 — Validate the Template (5 min)

```bash
source ~/.aws-adv-dev.env

aws cloudformation validate-template \
    --template-body file://~/environment/aws-adv-dev/lab2/base-stack.yaml \
    --region $AWS_REGION
```

A successful response prints the parameter descriptions back as JSON. Any YAML syntax error or unsupported resource type produces an error here — **before** you spend time waiting for a deploy to fail.

> CloudFormation `validate-template` only checks syntax and structure. It cannot verify that an S3 bucket name is globally unique or that you have IAM permission to create each resource. You will see those failures (if any) in the stack events.

---

## Step 3 — Deploy the Stack (12 min)

```bash
source ~/.aws-adv-dev.env

STACK_NAME="cloudair-$USER_ID-base"

aws cloudformation deploy \
    --stack-name $STACK_NAME \
    --template-file ~/environment/aws-adv-dev/lab2/base-stack.yaml \
    --parameter-overrides UserId=$USER_ID Environment=dev \
    --capabilities CAPABILITY_NAMED_IAM \
    --region $AWS_REGION \
    --tags Project=CloudAir Owner=$USER_ID
```

> `--capabilities CAPABILITY_NAMED_IAM` is required when a template creates or modifies IAM resources with custom names. This template does not create IAM resources, but it is good practice to include it — CloudFormation will reject the deploy if the flag is missing for templates that do.

The CLI polls until the stack reaches `CREATE_COMPLETE` (or fails). While it deploys, switch to the Console:

1. Open **CloudFormation → Stacks** — find `cloudair-$USER_ID-base`
2. Click the stack name → **Events** tab — watch resources create in order
3. Notice CloudFormation creates the S3 bucket first, then the DynamoDB table, then the SSM parameters — the dependency graph drives ordering

> If the deploy fails, the **Events** tab shows which resource failed and the error message (e.g., `BucketAlreadyExists` if you re-ran without changing the name). CloudFormation automatically rolls back to the previous stable state.

---

## Step 4 — Inspect Stack Outputs and Resources (8 min)

**Via CLI:**

```bash
source ~/.aws-adv-dev.env
STACK_NAME="cloudair-$USER_ID-base"

# All outputs
aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query "Stacks[0].Outputs" \
    --output table \
    --region $AWS_REGION

# Save the bucket name and table name for later labs
ASSETS_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query "Stacks[0].Outputs[?OutputKey=='StaticAssetsBucketName'].OutputValue" \
    --output text --region $AWS_REGION)

BOOKINGS_TABLE=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query "Stacks[0].Outputs[?OutputKey=='BookingsTableName'].OutputValue" \
    --output text --region $AWS_REGION)

echo "export ASSETS_BUCKET=$ASSETS_BUCKET"   >> ~/.aws-adv-dev.env
echo "export BOOKINGS_TABLE=$BOOKINGS_TABLE" >> ~/.aws-adv-dev.env
source ~/.aws-adv-dev.env
echo "Bucket: $ASSETS_BUCKET   Table: $BOOKINGS_TABLE"
```

**Via Console:**

1. **CloudFormation → Stacks → cloudair-$USER_ID-base → Outputs** — review every exported value
2. **Resources tab** — each logical ID links to the actual AWS resource; click the DynamoDB table link
3. Confirm the table has `PAY_PER_REQUEST` billing mode and a GSI named `userId-index`

**Verify the SSM parameters:**

```bash
aws ssm get-parameters-by-path \
    --path /cloudair/$USER_ID \
    --query "Parameters[*].{Name:Name,Value:Value}" \
    --output table \
    --region $AWS_REGION
```

---

## Step 5 — Drift Detection (5 min)

Drift detection answers: *"Has anyone changed this resource outside of CloudFormation?"*

1. Manually rename a tag on your S3 bucket via the Console:
   - **S3 → cloudair-$USER_ID-assets → Properties → Tags → Edit**
   - Change `Environment` value from `dev` to `manually-changed`
   - Save

2. Back in **CloudFormation → cloudair-$USER_ID-base → Stack actions → Detect drift**

3. After the check completes (30–60 s), click **View drift results**

4. The bucket shows `MODIFIED`; click it to see the **expected** vs **actual** value for the tag

> CloudFormation tracks the **desired state** in its own datastore. Any out-of-band change shows as drift. In production, drift alerts are wired to EventBridge → SNS so ops teams know when someone has edited infrastructure without going through the pipeline.

**Reset (optional):** revert the tag in S3 manually, or run `aws cloudformation deploy` again — CloudFormation will overwrite the tag back to `dev`.

---

## Discussion

- **Why IaC over the Console?** This stack took ~2 min to review and ~3 min to deploy. A team of 20 each got an identical, independently-named environment. Console click-ops at that scale is error-prone and unauditable.
- **`aws cloudformation deploy` vs `create-stack`/`update-stack`:** `deploy` is an idempotent wrapper — if the stack does not exist it calls `create-stack`; if it does exist it calls `update-stack`; if there are no changes it exits cleanly. Use it in CI/CD pipelines.
- **Outputs and cross-stack references:** The exported names (e.g., `cloudair-$USER_ID-bookings-table`) let other stacks import values with `!ImportValue` instead of hard-coding resource names.

---

## Success Criteria (3 min)

- ✅ `aws cloudformation validate-template` returned the parameters list without error
- ✅ Stack `cloudair-$USER_ID-base` is in `CREATE_COMPLETE` state in `us-east-1`
- ✅ S3 bucket `cloudair-$USER_ID-assets` exists with versioning enabled and Block Public Access on
- ✅ DynamoDB table `Bookings-$USER_ID` exists with `PAY_PER_REQUEST` billing and a `userId-index` GSI
- ✅ Three SSM parameters visible under `/cloudair/$USER_ID/` path
- ✅ `$ASSETS_BUCKET` and `$BOOKINGS_TABLE` saved to `~/.aws-adv-dev.env`
- ✅ Drift detection flagged the manually-modified bucket tag as `MODIFIED`
