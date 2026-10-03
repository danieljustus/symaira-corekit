#!/usr/bin/env python3
"""Exercise Go and Rust Cosign against one pinned public signed release."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://github.com/danieljustus/symaira-vault/releases/download/v0.22.1/"
ASSETS = {
    "symaira-vault_0.22.1_checksums.txt": "e722249e12a560717f67af31db4d5153186442a243aee1a14b2a42a02f97ee05",
    "symaira-vault_0.22.1_checksums.txt.sig": "2012a27ad4bf0a7ce080f04d04557a664f26987597b58af4a7be44a66166560f",
    "symaira-vault_0.22.1_checksums.txt.pem": "32295da270034818625e04e51a0f8cd41796de3cf125cecf3e764e1f85c6b4a4",
}
RUST_TEST = "cosign::network_tests::signed_release_accepts_exact_bytes_and_rejects_tampering"
GO_TEST = "^TestRealSignedReleaseAcceptsAndRejects$"


def run(command, env):
    result = subprocess.run(
        command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, check=False, timeout=180,
    )
    if result.returncode:
        raise RuntimeError(f"{' '.join(command)} failed:\n{result.stdout}")
    return result.stdout


def main():
    if shutil.which("cosign") is None:
        raise RuntimeError("real Cosign verification requires a local cosign CLI")
    if shutil.which("curl") is None:
        raise RuntimeError("pinned artifact download requires curl")
    original_home = Path.home()
    toolchain = {}
    if os.environ.get("GO_ORACLE") == "1":
        toolchain = json.loads(run(["go", "env", "-json", "GOMODCACHE", "GOROOT"], dict(os.environ, GOTOOLCHAIN="go1.26.6")))
    with tempfile.TemporaryDirectory(prefix="corekit-cosign-valid-") as directory:
        for name, expected in ASSETS.items():
            result = subprocess.run(
                ["curl", "--fail", "--silent", "--show-error", "--location",
                 "--max-time", "60", "--max-filesize", "1048576", BASE + name],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                timeout=65,
            )
            if result.returncode:
                raise RuntimeError(f"download {name}: {result.stderr.decode(errors='replace')}")
            actual = hashlib.sha256(result.stdout).hexdigest()
            if actual != expected:
                raise RuntimeError(f"download {name}: pinned SHA-256 mismatch")
            (Path(directory) / name).write_bytes(result.stdout)
        env = dict(os.environ, GOTOOLCHAIN="go1.26.6", CGO_ENABLED="0",
                   COSIGN_VALID_FIXTURE_DIR=directory)
        env.update(toolchain)
        for variable, suffix in (("CARGO_HOME", ".cargo"), ("RUSTUP_HOME", ".rustup")):
            env[variable] = os.environ.get(variable, str(original_home / suffix))
        for variable, suffix in (("HOME", "home"), ("USERPROFILE", "home"), ("XDG_CACHE_HOME", "cache"), ("XDG_CONFIG_HOME", "config"), ("APPDATA", "config"), ("XDG_DATA_HOME", "data"), ("LOCALAPPDATA", "data"), ("XDG_STATE_HOME", "state"), ("TMPDIR", "tmp"), ("TMP", "tmp"), ("TEMP", "tmp")):
            private = Path(directory) / suffix
            private.mkdir(mode=0o700, exist_ok=True)
            env[variable] = str(private)
        rust = run(
            ["cargo", "test", "-p", "symaira-core-update", "--lib", "--locked",
             RUST_TEST, "--", "--ignored", "--exact"], env,
        )
        if "test result: ok. 1 passed;" not in rust:
            raise RuntimeError("the Rust real-signature test did not run exactly once")
        rejection = run(
            ["cargo", "test", "-p", "symaira-core-update", "--lib", "--locked",
             "cosign::tests::real_cosign_rejects_invalid_signature_and_certificate",
             "--", "--ignored", "--exact"], env,
        )
        if "test result: ok. 1 passed; 0 failed; 0 ignored;" not in rejection:
            raise RuntimeError("the real invalid-signature test did not execute exactly once")
        if os.environ.get("GO_ORACLE") == "1":
            go = run(
                ["go", "test", "-count=1", "-v", "./updatecheck/cosign", "-run", GO_TEST],
                env,
            )
            if "--- PASS: TestRealSignedReleaseAcceptsAndRejects" not in go:
                raise RuntimeError("the Go real-signature test did not pass")
            print("PASS explicit live Go real-signature acceptance and rejection")
        apply = run(
            ["cargo", "test", "-p", "symaira-core-update", "--test",
             "applier_real_release", "--locked", "--", "--ignored", "--exact",
             "real_signed_release_only_replaces_disposable_target"],
            env,
        )
        if "test result: ok. 1 passed;" not in apply:
            raise RuntimeError("the signed end-to-end Apply test did not run exactly once")
    print("PASS pinned public release assets match all three SHA-256 digests")
    print("PASS real Rust Cosign: valid signature accepted; tampered bytes and wrong identity rejected")
    print("PASS signed release asset fetched, verified, extracted and installed only to a disposable target")
    return 0


if __name__ == "__main__":
    sys.exit(main())
