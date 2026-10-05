#!/usr/bin/env python3
"""Run the complete update acceptance on this native host, with disposable HOME/XDG roots."""

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

from bounded_oracle_process import run_checked

ROOT = Path(__file__).resolve().parents[2]
REAL_COSIGN_TEST = "cosign::tests::real_cosign_rejects_invalid_signature_and_certificate"


def require_real_cosign_rejection(returncode: int, output: str) -> None:
    if (returncode != 0
            or f"test {REAL_COSIGN_TEST} ... ok" not in output
            or "test result: ok. 1 passed; 0 failed; 0 ignored;" not in output):
        raise RuntimeError("real Cosign rejection did not execute exactly one passing named test")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    args.report_dir = args.report_dir.resolve()
    args.report_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    home = Path.home()
    env.setdefault("CARGO_HOME", str(home / ".cargo"))
    env.setdefault("RUSTUP_HOME", str(home / ".rustup"))
    env["GOTOOLCHAIN"] = "go1.26.6"
    live = os.environ.get("GO_ORACLE") == "1"
    if live:
        caches = json.loads(subprocess.check_output(
            ["go", "env", "-json", "GOMODCACHE", "GOCACHE", "GOROOT"], cwd=ROOT, env=env, text=True))
        # Resolve the compiler only for explicitly requested live regeneration.
        env["GOROOT"] = caches.pop("GOROOT")
        env["PATH"] = str(Path(env["GOROOT"]) / "bin") + os.pathsep + env["PATH"]
        env.update(caches)
    report = {"status": "in_progress", "native_os": platform.system(), "native_arch": platform.machine(),
              "head_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "commands": [], "oracle_mode": "live-go" if live else "frozen-native-go"}
    fixture = args.report_dir / "native-apply.json"
    with tempfile.TemporaryDirectory(prefix="corekit-native-update-", dir=args.report_dir) as temporary:
        private = Path(temporary)
        for name in ("home", "config", "data", "cache", "tmp"):
            (private / name).mkdir()
        env.update({"HOME": str(private / "home"), "USERPROFILE": str(private / "home"),
                    "XDG_CONFIG_HOME": str(private / "config"), "XDG_DATA_HOME": str(private / "data"),
                    "XDG_CACHE_HOME": str(private / "cache"), "TMPDIR": str(private / "tmp"),
                    "TMP": str(private / "tmp"), "TEMP": str(private / "tmp"), "CGO_ENABLED": "0",
                    "GOTOOLCHAIN": "go1.26.6", "DEV_EXTERNAL": "", "CARGO_TARGET_DIR": str(ROOT / "target"),
                    "UPDATE_APPLY_FIXTURE": str(fixture)})
        commands = [
            ["make", "rust-update-version-contract", "rust-update-contract", "rust-update-signed-contract"],
            ["cargo", "test", "--manifest-path", str(ROOT / "Cargo.toml"), "-p", "symaira-core-update",
             "--lib", "--locked", REAL_COSIGN_TEST,
             "--", "--ignored", "--exact"],
            ["cargo", "nextest", "run", "--manifest-path", str(ROOT / "Cargo.toml"),
             "--locked", "-p", "symaira-core-update"],
        ]
        if live:
            commands.insert(0, [sys.executable, "scripts/rust-port/update-apply-differential.py", "--write", "--fixture", str(fixture)])
        else:
            from frozen_update_replay import read_capture
            from frozen_update_anchors import CAPTURE_SOURCE_COMMIT
            _, observations = read_capture("apply")
            fixture.write_text(json.dumps(observations, indent=2) + "\n", encoding="utf-8")
            report["oracle_source_commit"] = CAPTURE_SOURCE_COMMIT
        try:
            for command in commands:
                print("RUN " + " ".join(command), flush=True)
                output = ""
                if REAL_COSIGN_TEST in command:
                    observed = run_checked(
                        command, cwd=ROOT, env=env, timeout=120, merge_stderr=True,
                        artifact_dir=args.report_dir / "raw-real-cosign-rejection",
                    )
                    output = observed.stdout.decode("utf-8", "replace")
                    print(output, end="", flush=True)
                    result = subprocess.CompletedProcess(command, observed.returncode, output)
                else:
                    result = subprocess.run(command, cwd=ROOT, env=env, check=False)
                report["commands"].append({"argv": command, "exit_code": result.returncode})
                result.check_returncode()
                if REAL_COSIGN_TEST in command:
                    require_real_cosign_rejection(result.returncode, output)
                    report["commands"][-1].update(named_test=REAL_COSIGN_TEST, executed_tests=1)
            captured = json.loads(fixture.read_text(encoding="utf-8"))
            if not captured["cases"]:
                raise ValueError("native Go Apply capture contains no cases")
            native_goos = {"Darwin": "darwin", "Linux": "linux", "Windows": "windows"}[platform.system()]
            if captured["goos"] != native_goos:
                raise ValueError("Go Apply capture does not match the native runner")
            report["native_apply_cases"] = len(captured["cases"])
            report["status"] = "passed"
        finally:
            if report["status"] != "passed":
                report["status"] = "failed"
            (args.report_dir / "acceptance.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PASS complete native update acceptance: {report['native_os']}/{report['native_arch']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
