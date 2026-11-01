"""The provider generator reproduces the committed registry and rejects drift."""
import json
import unittest

import llm_providers_gen as gen


class ProviderGeneratorTests(unittest.TestCase):
    def test_committed_registry_is_byte_identical(self):
        self.assertEqual(gen.generate(gen.SOURCE.read_bytes()), gen.TARGET.read_bytes())
        self.assertEqual(gen.main(["--check"]), 0)

    def test_changed_source_changes_output(self):
        source = json.loads(gen.SOURCE.read_bytes())
        source["providers"][0]["display_name"] += " (changed)"
        changed = gen.generate(json.dumps(source).encode("utf-8"))
        self.assertNotEqual(changed, gen.TARGET.read_bytes())

    def test_omitempty_fields_and_null_base_url(self):
        out = json.loads(gen.generate(json.dumps({"schema_version": 1, "providers": [{"id": "x"}]}).encode()))
        self.assertEqual(out["providers"][0], {
            "id": "x", "display_name": "", "base_url": None, "base_url_overridable": False,
            "auth_scheme": "", "dialect": "",
            "capabilities": dict.fromkeys(gen.CAPABILITIES, False),
            "models": {"mode": "", "default": ""},
        })


if __name__ == "__main__":
    unittest.main()
