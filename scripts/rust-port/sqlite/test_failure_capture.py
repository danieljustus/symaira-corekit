import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import candidate
import diff


class FailureCapture(unittest.TestCase):
    def test_failed_success_validation_retains_raw_observations(self):
        record = json.loads((diff.ROOT / 'testdata/rust-port/sqlite/differential-macos-bound.json').read_text())
        record['rust']['cases'][0]['success'] = False
        manifest, digest = candidate.load()
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            output = Path(directory) / 'failed.json'
            stack.enter_context(patch.object(sys, 'argv', ['diff.py', '--typed-errors', '--output', str(output)]))
            stack.enter_context(patch.object(candidate, 'load', return_value=(manifest, digest)))
            stack.enter_context(patch.object(candidate, 'snapshot', return_value=manifest['source_hashes']))
            stack.enter_context(patch.object(diff.generate, 'capture', return_value=record['go']))
            stack.enter_context(patch.object(diff, 'rust_capture', return_value=record['rust']))
            with self.assertRaisesRegex(ValueError, 'success'):
                diff.main()
            saved = json.loads(output.read_text())
            self.assertEqual(saved['verdict']['status'], 'failed')
            self.assertEqual(saved['go'], record['go'])
            self.assertEqual(saved['rust'], record['rust'])


if __name__ == '__main__':
    unittest.main()
