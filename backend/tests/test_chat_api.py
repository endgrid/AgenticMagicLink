import hashlib
import unittest

from app.services.session_store import InMemorySessionStore
from src.magic_link_script import MAGIC_LINK_SCRIPT_VERSION


class SessionStoreMagicLinkPayloadTest(unittest.TestCase):
    def test_message_update_sets_magic_link_script_content_and_metadata_after_role_capture(self) -> None:
        store = InMemorySessionStore()
        session = store.create_session()

        store.update_from_message(session.session_id, "Target account 123456789012")
        updated = store.update_from_message(
            session.session_id,
            "Please use arn:aws:iam::123456789012:role/ContractorRole",
        )

        expected_checksum = hashlib.sha256(updated.magic_link_script.encode("utf-8")).hexdigest()

        self.assertIsNotNone(updated.magic_link_script)
        self.assertEqual(updated.magic_link_script_checksum_sha256, expected_checksum)
        self.assertEqual(updated.magic_link_script_version, MAGIC_LINK_SCRIPT_VERSION)


if __name__ == "__main__":
    unittest.main()
