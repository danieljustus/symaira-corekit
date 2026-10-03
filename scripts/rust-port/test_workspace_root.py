"""Exercise adoption checkout resolution in standalone and linked worktrees."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import trust


class WorkspaceRootTests(unittest.TestCase):
    def test_standalone_and_external_linked_worktree_share_consumer_workspace(self):
        with tempfile.TemporaryDirectory(prefix="corekit-workspace-") as directory:
            parent = Path(directory).resolve()
            checkout = parent / "workspace" / "symaira-corekit"
            checkout.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(checkout)], check=True)
            subprocess.run([
                "git", "-C", str(checkout), "-c", "user.name=Fixture",
                "-c", "user.email=fixture@example.invalid", "commit", "-q",
                "--allow-empty", "-m", "fixture",
            ], check=True)
            linked = parent / "external" / "candidate"
            linked.parent.mkdir()
            subprocess.run([
                "git", "-C", str(checkout), "worktree", "add", "--quiet",
                "--detach", str(linked),
            ], check=True)
            expected = checkout.parent
            self.assertEqual(trust.workspace_root(checkout), expected)
            self.assertEqual(trust.workspace_root(linked), expected)
            with patch.object(trust, "workspace_root", return_value=expected):
                consumer = expected / "symaira-vault"
                consumer.mkdir()
                self.assertEqual(trust.safe_workspace_path("symaira-vault"), consumer)
                with self.assertRaisesRegex(ValueError, "traversal"):
                    trust.safe_workspace_path("../outside")
                with self.assertRaisesRegex(ValueError, "relative"):
                    trust.safe_workspace_path(str(consumer))
                link = expected / "escape"
                try:
                    link.symlink_to(parent, target_is_directory=True)
                except OSError:
                    pass  # Native Windows may prohibit creating symlinks.
                else:
                    with self.assertRaisesRegex(ValueError, "escapes|symlink"):
                        trust.safe_workspace_path("escape")

    def test_no_repository_does_not_guess_an_ancestor_workspace(self):
        with tempfile.TemporaryDirectory(prefix="corekit-no-repository-") as directory:
            with self.assertRaises(RuntimeError):
                trust.workspace_root(Path(directory))


if __name__ == "__main__":
    unittest.main()
