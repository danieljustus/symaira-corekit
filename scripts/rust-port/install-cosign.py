#!/usr/bin/env python3
"""Install the existing CI Cosign pin for the native runner, after SHA-256 verification."""

import argparse
import hashlib
import os
from pathlib import Path
import platform
import subprocess
import tempfile

VERSION = "3.0.5"
# Published https://github.com/sigstore/cosign/releases/download/v3.0.5/cosign_checksums.txt
PINNED = {
    ("Linux", "x86_64"): ("cosign-linux-amd64", "db15cc99e6e4837daabab023742aaddc3841ce57f193d11b7c3e06c8003642b2"),
    ("Darwin", "x86_64"): ("cosign-darwin-amd64", "e032c44d3f7c247bbb2966b41239f88ffba002497a4516358d327ad5693c386f"),
    ("Darwin", "arm64"): ("cosign-darwin-arm64", "4888c898e2901521a6bd4cf4f0383c9465588a6a46ecd2465ad34faf13f09eb7"),
    ("Windows", "AMD64"): ("cosign-windows-amd64.exe", "44e9e44202b67ddfaaf5ea1234f5a265417960c4ae98c5b57c35bc40ba9dd714"),
}


def validate_download(path, expected):
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected:
        raise ValueError("Cosign download failed its pinned SHA-256 check")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    identity = (platform.system(), platform.machine())
    if identity not in PINNED:
        raise ValueError(f"unsupported native Cosign runner: {identity}")
    asset, expected = PINNED[identity]
    args.directory.mkdir(parents=True, exist_ok=True)
    destination = args.directory / ("cosign.exe" if identity[0] == "Windows" else "cosign")
    if destination.exists():
        raise FileExistsError("refusing to replace an existing verifier")
    with tempfile.TemporaryDirectory(prefix="cosign-download-", dir=args.directory) as temporary:
        download = Path(temporary) / asset
        subprocess.run(
            ["curl", "--fail", "--show-error", "--location", "--max-time", "120",
             "--max-filesize", "268435456",
             f"https://github.com/sigstore/cosign/releases/download/v{VERSION}/{asset}",
             "--output", str(download)],
            check=True, timeout=125,
        )
        validate_download(download, expected)
        download.chmod(0o755)
        download.rename(destination)
    version = subprocess.check_output([str(destination), "version"], text=True, timeout=15)
    if f"GitVersion:    v{VERSION}" not in version:
        raise ValueError("verified Cosign executable reported an unexpected version")
    if os.environ.get("GITHUB_PATH"):
        with open(os.environ["GITHUB_PATH"], "a", encoding="utf-8") as output:
            output.write(str(args.directory.resolve()) + "\n")
    print(f"PASS verified native Cosign v{VERSION}: {asset}")


if __name__ == "__main__":
    main()
