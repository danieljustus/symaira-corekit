"""Small integrity check for the native CI verifier installer; no network."""

import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("install_cosign", Path(__file__).with_name("install-cosign.py"))
assert SPEC is not None and SPEC.loader is not None
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


class CosignInstallerIntegrity(unittest.TestCase):
    def test_native_pins_and_tampered_download_rejection(self):
        self.assertEqual(len(INSTALLER.PINNED), 4)
        for asset, digest in INSTALLER.PINNED.values():
            self.assertTrue(asset.startswith("cosign-"))
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "download"
            original = b"unit-test-only verifier bytes"
            path.write_bytes(original)
            expected = hashlib.sha256(original).hexdigest()
            INSTALLER.validate_download(path, expected)
            path.write_bytes(original + b"tampered")
            with self.assertRaisesRegex(ValueError, "pinned SHA-256"):
                INSTALLER.validate_download(path, expected)


if __name__ == "__main__":
    unittest.main()
