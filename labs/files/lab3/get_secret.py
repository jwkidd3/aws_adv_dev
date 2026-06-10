"""
Cloud Air — Lab 3b
==================
Fetches the database credential stored in AWS Secrets Manager under
cloudair/<USER_ID>/db and prints the parsed fields.

Also exposes load_for_app() — a function that returns the credential dict
ready for use by a database driver or ORM.

Usage:
    python3 get_secret.py

Environment:
    USER_ID      — student identifier (required; falls back to "user1")
    AWS_REGION   — AWS region (optional; falls back to "us-east-1")

Requires:
    boto3 >= 1.34

Optional (recommended for Lambda):
    aws-secretsmanager-caching  — pip install aws-secretsmanager-caching
"""

import json
import logging
import os
import sys

import boto3
from botocore.exceptions import ClientError

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(levelname)s  %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("get_secret")

# ── Config from environment ──────────────────────────────────────────────────
USER_ID = os.environ.get("USER_ID", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

if not USER_ID:
    log.warning(
        "$USER_ID is not set — falling back to 'user1'. "
        "Run: source ~/.aws-adv-dev.env"
    )
    USER_ID = "user1"

SECRET_NAME = f"cloudair/{USER_ID}/db"

# ── Module-level cache (simulates in-process caching for long-running servers
#    and Lambda warm-start reuse). In production, use the AWS-maintained
#    aws-secretsmanager-caching library for TTL-based refresh.
# ──────────────────────────────────────────────────────────────────────────────
_secret_cache: dict = {}


def get_secret(secret_name: str, region: str = AWS_REGION) -> dict:
    """
    Retrieve and parse the JSON secret from Secrets Manager.

    Returns the parsed dict. The result is cached in _secret_cache for the
    lifetime of the process (module-level caching pattern).

    For Lambda, this means the secret is fetched once per execution environment
    (once per cold start) and reused across warm invocations — avoiding a
    Secrets Manager API call on every function invocation.
    """
    if secret_name in _secret_cache:
        log.info("Cache hit for secret '%s' — skipping API call.", secret_name)
        return _secret_cache[secret_name]

    client = boto3.client("secretsmanager", region_name=region)
    log.info("Fetching secret '%s' from region %s ...", secret_name, region)

    try:
        response = client.get_secret_value(SecretId=secret_name)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        messages = {
            "ResourceNotFoundException": (
                f"Secret '{secret_name}' not found. "
                "Did you complete Lab 3b Step 2?"
            ),
            "AccessDeniedException": (
                "IAM role lacks secretsmanager:GetSecretValue permission."
            ),
            "InvalidRequestException": (
                f"Secret '{secret_name}' is scheduled for deletion and "
                "cannot be retrieved."
            ),
            "DecryptionFailure": (
                "KMS decryption failed. Ensure the IAM role has "
                "kms:Decrypt on the secret's KMS key."
            ),
        }
        log.error(messages.get(code, f"Unexpected error ({code}): {exc}"))
        sys.exit(1)

    # Secrets Manager returns either SecretString (JSON text) or SecretBinary
    raw = response.get("SecretString")
    if raw is None:
        import base64
        raw = base64.b64decode(response["SecretBinary"]).decode("utf-8")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.error("Secret value is not valid JSON: %s", exc)
        sys.exit(1)

    _secret_cache[secret_name] = parsed
    return parsed


def _mask(value: str) -> str:
    """Show the first 4 characters of a sensitive string, mask the rest."""
    if len(value) <= 4:
        return "****"
    return value[:4] + "*" * (len(value) - 4)


def print_credential(cred: dict) -> None:
    """Print a structured credential dict, masking the password field."""
    MASK_KEYS = {"password", "passwd", "secret", "token", "key"}
    print()
    print(f"  Secret name : {SECRET_NAME}")
    print(f"  {'FIELD':<12}  VALUE")
    print(f"  {'-'*12}  {'-'*40}")
    for field, value in sorted(cred.items()):
        display = _mask(str(value)) if field.lower() in MASK_KEYS else value
        print(f"  {field:<12}  {display}")
    print()


def load_for_app(
    secret_name: str = SECRET_NAME,
    region: str = AWS_REGION,
) -> dict:
    """
    Public helper for application code.

    Returns the credential dict. Callers use it to build a DB connection:

        cfg = load_for_app()
        engine = create_engine(
            f"{cfg['engine']}://{cfg['username']}:{cfg['password']}"
            f"@{cfg['host']}:{cfg['port']}/{cfg['dbname']}"
        )

    The function is safe to call on every request — the module-level cache
    ensures only one Secrets Manager API call per process lifetime.
    """
    return get_secret(secret_name, region)


if __name__ == "__main__":
    print(f"Fetching secret: {SECRET_NAME}")
    print(f"Region        : {AWS_REGION}")

    cred = get_secret(SECRET_NAME)
    print_credential(cred)

    # Demonstrate the app-wiring pattern
    engine = cred.get("engine", "db")
    user = cred.get("username", "")
    host = cred.get("host", "")
    port = cred.get("port", "")
    dbname = cred.get("dbname", "")
    print(
        "Connection string (password redacted):\n"
        f"  {engine}://{user}:***@{host}:{port}/{dbname}"
    )
    print()

    # Show that a second call hits the cache (no network round-trip)
    log.info("Calling get_secret() a second time to demonstrate caching ...")
    _ = get_secret(SECRET_NAME)
    print("Done — second call served from in-process cache.")
    print()
