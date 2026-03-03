import io
import json
import unittest
import urllib.parse
from unittest import mock

from backend.src.magic_link_script import MagicLinkScriptConfig, generate_magic_link_script


class MagicLinkScriptIntegrationTest(unittest.TestCase):
    def test_generated_script_constructs_login_url_from_federation_token(self) -> None:
        script = generate_magic_link_script(
            MagicLinkScriptConfig(
                default_role_arn="arn:aws:iam::123456789012:role/Test",
                expected_account_id="123456789012",
            )
        )
        namespace: dict = {}
        exec(script, namespace)

        namespace["assume_temporary_credentials"] = lambda **_: {
            "sessionId": "AKIA_TEST",
            "sessionKey": "SECRET",
            "sessionToken": "TOKEN",
        }

        class _FakeResponse:
            def __init__(self, payload: dict):
                self._payload = payload

            def read(self) -> bytes:
                return json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def fake_urlopen(url: str):
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            self.assertEqual(qs["Action"], ["getSigninToken"])
            return _FakeResponse({"SigninToken": "TOKEN123"})

        with mock.patch("sys.argv", [
            "magic_link.py",
            "arn:aws:iam::123456789012:role/Test",
            "--region", "us-east-1",
        ]), mock.patch("urllib.request.urlopen", side_effect=fake_urlopen), mock.patch(
            "sys.stdout", new_callable=io.StringIO
        ) as stdout:
            rc = namespace["main"]()

        self.assertEqual(rc, 0)
        lines = [line for line in stdout.getvalue().strip().splitlines() if line.strip()]
        output = lines[-3]
        parsed_login = urllib.parse.urlparse(output)
        login_qs = urllib.parse.parse_qs(parsed_login.query)

        self.assertEqual(parsed_login.netloc, "signin.aws.amazon.com")
        self.assertEqual(login_qs["Action"], ["login"])
        self.assertEqual(login_qs["SigninToken"], ["TOKEN123"])
        self.assertEqual(login_qs["Destination"], ["https://us-east-1.console.aws.amazon.com/"])

    def test_generated_script_rejects_account_mismatch(self) -> None:
        script = generate_magic_link_script(
            MagicLinkScriptConfig(
                default_role_arn="arn:aws:iam::210987654321:role/Test",
                expected_account_id="123456789012",
            )
        )
        namespace: dict = {}
        exec(script, namespace)

        with mock.patch("sys.argv", ["magic_link.py", "--region", "us-east-1"]):
            with self.assertRaises(SystemExit) as exc:
                namespace["main"]()

        self.assertIn("does not match", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
