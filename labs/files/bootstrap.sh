#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Advanced Developing on AWS — "catch me up" / fast-forward bootstrap.
#
#   bash ~/environment/aws-adv-dev/bootstrap.sh <labId>
#
# Provisions every PREREQUISITE a given lab needs — idempotently — so a student
# can start at any point in a course where each lab builds on the last. Then it
# writes the expected shell variables to ~/.aws-adv-dev.env so the lab's commands
# resolve. Re-running is safe: existing resources are detected and reused.
#
#   labId ∈ { 1b 1c 2a 2b 3a 3b 4a 4b 5a 5b 6a 6b 7a 7b }
#
# It provisions each lab's PREREQUISITES (what that lab needs to run), not a full
# replay of every prior lab — leaf resources nothing depends on (the Lab 3b secret,
# the Lab 5b saga) are created by the student in that lab, not here. To reconstruct
# a near-complete footprint, bootstrap the heavy labs: 4b (EB+flights), 5b (table),
# 6b (messaging), 7b (cognito).
#
# To wipe a student clean first, use admin/reset-student.sh <userN> --apply.
#
# NOTE: deploying deep into the course is not instant — it creates real AWS
# resources (EB env ~5 min; each SAM stack ~2-3 min). bootstrap.sh 4b or 7b from
# a clean slate is ~10-15 min, but hands-off.
# -----------------------------------------------------------------------------
set -uo pipefail

LAB="${1:-}"
ENV_FILE="$HOME/.aws-adv-dev.env"
REGION="us-east-1"
HERE="$(cd "$(dirname "$0")" && pwd)"

[ -z "$LAB" ] && { echo "usage: bootstrap.sh <labId>   e.g. bootstrap.sh 6a" >&2; exit 2; }

# --- identity & USER_ID guard ------------------------------------------------
# In Cloud9 the SDK runs as the shared LabRole, so we can't derive a per-student
# ID from the caller. USER_ID must be set (Lab 1b). Refuse on empty/LabRole.
[ -f "$ENV_FILE" ] && source "$ENV_FILE" || true
ACCT="$(aws sts get-caller-identity --query Account --output text)"
if [ -z "${USER_ID:-}" ] || [ "${USER_ID}" = "LabRole" ]; then
  cat >&2 <<EOF
✋ USER_ID is not set (or is 'LabRole'). Set it first, e.g.:
    echo 'export USER_ID=user1' >> $ENV_FILE
    echo 'export AWS_REGION=$REGION' >> $ENV_FILE && source $ENV_FILE
then re-run: bash $HERE/bootstrap.sh $LAB
EOF
  exit 1
fi
U="$USER_ID"

# --- helpers -----------------------------------------------------------------
touch "$ENV_FILE"
set_var(){ local n="$1" v="$2"
  grep -q "^export $n=" "$ENV_FILE" && sed -i "s|^export $n=.*|export $n=$v|" "$ENV_FILE" || echo "export $n=$v" >> "$ENV_FILE"; }
have(){ "$@" >/dev/null 2>&1; }
need(){ command -v "$1" >/dev/null 2>&1 || { echo "✋ '$1' not found — required for lab $LAB. Complete Lab 1a setup first." >&2; exit 1; }; }
log(){ echo "  $*"; }

set_var AWS_REGION "$REGION"; set_var USER_ID "$U"; set_var ACCT "$ACCT"
export AWS_REGION="$REGION" ACCT="$ACCT"
echo "▶ bootstrapping lab $LAB  —  USER_ID=$U  account=$ACCT  region=$REGION"

# =============================== ensures =====================================

ensure_base(){   # Lab 2a — S3 + Bookings table + SSM
  local STACK="cloudair-$U-base"
  if have aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION"; then
    log "✓ base stack $STACK"
  else
    log "+ deploying base stack $STACK"
    aws cloudformation deploy --stack-name "$STACK" --template-file "$HERE/lab2/base-stack.yaml" \
      --parameter-overrides UserId="$U" Environment=dev --capabilities CAPABILITY_NAMED_IAM --region "$REGION" >/dev/null
  fi
  set_var ASSETS_BUCKET  "cloudair-$U-assets"
  set_var BOOKINGS_TABLE "Bookings-$U"
}

ensure_ssm(){    # Lab 3a — config params
  log "+ SSM config params under /cloudair/$U/"
  aws ssm put-parameter --name "/cloudair/$U/flights_table" --value "Bookings-$U" --type String --overwrite --region "$REGION" >/dev/null
  aws ssm put-parameter --name "/cloudair/$U/assets_bucket" --value "cloudair-$U-assets" --type String --overwrite --region "$REGION" >/dev/null
  aws ssm put-parameter --name "/cloudair/$U/region" --value "$REGION" --type String --overwrite --region "$REGION" >/dev/null
  have aws ssm get-parameter --name "/cloudair/$U/ext_api_key" --region "$REGION" \
    || aws ssm put-parameter --name "/cloudair/$U/ext_api_key" --value "cloudair-demo-bootstrap" --type SecureString --overwrite --region "$REGION" >/dev/null
}

ensure_eb(){     # Lab 2b — Flask monolith on Elastic Beanstalk
  need eb
  if aws elasticbeanstalk describe-environments --environment-names "cloudair-$U-env" --region "$REGION" \
       --query "Environments[?Status=='Ready']" --output text 2>/dev/null | grep -q .; then
    log "✓ EB env cloudair-$U-env"
  else
    log "+ launching EB monolith cloudair-$U-env (~5 min)"
    ( cd "$HERE/lab2/monolith"
      [ -f .elasticbeanstalk/config.yml ] || printf 'n\n' | eb init "cloudair-$U" -p "Python 3.11 running on 64bit Amazon Linux 2023" --region "$REGION" >/dev/null 2>&1
      eb create "cloudair-$U-env" --instance-type t3.micro --single --region "$REGION" \
        --envvars "USER_ID=$U,BOOKINGS_TABLE=Bookings-$U,AWS_REGION=$REGION" >/dev/null 2>&1 )
  fi
  set_var EB_URL "$(aws elasticbeanstalk describe-environments --environment-names "cloudair-$U-env" --query "Environments[0].CNAME" --output text --region "$REGION")"
}

ensure_flights(){ # Lab 4a — Flights SAM stack (Lambda + HTTP API). $1=MonolithUrl (default placeholder)
  need sam
  local MURL="${1:-REPLACE_WITH_EB_CNAME}"
  if have aws cloudformation describe-stacks --stack-name "cloudair-$U-flights" --region "$REGION"; then
    log "✓ flights stack cloudair-$U-flights"
  else
    log "+ building + deploying flights stack (~2-3 min)"
    ( cd "$HERE/lab4" && sam build >/dev/null 2>&1 \
      && sam deploy --stack-name "cloudair-$U-flights" \
           --parameter-overrides UserId="$U" BookingsTableName="Bookings-$U" MonolithUrl="$MURL" \
           --capabilities CAPABILITY_IAM --resolve-s3 --no-confirm-changeset --no-fail-on-empty-changeset --region "$REGION" >/dev/null 2>&1 )
  fi
  local API; API=$(aws cloudformation describe-stacks --stack-name "cloudair-$U-flights" \
    --query "Stacks[0].Outputs[?OutputKey=='FlightsApiUrl'].OutputValue" --output text --region "$REGION" 2>/dev/null)
  set_var FLIGHTS_API_URL "$API"; set_var API_URL "$API"
}

ensure_singletable(){ # Lab 5a — CloudAir single table + items
  if have aws dynamodb describe-table --table-name "CloudAir-$U" --region "$REGION"; then
    log "✓ single table CloudAir-$U"
  else
    log "+ creating + loading CloudAir-$U"
    ( cd "$HERE/lab5" && USER_ID="$U" python3 create_table.py >/dev/null 2>&1 && USER_ID="$U" python3 bulk_load.py >/dev/null 2>&1 )
  fi
  set_var SINGLE_TABLE "CloudAir-$U"
}

ensure_messaging(){ # Lab 6a — SQS (+DLQ) + SNS topic + subscription + queue policy
  local DLQ_URL QUEUE_URL DLQ_ARN QUEUE_ARN TOPIC_ARN
  DLQ_URL=$(aws sqs get-queue-url --queue-name "cloudair-$U-bookings-dlq" --query QueueUrl --output text --region "$REGION" 2>/dev/null)
  [ -z "$DLQ_URL" ] || [ "$DLQ_URL" = "None" ] && DLQ_URL=$(aws sqs create-queue --queue-name "cloudair-$U-bookings-dlq" --attributes '{"MessageRetentionPeriod":"1209600"}' --query QueueUrl --output text --region "$REGION")
  DLQ_ARN=$(aws sqs get-queue-attributes --queue-url "$DLQ_URL" --attribute-names QueueArn --query "Attributes.QueueArn" --output text --region "$REGION")
  QUEUE_URL=$(aws sqs get-queue-url --queue-name "cloudair-$U-bookings" --query QueueUrl --output text --region "$REGION" 2>/dev/null)
  if [ -z "$QUEUE_URL" ] || [ "$QUEUE_URL" = "None" ]; then
    QUEUE_URL=$(aws sqs create-queue --queue-name "cloudair-$U-bookings" \
      --attributes "{\"VisibilityTimeout\":\"30\",\"MessageRetentionPeriod\":\"86400\",\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"$DLQ_ARN\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}" \
      --query QueueUrl --output text --region "$REGION")
  fi
  QUEUE_ARN=$(aws sqs get-queue-attributes --queue-url "$QUEUE_URL" --attribute-names QueueArn --query "Attributes.QueueArn" --output text --region "$REGION")
  TOPIC_ARN=$(aws sns create-topic --name "cloudair-$U-bookings" --query TopicArn --output text --region "$REGION")
  local SUB_ARN; SUB_ARN=$(aws sns subscribe --topic-arn "$TOPIC_ARN" --protocol sqs --notification-endpoint "$QUEUE_ARN" --query SubscriptionArn --output text --region "$REGION" 2>/dev/null)
  aws sqs set-queue-attributes --queue-url "$QUEUE_URL" --region "$REGION" --attributes "{\"Policy\":\"{\\\"Version\\\":\\\"2012-10-17\\\",\\\"Statement\\\":[{\\\"Effect\\\":\\\"Allow\\\",\\\"Principal\\\":{\\\"Service\\\":\\\"sns.amazonaws.com\\\"},\\\"Action\\\":\\\"sqs:SendMessage\\\",\\\"Resource\\\":\\\"$QUEUE_ARN\\\",\\\"Condition\\\":{\\\"ArnEquals\\\":{\\\"aws:SourceArn\\\":\\\"$TOPIC_ARN\\\"}}}]}\"}" >/dev/null 2>&1
  log "✓ SQS/SNS messaging (queue + DLQ + topic)"
  set_var QUEUE_URL "$QUEUE_URL"; set_var QUEUE_ARN "$QUEUE_ARN"
  set_var DLQ_URL "$DLQ_URL"; set_var DLQ_ARN "$DLQ_ARN"
  set_var TOPIC_ARN "$TOPIC_ARN"; set_var SUBSCRIPTION_ARN "$SUB_ARN"
}

ensure_cognito(){ # Lab 7a — user pool + client + user + token (NOT the authorizer; that's a 7a edit)
  local POOL_ID CLIENT_ID
  POOL_ID=$(aws cognito-idp list-user-pools --max-results 60 --region "$REGION" --query "UserPools[?Name=='cloudair-$U-pool'].Id | [0]" --output text 2>/dev/null)
  if [ -z "$POOL_ID" ] || [ "$POOL_ID" = "None" ]; then
    log "+ creating Cognito pool/client/user"
    POOL_ID=$(aws cognito-idp create-user-pool --pool-name "cloudair-$U-pool" \
      --policies '{"PasswordPolicy":{"MinimumLength":8,"RequireUppercase":true,"RequireLowercase":true,"RequireNumbers":true,"RequireSymbols":false}}' \
      --auto-verified-attributes email --username-attributes email --query "UserPool.Id" --output text --region "$REGION")
  else log "✓ Cognito pool cloudair-$U-pool"; fi
  CLIENT_ID=$(aws cognito-idp list-user-pool-clients --user-pool-id "$POOL_ID" --query "UserPoolClients[?ClientName=='cloudair-$U-client'].ClientId | [0]" --output text --region "$REGION" 2>/dev/null)
  if [ -z "$CLIENT_ID" ] || [ "$CLIENT_ID" = "None" ]; then
    CLIENT_ID=$(aws cognito-idp create-user-pool-client --user-pool-id "$POOL_ID" --client-name "cloudair-$U-client" \
      --no-generate-secret --explicit-auth-flows ALLOW_USER_PASSWORD_AUTH ALLOW_REFRESH_TOKEN_AUTH --query "UserPoolClient.ClientId" --output text --region "$REGION")
  fi
  aws cognito-idp admin-create-user --user-pool-id "$POOL_ID" --username "$U@cloudair.example" --temporary-password "TempPass1!" --message-action SUPPRESS --region "$REGION" >/dev/null 2>&1 || true
  aws cognito-idp admin-set-user-password --user-pool-id "$POOL_ID" --username "$U@cloudair.example" --password "CloudAir1!" --permanent --region "$REGION" >/dev/null 2>&1 || true
  local TOK; TOK=$(aws cognito-idp initiate-auth --auth-flow USER_PASSWORD_AUTH \
    --auth-parameters USERNAME="$U@cloudair.example",PASSWORD="CloudAir1!" --client-id "$CLIENT_ID" --region "$REGION" \
    --query "AuthenticationResult.IdToken" --output text 2>/dev/null)
  set_var POOL_ID "$POOL_ID"; set_var CLIENT_ID "$CLIENT_ID"; [ -n "$TOK" ] && set_var ID_TOKEN "$TOK"
  log "ℹ the Flights API is left OPEN — adding the JWT authorizer is the Lab 7a template edit."
}

# =============================== lab graph ===================================
case "$LAB" in
  1b|1c)  log "(no AWS resources required — env vars set)" ;;
  2a)     log "(Lab 2a creates the base stack itself)"; set_var BOOKINGS_TABLE "Bookings-$U" ;;
  2b)     ensure_base ;;
  3a)     ensure_base ;;
  3b)     ensure_base; ensure_ssm ;;
  4a)     ensure_base ;;
  4b)     ensure_base; ensure_eb; ensure_flights ;;
  5a)     ensure_base ;;
  5b)     ensure_base; ensure_singletable ;;
  6a)     ensure_base ;;
  6b)     ensure_base; ensure_messaging ;;
  7a)     ensure_base; ensure_flights ;;
  7b)     ensure_base; ensure_flights; ensure_cognito ;;
  *)      echo "unknown labId '$LAB' — valid: 1b 1c 2a 2b 3a 3b 4a 4b 5a 5b 6a 6b 7a 7b" >&2; exit 2 ;;
esac

echo "✅ lab $LAB prerequisites ready. Run:  source $ENV_FILE"
