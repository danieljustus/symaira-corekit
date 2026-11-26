#!/usr/bin/env python3
"""Regression tests for the product String Catalog checker CLI."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("check-strings.py")


def translated(value):
    return {"localizations": {"de": {"stringUnit": {"state": "translated", "value": value}}}}


class CheckStringsTests(unittest.TestCase):
    def run_check(self, source, strings):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = root / "Sources"
            nested = source_root / "Views"
            nested.mkdir(parents=True)
            (nested / "View.swift").write_text(source, encoding="utf-8")
            catalog = root / "Localizable.xcstrings"
            catalog.write_text(json.dumps({"sourceLanguage": "en", "strings": strings}), encoding="utf-8")
            return subprocess.run(
                [sys.executable, "-I", str(SCRIPT), str(source_root), str(catalog)],
                capture_output=True,
                text=True,
            )

    def test_missing_german_entry_fails(self):
        result = self.run_check('L("Save"); L("Retry")', {"Save": {}})
        self.assertEqual(result.returncode, 1)
        self.assertIn("no German text: Save", result.stderr)
        self.assertIn("no German text: Retry", result.stderr)

    def test_blank_german_value_fails(self):
        result = self.run_check('L("Save")', {"Save": translated(" ")})
        self.assertEqual(result.returncode, 1)
        self.assertIn("no German text: Save", result.stderr)

    def test_complete_catalog_passes(self):
        result = self.run_check(
            'L("Save"); L(\n    "%d songs", 2\n); L("Status: \\"Ready\\"")\n'
            '// L("Comment")\n/* L("Block comment") */\n',
            {
                "Save": translated("Speichern"),
                "%d songs": translated("%d Titel"),
                'Status: "Ready"': translated('Status: "Bereit"'),
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("all translated (3 keys)", result.stdout)

    def test_format_mismatch_fails(self):
        result = self.run_check('L("%d songs", 2)', {"%d songs": translated("%@ Titel")})
        self.assertEqual(result.returncode, 1)
        self.assertIn("placeholders differ: %d songs", result.stderr)

    def test_no_lookup_keys_fails(self):
        result = self.run_check('// L("Comment")', {})
        self.assertEqual(result.returncode, 1)
        self.assertIn("no literal L lookup keys found", result.stderr)


if __name__ == "__main__":
    unittest.main()
