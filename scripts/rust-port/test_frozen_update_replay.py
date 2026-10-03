"""Mutate actual native recordings and prove rejection before Rust execution."""
import json
from pathlib import Path
import tempfile
import unittest

import frozen_update_replay as replay


class FrozenUpdateTests(unittest.TestCase):
    def test_every_original_family_rejects_changed_bytes_and_restores(self):
        for lane in replay.COUNTS:
            with self.subTest(lane=lane):
                raw, observations = replay.read_capture(lane)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "recording.json"
                    path.write_bytes(raw)
                    self.assertEqual(replay.read_capture(lane, path)[0], raw)
                    mutated = json.loads(raw)
                    value = mutated["observations"]
                    cases = value if isinstance(value, list) else value["cases"]
                    row = cases[0]["input"] if lane == "apply" else cases[0]
                    row["id"] += "-mutated"
                    path.write_text(json.dumps(mutated), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "fixed reviewed bytes"):
                        replay.read_capture(lane, path)
                    path.write_bytes(raw.replace(b"\n", b"\r\n"))
                    with self.assertRaisesRegex(ValueError, "fixed reviewed bytes"):
                        replay.read_capture(lane, path)
                    path.write_bytes(raw)
                    self.assertEqual(replay.read_capture(lane, path)[1], observations)

    def test_original_raw_stream_drift_is_rejected_and_restored(self):
        target = "-".join(replay.native_goos_arch())
        for lane in replay.COUNTS:
            with self.subTest(lane=lane):
                path = replay.FIXTURES / target / f"{lane}.stdout"
                raw = path.read_bytes()
                try:
                    path.write_bytes(raw + b" ")
                    with self.assertRaisesRegex(ValueError, "raw stream changed"):
                        replay.read_capture(lane)
                finally:
                    path.write_bytes(raw)
                replay.read_capture(lane)


if __name__ == "__main__":
    unittest.main()
