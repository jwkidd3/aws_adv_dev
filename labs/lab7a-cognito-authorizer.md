# 🧪 Lab 7a — Secure the API: Cognito JWT Authorizer

*Hands-On Lab · 50 min · Console + CLI · Day 3 — Security & Observability*

## Objectives (3 min)

- Create a Cognito user pool and app client using the AWS CLI
- Create a user, set a permanent password, and authenticate to obtain tokens
- Attach a JWT authorizer to the Flights HTTP API from Lab 4
- Confirm unauthenticated requests return `401 Unauthorized`
- Call the API with a valid ID token and inspect the JWT claims

> After this lab, Lab 7b adds X-Ray tracing to the same API. Keep the user pool
> and the SAM stack alive until the end of Day 3.

---

## Prerequisites (3 min)

- Labs 4a–4b complete — `cloudair-$USER_ID-flights` Lambda and HTTP API deployed
- SAM stack outputs saved (`$API_URL` available in `~/.aws-adv-dev.env`)
- `~/.aws-adv-dev.env` exists with `$USER_ID`, `$ACCT`, `$AWS_REGION`

```bash
source ~/.aws-adv-dev.env

# Retrieve the API URL from the SAM stack if not already exported
API_URL=$(aws cloudformation describe-stacks \
    --stack-name "cloudair-$USER_ID-flights" \
    --query "Stacks[0].Outputs[?OutputKey=='FlightsApiUrl'].OutputValue" \
    --output text --region $AWS_REGION)

echo "API_URL=$API_URL"
echo "export API_URL=$API_URL" >> ~/.aws-adv-dev.env
```

> **Starting fresh?** `bash ~/environment/aws-adv-dev/bootstrap.sh 7a` ensures
> the base CloudFormation stack is present and the env file is populated. It does
> **not** deploy the Flights SAM stack — Lab 4a must be completed first before the
> `cloudair-$USER_ID-flights` stack and `$API_URL` are available.

---

## Step 1 — Confirm the API Requires No Auth Today (3 min)

Before adding the authorizer, verify the API is currently open:

```bash
source ~/.aws-adv-dev.env
curl -s "$API_URL/flights" | python3 -m json.tool
```

You should receive a `200 OK` with a JSON `flights` array. This is the baseline
you will lock down in Step 5.

---

## Step 2 — Create the Cognito User Pool (8 min)

```bash
source ~/.aws-adv-dev.env

POOL_ID=$(aws cognito-idp create-user-pool \
    --pool-name "cloudair-$USER_ID-pool" \
    --policies '{
        "PasswordPolicy": {
            "MinimumLength": 8,
            "RequireUppercase": true,
            "RequireLowercase": true,
            "RequireNumbers": true,
            "RequireSymbols": false
        }
    }' \
    --auto-verified-attributes email \
    --username-attributes email \
    --query "UserPool.Id" --output text \
    --region $AWS_REGION)

echo "POOL_ID=$POOL_ID"
echo "export POOL_ID=$POOL_ID" >> ~/.aws-adv-dev.env
```

The pool uses **email as the username** — students can sign in with their email
address rather than a generated sub UUID. `auto-verified-attributes email` means
Cognito sends a verification code on sign-up; in this lab you bypass that with
an admin-set password so no real email infrastructure is required.

---

## Step 3 — Create an App Client (5 min)

An app client is the credential set an application uses to call the Cognito API.
`--explicit-auth-flows` enables `USER_PASSWORD_AUTH` so you can exchange a
username and password for tokens from the CLI.

```bash
source ~/.aws-adv-dev.env

CLIENT_ID=$(aws cognito-idp create-user-pool-client \
    --user-pool-id $POOL_ID \
    --client-name "cloudair-$USER_ID-client" \
    --no-generate-secret \
    --explicit-auth-flows ALLOW_USER_PASSWORD_AUTH ALLOW_REFRESH_TOKEN_AUTH \
    --query "UserPoolClient.ClientId" --output text \
    --region $AWS_REGION)

echo "CLIENT_ID=$CLIENT_ID"
echo "export CLIENT_ID=$CLIENT_ID" >> ~/.aws-adv-dev.env
```

`--no-generate-secret` is correct for public clients (SPAs, mobile apps, CLI tools).
Server-side clients should use a secret and `ALLOW_USER_SRP_AUTH` instead.

---

## Step 4 — Create a User and Get Tokens (8 min)

**Create the user:**

```bash
source ~/.aws-adv-dev.env

aws cognito-idp admin-create-user \
    --user-pool-id $POOL_ID \
    --username "$USER_ID@cloudair.example" \
    --temporary-password "TempPass1!" \
    --message-action SUPPRESS \
    --region $AWS_REGION

# Set a permanent password so the user is not stuck in FORCE_CHANGE_PASSWORD state
aws cognito-idp admin-set-user-password \
    --user-pool-id $POOL_ID \
    --username "$USER_ID@cloudair.example" \
    --password "CloudAir1!" \
    --permanent \
    --region $AWS_REGION
```

**Authenticate and capture the ID token:**

```bash
source ~/.aws-adv-dev.env

# NOTE: --auth-parameters is a map — the key=value pairs must be COMMA-separated
# (no spaces). Space-separating them makes the CLI treat PASSWORD=... as an
# unknown option.
AUTH_RESULT=$(aws cognito-idp initiate-auth \
    --auth-flow USER_PASSWORD_AUTH \
    --auth-parameters USERNAME="$USER_ID@cloudair.example",PASSWORD="CloudAir1!" \
    --client-id $CLIENT_ID \
    --region $AWS_REGION)

ID_TOKEN=$(echo $AUTH_RESULT | \
    python3 -c "import json,sys; print(json.load(sys.stdin)['AuthenticationResult']['IdToken'])")

ACCESS_TOKEN=$(echo $AUTH_RESULT | \
    python3 -c "import json,sys; print(json.load(sys.stdin)['AuthenticationResult']['AccessToken'])")

echo "ID_TOKEN (first 60 chars): ${ID_TOKEN:0:60}..."
echo "export ID_TOKEN=$ID_TOKEN"       >> ~/.aws-adv-dev.env
echo "export ACCESS_TOKEN=$ACCESS_TOKEN" >> ~/.aws-adv-dev.env
```

**Inspect the JWT claims (no library required):**

```bash
# The payload is the second dot-delimited segment, base64url-encoded
echo $ID_TOKEN | cut -d. -f2 | \
    python3 -c "
import sys, base64, json
seg = sys.stdin.read().strip()
# Add padding if needed
seg += '=' * (4 - len(seg) % 4)
print(json.dumps(json.loads(base64.urlsafe_b64decode(seg)), indent=2))
"
```

Note the `sub` (unique user ID), `email`, `cognito:username`, `iss` (issuer URL),
`aud` (your CLIENT_ID), and `exp` (expiry timestamp) claims.

---

## Step 5 — Attach the JWT Authorizer to the HTTP API (8 min)

The Flights HTTP API is managed by the SAM stack. The cleanest approach is to
add the authorizer in `template.yaml` and redeploy.

Open `~/environment/aws-adv-dev/lab4/template.yaml` in the Cloud9 editor and
make two changes:

**1. Add the `Auth` block to the `FlightsApi` resource:**

```yaml
  FlightsApi:
    Type: AWS::Serverless::HttpApi
    Properties:
      StageName: prod
      Auth:                        # <-- add this block, right after StageName
        DefaultAuthorizer: CognitoJwtAuth
        Authorizers:
          CognitoJwtAuth:
            IdentitySource: $request.header.Authorization
            JwtConfiguration:
              issuer: !Sub "https://cognito-idp.${AWS::Region}.amazonaws.com/${PoolId}"
              audience:
                - !Ref AppClientId
      DefinitionBody:              # <-- leave the existing DefinitionBody unchanged
        # ... (the strangler /{proxy+} route from Lab 4 — do not edit) ...
      Tags:
        Project: CloudAir
        Owner: !Ref UserId
```

> **`DefaultAuthorizer` secures the *whole* facade.** It applies to every route on
> the API — `GET /flights` **and** the `ANY /{proxy+}` strangler proxy. So after this
> deploy, the legacy paths proxied to the monolith (e.g. `/bookings`) also require a
> valid token. That's the point of Lab 7a — you're locking down the entire Cloud Air
> entry point, not just the new microservice. (The proxy route survives this redeploy
> because it lives in the HttpApi's `DefinitionBody`, not as a separate route resource.)

**2. Add the two new Parameters:**

```yaml
  PoolId:
    Type: String
    Description: Cognito User Pool ID

  AppClientId:
    Type: String
    Description: Cognito App Client ID
```

**Rebuild, then redeploy with the new parameters:**

You edited the **source** `template.yaml`, but `sam deploy` ships the *built*
template under `.aws-sam/build/` — the one produced by `sam build` back in Lab 4.
If you skip the rebuild, SAM compares the stale built template (no authorizer)
against the deployed stack, finds no difference, and reports **"No changes to
deploy"** — your `Auth` block never ships. Always `sam build` after editing the
template. Delete `.aws-sam` first to force a clean rebuild so no cached artifact
masks the change:

```bash
source ~/.aws-adv-dev.env
cd ~/environment/aws-adv-dev/lab4

# Force a clean rebuild so the new Auth block is in the built template
rm -rf .aws-sam
sam build

sam deploy \
    --stack-name "cloudair-$USER_ID-flights" \
    --parameter-overrides \
        "UserId=$USER_ID" \
        "BookingsTableName=Bookings-$USER_ID" \
        "PoolId=$POOL_ID" \
        "AppClientId=$CLIENT_ID" \
    --no-confirm-changeset \
    --region $AWS_REGION
```

> **Why `rm -rf .aws-sam`?** `sam build` normally regenerates the built template,
> but a leftover cached build can make SAM believe nothing changed, so the deploy
> finds no diff. Removing `.aws-sam` guarantees the rebuild reflects your edit.
>
> SAM `deploy` without `--guided` uses the `samconfig.toml` saved during the
> Lab 4 deployment. If `samconfig.toml` is missing, add `--s3-bucket <your-sam-bucket>`
> and `--capabilities CAPABILITY_IAM`.

---

## Step 6 — Call the API Without and With the Token (5 min)

**Without a token — expect `401 Unauthorized`:**

```bash
source ~/.aws-adv-dev.env
curl -s -o /dev/null -w "%{http_code}" "$API_URL/flights"
```

Should print `401`.

**With the ID token — expect `200 OK`:**

```bash
source ~/.aws-adv-dev.env
curl -s -H "Authorization: $ID_TOKEN" "$API_URL/flights" | python3 -m json.tool
```

The JWT authorizer validates the token signature against the Cognito JWKS endpoint
(`<issuer>/.well-known/jwks.json`), checks `aud`, and verifies `exp` — all without
invoking your Lambda. Only valid tokens reach the function.

---

## Discussion

**ID token vs Access token:** Cognito issues both. The **ID token** contains user
profile claims (`email`, `name`, custom attributes). The **Access token** is the
correct credential for calling Cognito-protected resources and scoped OAuth flows.
For simple Lambda authorizers either works; for fine-grained OAuth use the access token.

**JWT authorizer vs Lambda authorizer:** A JWT authorizer is managed by API Gateway —
zero Lambda cold starts, no code to maintain, automatically refreshes JWKS. A Lambda
authorizer gives full programmatic control (e.g., validate a proprietary token,
look up permissions in DynamoDB). Choose JWT when Cognito (or any standards-compliant
IdP) is the identity provider.

**Token expiry:** `exp` in the JWT payload is a Unix timestamp. The default
Cognito token lifetime is 1 h for ID/access tokens, 30 days for refresh tokens.
Use `initiate-auth` with `REFRESH_TOKEN_AUTH` to obtain a new token set without
re-entering credentials.

**Cognito groups and scope:** Add users to pool groups and include the group
claim (`cognito:groups`) in the JWT. Your Lambda can then implement role-based
access control by reading `event['requestContext']['authorizer']['jwt']['claims']`.

---

## Success Criteria (3 min)

- ✅ Cognito user pool `cloudair-$USER_ID-pool` and app client created
- ✅ User `$USER_ID@cloudair.example` exists in `CONFIRMED` state
- ✅ `initiate-auth` returned an ID token and access token
- ✅ JWT claims decoded and inspected (sub, email, aud, exp visible)
- ✅ SAM stack redeployed with `CognitoJwtAuth` authorizer
- ✅ `curl` without a token returns `401`
- ✅ `curl` with `Authorization: $ID_TOKEN` returns `200` with flight data
