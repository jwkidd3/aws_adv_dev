"""
Cloud Air — Lab 3a
==================
Reads all SSM Parameter Store entries under /cloudair/<USER_ID>/ and
prints them as a formatted table.

Usage:
    python3 load_config.py

Environment:
    USER_ID      — student identifier (required; falls back to "user1")
    AWS_REGION   — AWS region (optional; falls back to "us-east-1")

Requires:
    boto3 >= 1.34
"""

import os
import sys
import json
import logging

import boto3
from botocore.exceptions import ClientError

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(levelname)s  %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("load_config")

# ── Config from environment ──────────────────────────────────────────────────
USER_ID = os.environ.get("USER_ID", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

if not USER_ID:
    log.warning(
        "$USER_ID is not set — falling back to 'user1'. "
        "Run: source ~/.aws-adv-dev.env"
    )
    USER_ID = "user1"

SSM_PATH = f"/cloudair/{USER_ID}"

# ── SSM client ───────────────────────────────────────────────────────────────
ssm = boto3.client("ssm", region_name=AWS_REGION)


def get_all_parameters(path: str) -> dict[str, str]:
    """
    Paginate through get_parameters_by_path, decrypting SecureString values,
    and return a {name: value} dict keyed by the leaf name only.

    SSM returns at most 10 parameters per page; the pagination loop is
    required for any path with more than 10 entries.
    """
    params: dict[str, str] = {}
    kwargs = {
        "Path": path,
        "Recursive": False,       # only direct children; set True for nested paths
        "WithDecryption": True,   # decrypt SecureString values using KMS
        "MaxResults": 10,
    }

    page_num = 0
    while True:
        page_num += 1
        log.info("Fetching page %d from %s ...", page_num, path)
        try:
            response = ssm.get_parameters_by_path(**kwargs)
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in ("AccessDeniedException", "InvalidKeyId"):
                log.error(
                    "KMS decryption failed (%s). "
                    "Ensure the IAM role has kms:Decrypt on alias/aws/ssm.",
                    code,
                )
                sys.exit(1)
            raise

        for param in response.get("Parameters", []):
            # Use only the leaf portion of the name as the dict key
            leaf = param["Name"].rsplit("/", 1)[-1]
            params[leaf] = param["Value"]

        next_token = response.get("NextToken")
        if not next_token:
            break
        kwargs["NextToken"] = next_token

    return params


def print_table(params: dict[str, str]) -> None:
    """Pretty-print the parameters as a two-column table."""
    if not params:
        print(f"\n  (no parameters found under {SSM_PATH})\n")
        return

    # Mask secrets: any key containing 'key', 'secret', 'pass', or 'token'
    SENSITIVE_KEYWORDS = {"key", "secret", "pass", "token", "pwd"}

    col_w = max(len(k) for k in params) + 2
    header = f"{'PARAMETER':<{col_w}}  VALUE"
    print()
    print(header)
    print("-" * (len(header) + 20))
    for name, value in sorted(params.items()):
        if any(kw in name.lower() for kw in SENSITIVE_KEYWORDS):
            display = value[:4] + "****" if len(value) > 4 else "****"
        else:
            display = value
        print(f"  {name:<{col_w}}{display}")
    print()


def load_as_env(params: dict[str, str]) -> dict[str, str]:
    """
    Return a dict mapping upper-cased parameter names to their values.
    Suitable for passing to os.environ.update() or an app config object.

    Example:
        env = load_as_env(params)
        os.environ.update(env)
    """
    return {k.upper(): v for k, v in params.items()}


if __name__ == "__main__":
    print(f"Loading parameters from SSM path: {SSM_PATH}")
    print(f"Region: {AWS_REGION}")

    params = get_all_parameters(SSM_PATH)

    if not params:
        print(
            f"\nNo parameters found under '{SSM_PATH}'.\n"
            "Did you complete Lab 3a Step 2?\n"
        )
        sys.exit(0)

    print_table(params)

    # Show the env-style dict that an application would consume
    env_vars = load_as_env(params)
    print("As environment variables (UPPER_CASE keys):")
    print(json.dumps(env_vars, indent=2, default=str))
    print()
    print(f"Loaded {len(params)} parameter(s) from {SSM_PATH}")
