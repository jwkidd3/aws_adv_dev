#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Instructor pre-class setup for the shared "Developing on AWS" account.
#
# Provisions, idempotently:
#   1. RestrictToUsEast1   — customer-managed IAM policy denying every regional
#                            action outside us-east-1 (global services excluded).
#   2. LabRole             — the shared role students attach to their Cloud9 EC2
#                            in Lab 1a (EC2 trust), broad enough for every lab,
#                            region-locked to us-east-1, + an instance profile so
#                            it can be attached to an instance.
#   3. students group      — AdministratorAccess + RestrictToUsEast1 attached;
#                            every userN enrolled. Net effect: each student is a
#                            full administrator, but only inside us-east-1
#                            (explicit deny wins outside it; global services
#                            like IAM/STS stay available). This is intentional —
#                            students are admins by design, isolated by naming
#                            convention (USER_ID prefix), not by IAM.
#
# This account is the ORG MANAGEMENT account, so SCPs don't restrict it — the
# region lock is enforced with IAM policies instead. Root and the `admins`
# group are left untouched (root is never bound by IAM policy anyway).
#
# Usage:
#   ./setup-account.sh            # dry run — print every action, change nothing
#   ./setup-account.sh --apply    # actually create / attach
#
# Re-runnable: existing resources are detected and reused.
# -----------------------------------------------------------------------------
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REGION_POLICY_DOC="file://$HERE/restrict-region-us-east-1.json"
REGION_POLICY_NAME="RestrictToUsEast1"
LAB_ROLE="LabRole"
GROUP="students"

APPLY=0; [ "${1:-}" = "--apply" ] && APPLY=1
run(){ echo "+ $*"; if [ "$APPLY" = 1 ]; then "$@"; fi; }

ACCT=$(aws sts get-caller-identity --query Account --output text)
REGION_POLICY_ARN="arn:aws:iam::${ACCT}:policy/${REGION_POLICY_NAME}"
echo "Account $ACCT — $( [ "$APPLY" = 1 ] && echo APPLY || echo 'DRY RUN' )"

# --- scratch policy docs (trust + lab IAM perms) -----------------------------
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/labrole-trust.json" <<'JSON'
{ "Version":"2012-10-17",
  "Statement":[{"Effect":"Allow",
    "Principal":{"Service":"ec2.amazonaws.com"},
    "Action":"sts:AssumeRole"}] }
JSON
# The labs create/destroy IAM roles & policies (Lambda exec role, StudentLambdaRole,
# instance profiles) and pass roles to Lambda / API Gateway / Elastic Beanstalk /
# Step Functions. PowerUserAccess covers everything else; this inline policy adds
# just the IAM writes the labs need. Notes on PassRole's service list:
#   - elasticbeanstalk + ec2 — Lab 2b `eb create` passes aws-elasticbeanstalk-
#     service-role and the ec2 instance profile (also CreateServiceLinkedRole).
#   - states — Lab 5b's CloudFormation passes the saga state-machine execution
#     role to Step Functions (states.amazonaws.com).
cat > "$TMP/labrole-iam.json" <<'JSON'
{ "Version":"2012-10-17",
  "Statement":[
    {"Sid":"ManageLabRolesAndPolicies","Effect":"Allow",
     "Action":[
       "iam:CreateRole","iam:DeleteRole","iam:GetRole","iam:TagRole","iam:UntagRole",
       "iam:ListRoles","iam:ListRolePolicies","iam:ListAttachedRolePolicies",
       "iam:AttachRolePolicy","iam:DetachRolePolicy",
       "iam:PutRolePolicy","iam:DeleteRolePolicy","iam:GetRolePolicy",
       "iam:CreatePolicy","iam:DeletePolicy","iam:GetPolicy",
       "iam:ListPolicyVersions","iam:CreatePolicyVersion","iam:DeletePolicyVersion",
       "iam:CreateInstanceProfile","iam:DeleteInstanceProfile","iam:GetInstanceProfile",
       "iam:AddRoleToInstanceProfile","iam:RemoveRoleFromInstanceProfile"],
     "Resource":"*"},
    {"Sid":"PassRoleToLabServices","Effect":"Allow",
     "Action":"iam:PassRole","Resource":"*",
     "Condition":{"StringEquals":{"iam:PassedToService":[
       "lambda.amazonaws.com","apigateway.amazonaws.com",
       "elasticbeanstalk.amazonaws.com","ec2.amazonaws.com",
       "states.amazonaws.com"]}}},
    {"Sid":"ElasticBeanstalkServiceLinkedRole","Effect":"Allow",
     "Action":"iam:CreateServiceLinkedRole","Resource":"*",
     "Condition":{"StringEquals":{"iam:AWSServiceName":"elasticbeanstalk.amazonaws.com"}}}
  ] }
JSON

# --- 1. Region-lock managed policy -------------------------------------------
echo; echo "1) Region-lock policy"
if aws iam get-policy --policy-arn "$REGION_POLICY_ARN" >/dev/null 2>&1; then
  echo "   $REGION_POLICY_NAME exists ($REGION_POLICY_ARN)"
else
  run aws iam create-policy --policy-name "$REGION_POLICY_NAME" \
      --description "Deny all non-us-east-1 actions (global services excluded)" \
      --policy-document "$REGION_POLICY_DOC"
fi

# --- 2. LabRole + instance profile -------------------------------------------
echo; echo "2) LabRole (Cloud9 runtime role)"
if aws iam get-role --role-name "$LAB_ROLE" >/dev/null 2>&1; then
  echo "   role $LAB_ROLE exists"
else
  run aws iam create-role --role-name "$LAB_ROLE" \
      --description "Shared role students attach to their Cloud9 EC2 (region-locked to us-east-1)" \
      --assume-role-policy-document "file://$TMP/labrole-trust.json"
fi
run aws iam attach-role-policy --role-name "$LAB_ROLE" \
    --policy-arn arn:aws:iam::aws:policy/PowerUserAccess
run aws iam attach-role-policy --role-name "$LAB_ROLE" \
    --policy-arn "$REGION_POLICY_ARN"
run aws iam put-role-policy --role-name "$LAB_ROLE" \
    --policy-name LabRoleIamForLabs \
    --policy-document "file://$TMP/labrole-iam.json"
# Instance profile (EC2 attaches the profile, not the role directly)
if aws iam get-instance-profile --instance-profile-name "$LAB_ROLE" >/dev/null 2>&1; then
  echo "   instance profile $LAB_ROLE exists"
else
  run aws iam create-instance-profile --instance-profile-name "$LAB_ROLE"
fi
# add-role-to-instance-profile is a no-op error if already linked; guard it
if ! aws iam get-instance-profile --instance-profile-name "$LAB_ROLE" \
      --query 'InstanceProfile.Roles[0].RoleName' --output text 2>/dev/null | grep -qx "$LAB_ROLE"; then
  run aws iam add-role-to-instance-profile \
      --instance-profile-name "$LAB_ROLE" --role-name "$LAB_ROLE"
else
  echo "   role already in instance profile"
fi

# --- 3. students group + region lock on every userN --------------------------
echo; echo "3) students group + region lock on userN"
aws iam get-group --group-name "$GROUP" >/dev/null 2>&1 \
  && echo "   group $GROUP exists" \
  || run aws iam create-group --group-name "$GROUP"
# Students are full admins, but only in us-east-1: AdministratorAccess grants
# everything, RestrictToUsEast1's explicit deny claws back non-us-east-1 actions.
run aws iam attach-group-policy --group-name "$GROUP" \
    --policy-arn arn:aws:iam::aws:policy/AdministratorAccess
run aws iam attach-group-policy --group-name "$GROUP" --policy-arn "$REGION_POLICY_ARN"
for U in $(aws iam list-users \
            --query "Users[?starts_with(UserName,'user')].UserName" --output text); do
  run aws iam add-user-to-group --group-name "$GROUP" --user-name "$U"
done

# --- 4. Elastic Beanstalk roles (Lab 2b) -------------------------------------
# `eb create` needs two pre-existing roles. We create them ONCE here so 25
# students don't race to create the same global-named roles (and so LabRole's
# scoped PassRole works without LabRole also having to create them):
#   aws-elasticbeanstalk-service-role  — EB service role (env orchestration/health)
#   aws-elasticbeanstalk-ec2-role      — EC2 instance profile for the app instances
# The per-student DynamoDB grant the Bookings routes need is added by the
# monolith's .ebextensions at deploy time (scoped to Bookings-<userN>), so it is
# NOT attached here.
echo; echo "4) Elastic Beanstalk roles (Lab 2b)"
cat > "$TMP/eb-service-trust.json" <<'JSON'
{ "Version":"2012-10-17",
  "Statement":[{"Effect":"Allow",
    "Principal":{"Service":"elasticbeanstalk.amazonaws.com"},
    "Action":"sts:AssumeRole"}] }
JSON

EB_SVC="aws-elasticbeanstalk-service-role"
EB_EC2="aws-elasticbeanstalk-ec2-role"

if aws iam get-role --role-name "$EB_SVC" >/dev/null 2>&1; then
  echo "   role $EB_SVC exists"
else
  run aws iam create-role --role-name "$EB_SVC" \
      --description "Elastic Beanstalk service role (Lab 2b)" \
      --assume-role-policy-document "file://$TMP/eb-service-trust.json"
fi
run aws iam attach-role-policy --role-name "$EB_SVC" \
    --policy-arn arn:aws:iam::aws:policy/AWSElasticBeanstalkEnhancedHealth
run aws iam attach-role-policy --role-name "$EB_SVC" \
    --policy-arn arn:aws:iam::aws:policy/AWSElasticBeanstalkManagedUpdatesCustomerRolePolicy

if aws iam get-role --role-name "$EB_EC2" >/dev/null 2>&1; then
  echo "   role $EB_EC2 exists"
else
  run aws iam create-role --role-name "$EB_EC2" \
      --description "Elastic Beanstalk EC2 instance profile role (Lab 2b)" \
      --assume-role-policy-document "file://$TMP/labrole-trust.json"   # ec2 trust
fi
for P in AWSElasticBeanstalkWebTier AWSElasticBeanstalkWorkerTier \
         AWSElasticBeanstalkMulticontainerDocker; do
  run aws iam attach-role-policy --role-name "$EB_EC2" \
      --policy-arn "arn:aws:iam::aws:policy/$P"
done
if aws iam get-instance-profile --instance-profile-name "$EB_EC2" >/dev/null 2>&1; then
  echo "   instance profile $EB_EC2 exists"
else
  run aws iam create-instance-profile --instance-profile-name "$EB_EC2"
fi
if ! aws iam get-instance-profile --instance-profile-name "$EB_EC2" \
      --query 'InstanceProfile.Roles[0].RoleName' --output text 2>/dev/null | grep -qx "$EB_EC2"; then
  run aws iam add-role-to-instance-profile \
      --instance-profile-name "$EB_EC2" --role-name "$EB_EC2"
else
  echo "   role already in instance profile"
fi

echo
[ "$APPLY" = 0 ] && echo "(dry run — re-run with --apply to make changes)" || cat <<EOF
Done. Students in Lab 1a attach the '$LAB_ROLE' instance profile to their Cloud9
EC2 (Modify IAM role) and turn AMTC off. Everything is region-locked to us-east-1.
Lab 2b: the Elastic Beanstalk roles are pre-provisioned and LabRole can pass them.
EOF
