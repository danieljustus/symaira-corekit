#!/usr/bin/env python3
"""Native live Dynamic Type regression. Xcode + Python stdlib only; see docs/typography.md."""
import argparse
import hashlib
import json
import pathlib
import plistlib
import shutil
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "Tests/NativeTypography"
WEIGHTS = {
    "display": 700, "title": 700, "heading": 700, "subheading": 650,
    "body": 500, "bodyEmphasized": 700, "bodyMedium": 600, "label": 600,
    "callout": 500, "caption": 500, "micro": 650, "readout": 700, "stat": 700,
    "modifier-body": 500, "modifier-title": 700, "tabular-1": 700, "tabular-8": 700,
}
SAMPLES = set(WEIGHTS) | {"mono", "monoSmall"}
PHASES = ("large", "accessibility5", "large-restored")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest():
    paths = [ROOT / name for name in ("Package.swift", "Makefile", ".swift-format")]
    for folder in ("Sources", "Tests", "scripts", "contracts"):
        paths.extend(p for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)}


def check(data, bundled):
    assert data["fontAvailable"] == bundled
    for phase in PHASES:
        assert set(data[phase]) == SAMPLES, (phase, "missing/extra layout samples")
        assert set(data[phase + "-resolved"]) == SAMPLES, "Axis verification requires iOS 26+ runtime"
        assert abs(data[phase]["tabular-1"]["width"] - data[phase]["tabular-8"]["width"]) < 0.1
        for name, weight in WEIGHTS.items():
            font = data[phase + "-resolved"][name]
            assert (font["family"] == "Google Sans Flex") == bundled, (phase, name, font)
            if bundled:
                assert font["variation"][str(int.from_bytes(b"opsz", "big"))] == 18, (phase, name, font)
                assert font["variation"][str(int.from_bytes(b"wght", "big"))] == weight, (phase, name, font)
    for name in SAMPLES:
        base, maximum, restored = [data[phase][name] for phase in PHASES]
        assert maximum["height"] > base["height"] * 1.3, (name, base, maximum)
        assert base == restored, (name, "failed to restore", base, restored)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True, help="Already booted iOS 26+ simulator UDID")
    parser.add_argument("--build-dir", required=True, type=pathlib.Path)
    parser.add_argument("--evidence-dir", required=True, type=pathlib.Path, help="Fresh directory; never overwritten")
    parser.add_argument("--build-launcher", help="Optional external-build guard executable")
    args = parser.parse_args()
    build = args.build_dir.resolve()
    evidence = args.evidence_dir.resolve()
    assert not evidence.exists(), "Use a fresh evidence directory"
    assert not build.is_relative_to(ROOT) and not evidence.is_relative_to(ROOT), "Keep generated files outside the repo"
    evidence.mkdir(parents=True)
    commands = []

    def run(command, timeout=60, allow_failure=False):
        log = evidence / f"command-{len(commands):02d}.log"
        with log.open("x") as output:
            result = subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, timeout=timeout)
        commands.append(dict(command=command, exit=result.returncode, log=log.name))
        (evidence / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        assert allow_failure or result.returncode == 0, (command, result.returncode, str(log))
        return log.read_text().strip()

    inputs = manifest()
    (evidence / "source-manifest.json").write_text(json.dumps(inputs, indent=2) + "\n")
    devices = json.loads(run(["xcrun", "simctl", "list", "devices", "booted", "--json"]))
    assert any(d["udid"] == args.device for group in devices["devices"].values() for d in group), "Simulator must be booted"
    project = build / "host/TypographyProbe.xcodeproj"
    project.mkdir(parents=True, exist_ok=True)
    template = (FIXTURE / "project.pbxproj").read_text()
    assert template.count("__PACKAGE_PATH__") == 1
    (project / "project.pbxproj").write_text(template.replace("__PACKAGE_PATH__", json.dumps(str(ROOT))))
    shutil.copy2(FIXTURE / "Probe.swift", project.parent / "Probe.swift")
    run(([args.build_launcher] if args.build_launcher else []) + [
        "xcodebuild", "-project", str(project), "-scheme", "TypographyProbe", "-configuration", "Debug",
        "-sdk", "iphonesimulator", "-destination", "generic/platform=iOS Simulator",
        "-derivedDataPath", str(build / "derived"), "build"], timeout=600)
    original = build / "derived/Build/Products/Debug-iphonesimulator/TypographyProbe.app"
    info = plistlib.loads((original / "Info.plist").read_bytes())
    assert info["MinimumOSVersion"] == "17.0" and info["UIDeviceFamily"] == [1, 2], info
    binary = original / "TypographyProbe"
    load_commands = run(["xcrun", "vtool", "-show-build", str(binary)])
    assert "minos 17.0" in load_commands, load_commands
    results = []
    for bundled in (True, False):
        mode = "bundled" if bundled else "missing-resource"
        app = original
        bundle_id = info["CFBundleIdentifier"]
        if not bundled:
            app = build / "missing-resource/TypographyProbe.app"
            assert not app.exists(), "Preserve previous fallback copies; use another build directory"
            shutil.copytree(original, app, ignore=shutil.ignore_patterns("*.ttf"))
            bundle_id += ".fallback"
            fallback = dict(info, CFBundleIdentifier=bundle_id)
            (app / "Info.plist").write_bytes(plistlib.dumps(fallback))
            assert not list(app.rglob("*.ttf"))
        run(["xcrun", "simctl", "terminate", args.device, bundle_id], allow_failure=True)
        run(["xcrun", "simctl", "install", args.device, str(app)])
        started = time.time()
        launch = run(["xcrun", "simctl", "launch", args.device, bundle_id])
        pid = int(launch.rsplit(":", 1)[1])
        try:
            container = pathlib.Path(run(["xcrun", "simctl", "get_app_container", args.device, bundle_id, "data"])) / "Documents"
            path = container / "results.json"
            data = None
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if path.exists() and path.stat().st_mtime >= started:
                    candidate = json.loads(path.read_text())
                    if candidate.get("processID") == pid:
                        data = candidate
                        break
                time.sleep(0.25)
            assert data is not None, "No fresh result from the launched process within 30 seconds"
            shutil.copytree(container, evidence / mode)
            check(data, bundled)
            results.append(dict(mode=mode, pid=pid, samples=len(SAMPLES), phases=len(PHASES),
                                files={str(p.relative_to(app)): digest(p) for p in sorted(app.rglob("*")) if p.is_file()}))
        finally:
            run(["xcrun", "simctl", "terminate", args.device, bundle_id])
    assert inputs == manifest(), "Source changed during verification"
    (evidence / "receipt.json").write_text(json.dumps(dict(passed=True, runs=results, device=args.device), indent=2) + "\n")
    print(f"PASS: {len(results)} native runs, {len(SAMPLES)} samples each, large → accessibility5 → large; iOS floor 17.0")


if __name__ == "__main__":
    main()
