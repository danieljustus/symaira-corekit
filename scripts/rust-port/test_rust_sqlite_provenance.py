"""Production-path SQLite provenance regression controls."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from typing import Any
from unittest.mock import patch

SQLITE_ROOT = Path(__file__).resolve().parent / "sqlite"


def load(name: str) -> Any:
    path = SQLITE_ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


load("generate")
candidate = load("candidate")
load("typed_contract")
diff = load("diff")


class SqliteProvenanceControls(unittest.TestCase):
    def setUp(self):
        record = json.loads(
            (candidate.ROOT / "testdata/rust-port/sqlite/differential-checkpoint-provenance-repair.json").read_text()
        )
        self.go = record["go"]
        self.rust = copy.deepcopy(record["rust"])
        self.manifest, self.manifest_sha = candidate.load()

    def test_valid_existing_unrelated_revision_rejected(self):
        # Build an isolated repository with two root commits and a matching
        # temporary manifest. Frozen captures/manifests remain untouched.
        with tempfile.TemporaryDirectory(prefix="sqlite-provenance-") as directory:
            repo = Path(directory)
            git_env = {
                **os.environ,
                "GIT_AUTHOR_NAME": "SQLite provenance test",
                "GIT_AUTHOR_EMAIL": "sqlite-provenance-test@example.invalid",
                "GIT_COMMITTER_NAME": "SQLite provenance test",
                "GIT_COMMITTER_EMAIL": "sqlite-provenance-test@example.invalid",
                "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
                "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
            }

            def git(*args):
                return subprocess.run(
                    ["git", *args],
                    cwd=repo,
                    env=git_env,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()

            git("init", "--quiet")
            git("commit", "--quiet", "--allow-empty", "-m", "baseline")
            base = git("rev-parse", "HEAD")
            git("checkout", "--quiet", "--orphan", "unrelated")
            git("commit", "--quiet", "--allow-empty", "-m", "unrelated revision")
            unrelated = git("rev-parse", "HEAD")
            self.assertEqual(git("cat-file", "-t", base), "commit")
            self.assertEqual(git("cat-file", "-t", unrelated), "commit")
            self.assertNotEqual(base, unrelated)

            manifest = copy.deepcopy(self.manifest)
            manifest["base"] = base
            manifest_path = repo / "candidate-source.json"
            manifest_path.write_bytes(
                (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
            )
            manifest, manifest_sha = candidate.load(manifest_path)
            rust = copy.deepcopy(self.rust)
            rust["candidate_base"] = base
            rust["candidate_revision"] = unrelated
            rust["candidate_manifest_sha256"] = manifest_sha
            with patch.object(candidate, "ROOT", repo):
                with self.assertRaisesRegex(ValueError, "verified descendant"):
                    diff.evaluate(self.go, rust, manifest, manifest_sha)


if __name__ == "__main__":
    unittest.main()
