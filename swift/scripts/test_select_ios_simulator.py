#!/usr/bin/env python3
"""Regression tests for CI iOS Simulator device selection."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from select_ios_simulator import select_device  # noqa: E402

PREFIX = "com.apple.CoreSimulator.SimRuntime."


def device(name: str, udid: str, available: bool = True) -> dict:
    return {"name": name, "udid": udid, "isAvailable": available}


class SelectIOSSimulatorTests(unittest.TestCase):
    def test_prefers_newest_runtime_then_iphone_then_name(self) -> None:
        listing = {
            "devices": {
                PREFIX + "iOS-18-6": [device("iPhone 16", "old")],
                PREFIX + "iOS-27-2": [
                    device("iPad Pro 13-inch (M5)", "ipad"),
                    device("iPhone 18 Pro", "b"),
                    device("iPhone 17", "a"),
                ],
                PREFIX + "watchOS-27-0": [device("Apple Watch", "watch")],
            }
        }
        self.assertEqual(select_device(listing), "a")

    def test_compares_runtime_versions_numerically(self) -> None:
        listing = {
            "devices": {
                PREFIX + "iOS-9-3": [device("iPhone A", "nine")],
                PREFIX + "iOS-27-0": [device("iPhone Z", "twenty-seven")],
            }
        }
        self.assertEqual(select_device(listing), "twenty-seven")

    def test_ignores_unavailable_devices_and_other_platforms(self) -> None:
        listing = {
            "devices": {
                PREFIX + "iOS-27-2": [device("iPhone 17", "gone", available=False)],
                PREFIX + "tvOS-27-0": [device("Apple TV", "tv")],
            }
        }
        with self.assertRaisesRegex(RuntimeError, "No available iOS Simulator device"):
            select_device(listing)

    def test_runtime_without_devices_is_not_selectable(self) -> None:
        with self.assertRaises(RuntimeError):
            select_device({"devices": {PREFIX + "iOS-18-6": []}})


if __name__ == "__main__":
    unittest.main()
