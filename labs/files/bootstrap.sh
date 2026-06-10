#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Advanced Developing on AWS — "catch me up" bootstrap.
#
#   bash ~/environment/aws-adv-dev/bootstrap.sh <labId>
#
# Creates-or-reuses every resource a given lab depends on, then writes the
# expected shell variables to ~/.aws-adv-dev.env so you can pick up mid-course
# even if you skipped or failed an earlier lab. Idempotent: existing resources
# are detected and reused, never duplicated.
#
# labId ∈ { 1b 1c 2a 2b 3a 3b 4a 4b 5a 5b 6a 6b 7a 7b }
#
# The Cloud Air refactor builds on a small spine of shared resources:
#   base CloudFormation stack  (S3 assets bucket + Bookings table + SSM params)
#   CloudAir-<user> single table   (lab 5+)
# Heavier per-lab resources (SAM stacks, Cognito, EventBridge) are created by
# the labs themselves; bootstrap ensures the *prerequisites* for each lab exist.
# -----------------------------------------------------------------------------
set -euo pipefail

LAB="${1:-}"
ENV_FILE="$HOME/.aws-adv-dev.env"
REGION="us-east-1"
HERE="$(cd "$(dirname "$0")" && pwd)"

if [ -z "$LAB" ]; then
  echo "usage: bootstrap.sh <labId>   e.g. bootstrap.sh 4a" >&2
  exit 2
fi

# --- identity & USER_ID guard ------------------------------------------------
# In Cloud9 the SDK runs as the shared LabRole, so we cannot derive a per-student
# ID from the caller. USER_ID must be set by the student (Lab 1b). Refuse to run
# on an empty or LabRole value rather than silently colliding with the class.
[ -f "$ENV_FILE" ] && source "$ENV_FILE" || true
ACCT="$(aws sts get-caller-identity --query Account --output text)"

if [ -z "${USER_ID:-}" ] || [ "${USER_ID}" = "LabRole" ]; then
  cat >&2 <<EOF
✋ USER_ID is not set (or is 'LabRole').

Set it to your assigned user before bootstrapping, e.g.:

    echo 'export USER_ID=user1' >> $ENV_FILE
    echo 'export AWS_REGION=$REGION' >> $ENV_FILE
    source $ENV_FILE

then re-run: bash $HERE/bootstrap.sh $LAB
EOF
  exit 1
fi

# Persist the spine vars every lab assumes.
touch "$ENV_FILE"
set_var(){ # set_var NAME VALUE  — idempotent upsert into the env file
  local n="$1" v="$2"
  grep -q "^export $n=" "$ENV_FILE" && \
    sed -i "s|^export $n=.*|export $n=$v|" "$ENV_FILE" || \
    echo "export $n=$v" >> "$ENV_FILE"
}
set_var AWS_REGION "$REGION"
set_var USER_ID    "$USER_ID"
set_var ACCT       "$ACCT"
export AWS_REGION="$REGION" ACCT="$ACCT"
echo "▶ bootstrapping lab $LAB  —  USER_ID=$USER_ID  account=$ACCT  region=$REGION"

have(){ "$@" >/dev/null 2>&1; }

# --- base CloudFormation stack (S3 assets + Bookings table + SSM params) ------
# Prereq for everything from lab 2 onward. Lab 2a deploys it by hand; bootstrap
# deploys the same template so later labs don't depend on having done 2a.
ensure_base(){
  local STACK="cloudair-$USER_ID-base"
  if have aws cloudformation describe-stacks --stack-name "$STACK"; then
    echo "  ✓ base stack $STACK exists"
  else
    echo "  + deploying base stack $STACK"
    aws cloudformation deploy \
      --stack-name "$STACK" \
      --template-file "$HERE/lab2/base-stack.yaml" \
      --parameter-overrides UserId="$USER_ID" \
      --capabilities CAPABILITY_NAMED_IAM >/dev/null
  fi
  local bucket table
  bucket=$(aws cloudformation describe-stacks --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='StaticAssetsBucketName'].OutputValue" --output text 2>/dev/null || true)
  [ -z "$bucket" ] && bucket="cloudair-$USER_ID-assets"
  set_var ASSETS_BUCKET  "$bucket"
  set_var BOOKINGS_TABLE "Bookings-$USER_ID"
}

# --- single table (lab 5+) ----------------------------------------------------
ensure_singletable(){
  local T="CloudAir-$USER_ID"
  if have aws dynamodb describe-table --table-name "$T"; then
    echo "  ✓ single table $T exists"
  else
    echo "  + creating single table $T"
    USER_ID="$USER_ID" python3 "$HERE/lab5/create_table.py" >/dev/null
  fi
  set_var SINGLE_TABLE "$T"
}

# --- per-lab prerequisite graph ----------------------------------------------
case "$LAB" in
  1b|1c)
    echo "  (no AWS resources required — env vars set)"
    ;;
  2a|2b)
    echo "  (lab creates the base stack / EB env itself — env vars set)"
    set_var BOOKINGS_TABLE "Bookings-$USER_ID"
    ;;
  3a|3b)
    ensure_base
    ;;
  4a|4b)
    ensure_base
    echo "  ℹ lab 4 deploys the Flights SAM stack (cloudair-$USER_ID-flights) itself."
    [ "$LAB" = "4b" ] && echo "  ℹ set MonolithUrl to your Lab 2b EB CNAME (\$EB_URL) when you deploy."
    ;;
  5a)
    ensure_base; ensure_singletable
    ;;
  5b)
    ensure_base; ensure_singletable
    echo "  ℹ lab 5b deploys the booking-saga SAM stack (cloudair-$USER_ID-saga) itself."
    ;;
  6a|6b)
    ensure_base
    echo "  ℹ lab 6 creates the SQS/SNS (6a) or EventBridge bus (6b) resources itself."
    ;;
  7a|7b)
    ensure_base
    echo "  ℹ lab 7 needs the Flights API from lab 4. If missing, run lab 4a first."
    ;;
  *)
    echo "unknown labId '$LAB' — valid: 1b 1c 2a 2b 3a 3b 4a 4b 5a 5b 6a 6b 7a 7b" >&2
    exit 2
    ;;
esac

echo "✅ lab $LAB ready. Run:  source $ENV_FILE"
