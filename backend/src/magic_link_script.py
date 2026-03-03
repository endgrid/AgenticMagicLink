"""Generator for AWS console magic-link scripts."""

from __future__ import annotations

from dataclasses import dataclass
import json
import textwrap


DEFAULT_SESSION_DURATION_SECONDS = 900
MIN_SESSION_DURATION_SECONDS = 900
MAX_SESSION_DURATION_SECONDS = 43200
MAGIC_LINK_SCRIPT_VERSION = "1.0.0"
DEFAULT_REGION_PLACEHOLDER = "us-east-1"
DEFAULT_ROLE_ARN_PLACEHOLDER = "arn:aws:iam::123456789012:role/ExampleFederationRole"
DEFAULT_SESSION_NAME_PLACEHOLDER = "magic-link-session"


@dataclass(frozen=True)
class MagicLinkScriptConfig:
    """Configuration placeholders embedded in the generated script."""

    role_arn_placeholder: str = DEFAULT_ROLE_ARN_PLACEHOLDER
    session_name_placeholder: str = DEFAULT_SESSION_NAME_PLACEHOLDER
    region_placeholder: str = DEFAULT_REGION_PLACEHOLDER
    default_session_duration_seconds: int = DEFAULT_SESSION_DURATION_SECONDS
    default_role_arn: str = DEFAULT_ROLE_ARN_PLACEHOLDER
    default_session_name: str = DEFAULT_SESSION_NAME_PLACEHOLDER
    expected_account_id: str | None = None


def generate_magic_link_script(config: MagicLinkScriptConfig | None = None) -> str:
    """Return a runnable Python script that creates an AWS console login URL."""

    cfg = config or MagicLinkScriptConfig()
    default_role_arn_literal = json.dumps(cfg.default_role_arn)
    default_session_name_literal = json.dumps(cfg.default_session_name)
    expected_account_id_literal = json.dumps(cfg.expected_account_id)

    return textwrap.dedent(
        f'''\
#!/usr/bin/env python3
"""
AWS Console Federation URL Generator.

Assumes an IAM role and generates a temporary AWS Management Console sign-in URL that can be shared with a contractor.

Usage:
  python magic_link.py <role_arn> [--session-name NAME] [--duration SECONDS] [--region REGION]

Examples:
  python magic_link.py {cfg.role_arn_placeholder}
  python magic_link.py {cfg.role_arn_placeholder} --duration 3600 --session-name contractor-jane
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request

DEFAULT_DURATION_SECONDS = {cfg.default_session_duration_seconds}
MIN_DURATION_SECONDS = {MIN_SESSION_DURATION_SECONDS}
MAX_DURATION_SECONDS = {MAX_SESSION_DURATION_SECONDS}
DEFAULT_ROLE_ARN = {default_role_arn_literal}
DEFAULT_SESSION_NAME = {default_session_name_literal}
EXPECTED_ACCOUNT_ID = {expected_account_id_literal}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a temporary AWS Console sign-in URL for a contractor.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("role_arn", nargs="?", default=DEFAULT_ROLE_ARN, help="ARN of the IAM role to assume")
    parser.add_argument(
        "--session-name",
        default=DEFAULT_SESSION_NAME,
        help="Session name for the assumed role (default: %(default)s)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_DURATION_SECONDS,
        help="Session duration in seconds (900–43200, default: %(default)s)",
    )
    parser.add_argument(
        "--region",
        default="{cfg.region_placeholder}",
        help="AWS region for the console destination (e.g. us-east-1)",
    )
    return parser.parse_args()


def resolve_destination(region: str) -> str:
    return f"https://{{region}}.console.aws.amazon.com/"


def assume_temporary_credentials(
    role_arn: str,
    session_name: str,
    region: str,
    duration_seconds: int,
) -> dict:
    try:
        import boto3  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "boto3 is required to assume the role. Install boto3 or provide equivalent flow."
        ) from exc

    sts = boto3.client("sts", region_name=region)
    resp = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName=session_name,
        DurationSeconds=duration_seconds,
    )
    creds = resp["Credentials"]
    return {{
        "sessionId": creds["AccessKeyId"],
        "sessionKey": creds["SecretAccessKey"],
        "sessionToken": creds["SessionToken"],
    }}


def get_signin_token(session_dict: dict) -> str:
    params = urllib.parse.urlencode(
        {{
            "Action": "getSigninToken",
            "Session": json.dumps(session_dict),
        }}
    )
    url = f"https://signin.aws.amazon.com/federation?{{params}}"
    with urllib.request.urlopen(url) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["SigninToken"]


def build_login_url(signin_token: str, destination: str, issuer: str = "custom-iam-broker") -> str:
    params = urllib.parse.urlencode(
        {{
            "Action": "login",
            "Issuer": issuer,
            "Destination": destination,
            "SigninToken": signin_token,
        }}
    )
    return f"https://signin.aws.amazon.com/federation?{{params}}"


def main() -> int:
    args = parse_args()
    if not args.role_arn:
        raise SystemExit("A role ARN is required.")

    if EXPECTED_ACCOUNT_ID and f"::{{EXPECTED_ACCOUNT_ID}}:" not in args.role_arn:
        raise SystemExit("Role ARN account does not match the target account.")

    if args.duration < MIN_DURATION_SECONDS or args.duration > MAX_DURATION_SECONDS:
        raise SystemExit(
            f"--duration must be between {{MIN_DURATION_SECONDS}} and {{MAX_DURATION_SECONDS}} seconds"
        )

    print(f"Assuming role: {{args.role_arn}}")
    print(f"Session name: {{args.session_name}}")
    print(f"Duration: {{args.duration}}s")
    print()

    destination = resolve_destination(args.region)
    session_dict = assume_temporary_credentials(
        role_arn=args.role_arn,
        session_name=args.session_name,
        region=args.region,
        duration_seconds=args.duration,
    )
    signin_token = get_signin_token(session_dict)
    signin_url = build_login_url(signin_token, destination)

    print("Temporary console sign-in URL (share with contractor):\\n")
    print(signin_url)
    print(f"\\nThis URL expires in {{args.duration // 60}} minutes.")
    print("WARNING: Treat this URL as a secret — anyone with it can access the AWS Console.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''
    )
