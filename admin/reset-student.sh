#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# reset-student.sh — tear down ONE student's entire Cloud Air footprint so they
# can restart clean (or so an instructor can recycle a userN between cohorts).
#
#   ./reset-student.sh user12            # DRY RUN — list what would be deleted
#   ./reset-student.sh user12 --apply    # actually delete
#
# Deletes everything labs 2–7 create for a single userN, in dependency order:
#   SAM stacks (flights, saga) · Cognito pool · EventBridge bus/rule/archive ·
#   SQS queues + SNS topic · worker Lambda + role · CloudAir/ProcessedBookings
#   tables · Secrets Manager secret · /cloudair/<user>/ SSM params · Elastic
#   Beanstalk env + app · base CloudFormation stack (S3 + Bookings table).
#
# Best-effort and idempotent: missing resources are skipped, not fatal. Resource
# names are derived deterministically from userN, so nothing else is touched.
# Pairs with bootstrap.sh, which fast-forwards a student INTO any lab.
# -----------------------------------------------------------------------------
set -uo pipefail   # deliberately NOT -e: continue past already-gone resources

U="${1:-}"
case "$U" in
  user[0-9]*) : ;;
  *) echo "usage: $0 userN [--apply]   (e.g. $0 user12 --apply)" >&2; exit 2 ;;
esac
APPLY=0; [ "${2:-}" = "--apply" ] && APPLY=1
REGION="us-east-1"
ACCT="$(aws sts get-caller-identity --query Account --output text)"
echo "Reset $U in account $ACCT / $REGION — $( [ "$APPLY" = 1 ] && echo APPLY || echo 'DRY RUN' )"

# run CMD...  — echo it; execute only with --apply; never abort the script
run(){ echo "  + $*"; if [ "$APPLY" = 1 ]; then "$@" >/dev/null 2>&1 || echo "    (skip/err — already gone?)"; fi; }
have(){ "$@" >/dev/null 2>&1; }
section(){ echo; echo "### $*"; }

# --- SAM/CloudFormation app stacks -------------------------------------------
section "Flights + saga CloudFormation stacks"
for S in "cloudair-$U-flights" "cloudair-$U-saga"; do
  if have aws cloudformation describe-stacks --stack-name "$S" --region "$REGION"; then
    run aws cloudformation delete-stack --stack-name "$S" --region "$REGION"
  else echo "  - $S (absent)"; fi
done

# --- Cognito user pool (looked up by name) -----------------------------------
section "Cognito user pool cloudair-$U-pool"
POOL_ID=$(aws cognito-idp list-user-pools --max-results 60 --region "$REGION" \
  --query "UserPools[?Name=='cloudair-$U-pool'].Id | [0]" --output text 2>/dev/null)
if [ -n "$POOL_ID" ] && [ "$POOL_ID" != "None" ]; then
  for CID in $(aws cognito-idp list-user-pool-clients --user-pool-id "$POOL_ID" --region "$REGION" \
                --query "UserPoolClients[].ClientId" --output text 2>/dev/null); do
    run aws cognito-idp delete-user-pool-client --user-pool-id "$POOL_ID" --client-id "$CID" --region "$REGION"
  done
  run aws cognito-idp delete-user-pool --user-pool-id "$POOL_ID" --region "$REGION"
else echo "  - pool (absent)"; fi

# --- EventBridge custom bus + rule + archive ---------------------------------
section "EventBridge bus cloudair-$U"
if have aws events describe-event-bus --name "cloudair-$U" --region "$REGION"; then
  BUS_ARN="arn:aws:events:$REGION:$ACCT:event-bus/cloudair-$U"
  # Schema Discovery (Lab 6b/7b) creates a discoverer + a service-MANAGED rule named
  # "Schemas-events-event-bus-…". A managed rule blocks delete-event-bus and cannot be
  # removed with a plain delete-rule. Delete the discoverer first — that removes its
  # managed rule automatically — then force-delete any remaining rules.
  for D in $(aws schemas list-discoverers --region "$REGION" \
              --query "Discoverers[?SourceArn=='$BUS_ARN'].DiscovererId" --output text 2>/dev/null); do
    run aws schemas delete-discoverer --discoverer-id "$D" --region "$REGION"
  done
  for R in $(aws events list-rules --event-bus-name "cloudair-$U" --region "$REGION" --query "Rules[].Name" --output text 2>/dev/null); do
    TIDS=$(aws events list-targets-by-rule --rule "$R" --event-bus-name "cloudair-$U" --region "$REGION" --query "Targets[].Id" --output text 2>/dev/null)
    [ -n "$TIDS" ] && run aws events remove-targets --rule "$R" --event-bus-name "cloudair-$U" --ids $TIDS --force --region "$REGION"
    run aws events delete-rule --name "$R" --event-bus-name "cloudair-$U" --force --region "$REGION"
  done
  run aws events delete-archive --archive-name "cloudair-$U-archive" --region "$REGION"
  run aws events delete-event-bus --name "cloudair-$U" --region "$REGION"
else echo "  - bus (absent)"; fi

# --- SQS queues + SNS topic --------------------------------------------------
section "SQS queues + SNS topic"
for Q in "cloudair-$U-bookings" "cloudair-$U-bookings-dlq"; do
  URL=$(aws sqs get-queue-url --queue-name "$Q" --region "$REGION" --query QueueUrl --output text 2>/dev/null)
  [ -n "$URL" ] && [ "$URL" != "None" ] && run aws sqs delete-queue --queue-url "$URL" --region "$REGION" || echo "  - $Q (absent)"
done
TOPIC="arn:aws:sns:$REGION:$ACCT:cloudair-$U-bookings"
have aws sns get-topic-attributes --topic-arn "$TOPIC" --region "$REGION" \
  && run aws sns delete-topic --topic-arn "$TOPIC" --region "$REGION" \
  || echo "  - SNS topic (absent)"

# --- Worker Lambda (+ event-source mappings) + its IAM role -------------------
section "Worker Lambda + event-source mappings + role"
# Delete the SQS event-source mapping(s) FIRST — they can outlive delete-function
# and, because the queue/function names are reused, a stale Disabled mapping then
# silently blocks create-event-source-mapping when the lab is re-provisioned.
for ESM in $(aws lambda list-event-source-mappings --function-name "cloudair-$U-worker" \
              --query "EventSourceMappings[].UUID" --output text --region "$REGION" 2>/dev/null); do
  run aws lambda delete-event-source-mapping --uuid "$ESM" --region "$REGION"
done
have aws lambda get-function --function-name "cloudair-$U-worker" --region "$REGION" \
  && run aws lambda delete-function --function-name "cloudair-$U-worker" --region "$REGION" \
  || echo "  - worker fn (absent)"
ROLE="CloudAirWorkerRole-$U"
if have aws iam get-role --role-name "$ROLE"; then
  for P in $(aws iam list-attached-role-policies --role-name "$ROLE" --query "AttachedPolicies[].PolicyArn" --output text 2>/dev/null); do
    run aws iam detach-role-policy --role-name "$ROLE" --policy-arn "$P"
  done
  run aws iam delete-role --role-name "$ROLE"
else echo "  - $ROLE (absent)"; fi

# --- DynamoDB tables (the two NOT in the base stack) -------------------------
section "DynamoDB tables CloudAir-$U / ProcessedBookings-$U"
for T in "CloudAir-$U" "ProcessedBookings-$U"; do
  have aws dynamodb describe-table --table-name "$T" --region "$REGION" \
    && run aws dynamodb delete-table --table-name "$T" --region "$REGION" \
    || echo "  - $T (absent)"
done

# --- Secrets Manager secret --------------------------------------------------
section "Secrets Manager cloudair/$U/db"
have aws secretsmanager describe-secret --secret-id "cloudair/$U/db" --region "$REGION" \
  && run aws secretsmanager delete-secret --secret-id "cloudair/$U/db" --force-delete-without-recovery --region "$REGION" \
  || echo "  - secret (absent)"

# --- SSM parameters under /cloudair/<user>/ ----------------------------------
# (base-stack params under this path go away with the base stack below, but
#  delete-parameters here also clears the Lab 3a extras; harmless overlap.)
section "SSM params /cloudair/$U/"
PNAMES=$(aws ssm get-parameters-by-path --path "/cloudair/$U" --region "$REGION" --query "Parameters[].Name" --output text 2>/dev/null)
if [ -n "$PNAMES" ]; then
  # delete-parameters takes up to 10 names per call
  echo "$PNAMES" | tr '\t' '\n' | xargs -n10 -r echo | while read -r CHUNK; do
    run aws ssm delete-parameters --names $CHUNK --region "$REGION"
  done
else echo "  - no SSM params"; fi

# --- Elastic Beanstalk env + application -------------------------------------
section "Elastic Beanstalk env + app (cloudair-$U)"
if aws elasticbeanstalk describe-environments --environment-names "cloudair-$U-env" --region "$REGION" \
     --query "Environments[?Status!='Terminated']" --output text 2>/dev/null | grep -q .; then
  run aws elasticbeanstalk terminate-environment --environment-name "cloudair-$U-env" --region "$REGION"
  if [ "$APPLY" = 1 ]; then
    echo "    waiting for EB termination (~3 min)…"
    aws elasticbeanstalk wait environment-terminated --environment-names "cloudair-$U-env" --region "$REGION" 2>/dev/null || true
  fi
else echo "  - EB env (absent/terminated)"; fi
have aws elasticbeanstalk describe-applications --application-names "cloudair-$U" --region "$REGION" \
  && [ -n "$(aws elasticbeanstalk describe-applications --application-names "cloudair-$U" --region "$REGION" --query "Applications" --output text 2>/dev/null)" ] \
  && run aws elasticbeanstalk delete-application --application-name "cloudair-$U" --terminate-env-by-force --region "$REGION" \
  || echo "  - EB app (absent)"

# --- Base CloudFormation stack (empty its S3 bucket first) -------------------
section "Base stack cloudair-$U-base (S3 + Bookings table + SSM)"
BUCKET="cloudair-$U-assets"
have aws s3api head-bucket --bucket "$BUCKET" \
  && run aws s3 rm "s3://$BUCKET" --recursive   # bucket must be empty for stack delete
if have aws cloudformation describe-stacks --stack-name "cloudair-$U-base" --region "$REGION"; then
  run aws cloudformation delete-stack --stack-name "cloudair-$U-base" --region "$REGION"
  if [ "$APPLY" = 1 ]; then
    aws cloudformation wait stack-delete-complete --stack-name "cloudair-$U-base" --region "$REGION" 2>/dev/null || true
  fi
else echo "  - base stack (absent)"; fi

echo
[ "$APPLY" = 0 ] && echo "(dry run — re-run with --apply to delete)" \
  || echo "✅ $U reset. They can restart from Lab 1a, or jump in with: bootstrap.sh <labId>"
