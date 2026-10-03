#!/usr/bin/env python3
"""Replay frozen Go atomic-swap observations through Rust."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_static_runner import main_for_lane  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main_for_lane("swap"))
