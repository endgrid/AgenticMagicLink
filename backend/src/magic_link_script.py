"""Generator for AWS console magic-link scripts."""

from __future__ import annotations

from dataclasses import dataclass
import textwrap


DEFAULT_SESSION_DURATION_SECONDS = 900
MAGIC_LINK_SCRIPT_VERSION = "1.0.0"
DEFAULT_REGION_PLACEHOLDER = "us-east-1"
DEFAULT_ROLE_ARN_PLACEHOLDER = "arn:aws:iam::123456789012:role/ExampleFederationRole"
DEFAULT_SESSION_NAME_PLACEHOLDER = "magic-link-session"

# Least-privilege starter policy. Keep narrow and extend only when required.
DEFAULT_LEAST_PRIVILEGE_SESSION_POLICY = textwrap.dedent(
    """
    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Sid": "ReadOnlyDiscovery",
          "Effect": "Allow",
          "Action": [
            "sts:GetCallerIdentity",
            "iam:ListAccountAliases"
          ],
          "Resource": "*"
        }
      ]
    }
    """
).strip()


@dataclass(frozen=True)
class MagicLinkScriptConfig:
    """Configuration placeholders embedded in the generated script."""

    role_arn_placeholder: str = DEFAULT_ROLE_ARN_PLACEHOLDER
    session_name_placeholder: str = DEFAULT_SESSION_NAME_PLACEHOLDER
    region_placeholder: str = DEFAULT_REGION_PLACEHOLDER
    default_session_duration_seconds: int = DEFAULT_SESSION_DURATION_SECONDS


def generate_magic_link_script(config: MagicLinkScriptConfig | None = None) -> str:
    """Return a runnable Python script that creates an AWS console login URL.

    The produced script contains explicit placeholders for runtime values and follows
    safety constraints:
    - short default duration
    - least-privilege session policy by default
    - no hardcoded long-term secrets
    """

    cfg = config or MagicLinkScriptConfig()
    policy_literal = repr(DEFAULT_LEAST_PRIVILEGE_SESSION_POLICY)

    return textwrap.dedent(
        f'''\
#!/usr/bin/env python3
"""
AWS Magic Link generator.

Usage examples:
  python magic_link.py --role-arn {cfg.role_arn_placeholder} \\
      --session-name {cfg.session_name_placeholder} --region {cfg.region_placeholder}

  python magic_link.py --role-arn <ROLE_ARN_OR_FEDERATION_PRINCIPAL> \\
      --session-name <SESSION_NAME> --region <AWS_REGION> \\
      --account-alias my-account-alias --destination https://console.aws.amazon.com/ec2/home

Safety defaults:
  * Session duration defaults to {cfg.default_session_duration_seconds} seconds.
  * A least-privilege session policy is attached unless overridden.
  * No static AWS secrets are embedded; base credentials must come from your environment.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request

DEFAULT_DURATION_SECONDS = {cfg.default_session_duration_seconds}
DEFAULT_POLICY_JSON = {policy_literal}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a temporary AWS console magic link")
    parser.add_argument("--role-arn", required=True, help="Role ARN (or federation principal identifier)")
    parser.add_argument("--session-name", required=True, help="STS session name")
    parser.add_argument("--region", required=True, help="AWS region used for STS client")
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=DEFAULT_DURATION_SECONDS,
        help="Session duration in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--session-policy-json",
        default=DEFAULT_POLICY_JSON,
        help="Inline session policy JSON; keep this least-privilege",
    )
    parser.add_argument(
        "--account-alias",
        default="",
        help="Optional account alias to target the account-branded sign-in endpoint",
    )
    parser.add_argument(
        "--destination",
        default="",
        help="Optional console destination URL. Defaults to AWS console home with region.",
    )
    return parser.parse_args()


def resolve_destination(region: str, account_alias: str, destination: str) -> str:
    if destination:
        return destination
    if account_alias:
        return f"https://{{account_alias}}.signin.aws.amazon.com/console?region={{region}}"
    return f"https://console.aws.amazon.com/console/home?region={{region}}"


def assume_temporary_credentials(
    role_arn: str,
    session_name: str,
    region: str,
    duration_seconds: int,
    session_policy_json: str,
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
        Policy=session_policy_json,
    )
    creds = resp["Credentials"]
    return {{
        "sessionId": creds["AccessKeyId"],
        "sessionKey": creds["SecretAccessKey"],
        "sessionToken": creds["SessionToken"],
    }}


def get_signin_token(session_dict: dict, duration_seconds: int) -> str:
    params = urllib.parse.urlencode(
        {{
            "Action": "getSigninToken",
            "Session": json.dumps(session_dict),
            "SessionDuration": str(duration_seconds),
        }}
    )
    url = f"https://signin.aws.amazon.com/federation?{{params}}"
    with urllib.request.urlopen(url) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["SigninToken"]


def build_login_url(signin_token: str, destination: str, issuer: str = "magic-link-script") -> str:
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
    if args.duration_seconds > 3600:
        raise SystemExit("Refusing duration over 3600 seconds. Use the shortest viable session.")

    destination = resolve_destination(args.region, args.account_alias, args.destination)
    session_dict = assume_temporary_credentials(
        role_arn=args.role_arn,
        session_name=args.session_name,
        region=args.region,
        duration_seconds=args.duration_seconds,
        session_policy_json=args.session_policy_json,
    )
    signin_token = get_signin_token(session_dict, args.duration_seconds)
    print(build_login_url(signin_token, destination))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''
    )
