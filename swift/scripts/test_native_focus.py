#!/usr/bin/env python3
"""Run the native macOS Tab/Shift-Tab/Space focus regression without changing preferences."""
import argparse
import json
import pathlib
import shutil
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "Tests/NativeFocus"
STEPS = [
    "00-initial", "01-tab", "02-space", "03-tab", "04-space", "05-shift-tab",
    "06-space", "07-tab", "08-tab", "09-space", "10-space", "11-tab",
    "12-space", "13-tab", "14-space", "15-tab",
]
KEYS = [48, 49, 48, 49, 48, 49, 48, 48, 49, 49, 48, 49, 48, 49, 48]


def run(command, log, timeout=600):
    with log.open("a") as output:
        result = subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}; see {log}")


def preference():
    return subprocess.check_output(
        ["defaults", "read", "-g", "AppleKeyboardUIMode"], text=True
    ).strip()


def verify(data, scheme, evidence):
    assert data["fullKeyboardAccess"] is True, data
    assert "Optional(2)" in data["keyboardPreference"], data
    assert data["received"] == KEYS, data["received"]
    assert [row["step"] for row in data["rows"]] == STEPS
    rows = {row["step"]: row for row in data["rows"]}
    assert rows["02-space"]["selection"] == 1, rows["02-space"]
    assert rows["04-space"]["isOn"] is True, rows["04-space"]
    for row in data["rows"]:
        assert row["disabledSelection"] == 0, row
        assert row["disabledIsOn"] is False, row
    for step in STEPS:
        assert (evidence / scheme / f"{step}.png").is_file(), step


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", required=True, type=pathlib.Path)
    parser.add_argument("--evidence-dir", required=True, type=pathlib.Path)
    parser.add_argument("--build-launcher", help="Optional external-build guard executable")
    args = parser.parse_args()
    build = args.build_dir.resolve()
    evidence = args.evidence_dir.resolve()
    assert not build.is_relative_to(ROOT)
    assert not evidence.is_relative_to(ROOT)
    assert not evidence.exists(), "Use a fresh evidence directory"
    assert preference() == "2", "Enable Keyboard Navigation before running this passive host"
    evidence.mkdir(parents=True)
    build.mkdir(parents=True, exist_ok=True)
    log = evidence / "commands.log"
    project = build / "NativeFocusProbe.xcodeproj"
    project.mkdir()
    template = (FIXTURE / "project.pbxproj").read_text()
    assert template.count("__PACKAGE_PATH__") == 1
    (project / "project.pbxproj").write_text(template.replace("__PACKAGE_PATH__", json.dumps(str(ROOT))))
    shutil.copy2(FIXTURE / "Probe.swift", project.parent / "Probe.swift")
    launcher = [args.build_launcher] if args.build_launcher else []
    run(launcher + [
        "xcodebuild", "-project", str(project), "-scheme", "NativeFocusProbe", "-configuration", "Debug",
        "-derivedDataPath", str(build / "derived"), "build",
    ], log)
    app = build / "derived/Build/Products/Debug/NativeFocusProbe.app/Contents/MacOS/NativeFocusProbe"
    assert app.is_file(), app
    before = preference()
    results = {}
    for scheme in ("light", "dark"):
        output = evidence / scheme
        output.mkdir()
        started = time.monotonic()
        run([str(app), str(output), scheme], log, timeout=60)
        result = json.loads((output / "results.json").read_text())
        assert result["scheme"] == scheme
        assert time.monotonic() > started
        verify(result, scheme, evidence)
        results[scheme] = {
            "keyboardPreference": result["keyboardPreference"],
            "fullKeyboardAccess": result["fullKeyboardAccess"],
            "steps": len(result["rows"]),
        }
    after = preference()
    assert before == after == "2", (before, after)
    (evidence / "receipt.json").write_text(json.dumps({
        "passed": True,
        "preferenceBefore": before,
        "preferenceAfter": after,
        "runs": results,
        "input": "CGEvent keyDown/keyUp; no AXPress or programmatic focus",
    }, indent=2) + "\n")
    print("PASS: native Tab/Shift-Tab/Space focus and state regression passed in light and dark")


if __name__ == "__main__":
    main()
