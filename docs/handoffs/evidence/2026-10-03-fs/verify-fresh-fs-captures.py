"""Read-only verifier for genuine 5fc5299 native captures; not Rust acceptance."""
from pathlib import Path, PureWindowsPath
import copy
import hashlib
import json
import re
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parent
HEAD = "5fc5299a56e96b6007fda7d8900363f3aa6ba282"
SOURCE = ROOT / "source-5fc5299"
sys.path.insert(0, str(SOURCE / "scripts/rust-port"))
import fs_secret_oracle as oracle

OFFICIAL = {
    "darwin-arm64": ("go1.26.6.darwin-arm64.tar.gz", "2dc95ce4675829f2df0e86b28bcef3283635902062a5f0580ca659bf570f3204"),
    "linux-amd64": ("go1.26.6.linux-amd64.tar.gz", "708effb774be8237570d0add163225abbdfaf4fca28b2611df167beba4feef89"),
    "windows-amd64": ("go1.26.6.windows-amd64.zip", "5b6c5b556525810463b5c897b50dc7a82d6a3dc0bfaf55d990a7e9f31d6b2318"),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def verify(row, altered=None):
    raw = (ROOT / row["fixture"]).read_bytes()
    payload = json.loads(raw) if altered is None else altered
    target = row["target"]
    oracle.validate_capture_payload(payload, tuple(target.split("-")))
    cap = payload["capture"]
    assert cap["candidate"]["head_before"] == cap["candidate"]["head_after"] == HEAD
    assert cap["candidate"]["clean_before"] is True and cap["candidate"]["clean_after"] is True
    oracle._verify_candidate_files(cap, SOURCE)
    files = {item["path"]: item["sha256"] for item in cap["inputs"]["files"]}
    embedded = {"candidate/contracts/secret_refs.json", "candidate/testdata/rust-port/fixtures/fs-secret/corpus.json"}
    assert embedded.issubset(files)
    for item in cap["oracle"]["source_files"]:
        assert digest((ROOT / "oracle-f3d3eb7-source" / item["path"]).read_bytes()) == item["sha256"]
    art = (ROOT / row["raw_root"])
    run = json.loads((art / "run.json").read_bytes())
    assert run["status"] == "captured-unreviewed"
    assert run["fixture_sha256"] == digest(raw)
    assert canonical(run["commands"]) == canonical(cap["commands"])
    assert digest((art / "go-probe.binary").read_bytes()) == cap["go"]["probe_binary_sha256"]
    streams = 0
    for command in cap["commands"]:
        assert command["exit_code"] == 0 and command["cleanup_verified"] is True
        assert command["timed_out"] is False and command["output_exceeded"] is False
        for stream in ("stdout", "stderr"):
            data = (art / "raw" / (command["id"] + "." + stream + ".raw")).read_bytes()
            assert len(data) == command[stream + "_bytes"]
            assert digest(data) == command[stream + "_sha256"]
            streams += 1
    cases = json.loads((art / "raw/go-cases.stdout.raw").read_bytes())
    controls = json.loads((art / "raw/go-path-controls.stdout.raw").read_bytes())
    assert cases["native_target"] == target and cases["oracle_commit"] == oracle.ORACLE
    assert set(cases["cases"]) == set(oracle.CASE_IDS) and len(cases["cases"]) == 13
    assert canonical(cases["cases"]) == canonical(payload["observations"]["cases"]), "original Go case bytes differ"
    assert set(controls) == set(oracle.PATH_CONTROL_IDS) and len(controls) == 9
    assert all(type(value) is bool for value in controls.values())
    assert canonical(controls) == canonical(payload["observations"]["path_controls"])
    assert all(controls[key] is True for key in oracle.STRICT_V1_GO_ACCEPTED)
    assert (art / "raw/git-status-before.stdout.raw").read_bytes() == b""
    assert (art / "raw/git-status-after.stdout.raw").read_bytes() == b""
    assert (art / "raw/git-head-before.stdout.raw").read_bytes().strip().decode() == HEAD
    assert (art / "raw/git-head-after.stdout.raw").read_bytes().strip().decode() == HEAD
    assert cap["inputs"]["before_sha256"] == cap["inputs"]["after_sha256"]
    for item in cap["inputs"]["files"]:
        if item["path"].startswith("oracle/"):
            assert digest((ROOT / "oracle-f3d3eb7-source" / item["path"][7:]).read_bytes()) == item["sha256"]
    packages = oracle._parse_go_list((art / "raw/go-list-before.stdout.raw").read_bytes())
    replacements = {p["Module"]["Replace"]["Dir"] for p in packages if isinstance(p.get("Module"), dict) and isinstance(p["Module"].get("Replace"), dict)}
    assert len(replacements) == 1
    replacement = next(iter(replacements))
    spelling = PureWindowsPath(replacement).as_posix() if target.startswith("windows") else replacement
    helper = SOURCE / "scripts/rust-port/go-oracle"
    original = (helper / "go.mod").read_text()
    line = "replace github.com/danieljustus/symaira-corekit => ../../.."
    assert original.count(line) == 1
    effective = original.replace(line, "replace github.com/danieljustus/symaira-corekit => " + json.dumps(spelling, ensure_ascii=False))
    if target.startswith("windows"):
        effective = effective.replace("\n", "\r\n")
    modules = {
        "modules/current-helper/effective.mod": effective.encode(),
        "modules/current-helper/effective.sum": (helper / "go.sum").read_bytes(),
        "modules/current-helper/source-go.mod": (helper / "go.mod").read_bytes(),
        "modules/current-helper/source-go.sum": (helper / "go.sum").read_bytes(),
        "modules/replacement/go.mod": (ROOT / "oracle-f3d3eb7-source/go.mod").read_bytes(),
        "modules/replacement/go.sum": (ROOT / "oracle-f3d3eb7-source/go.sum").read_bytes(),
    }
    assert {path for path in files if path.startswith("modules/")} == set(modules)
    assert all(digest(data) == files[path] for path, data in modules.items())
    filename, checksum = OFFICIAL[target]
    archive = ROOT / "sdk" / filename
    with archive.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == checksum
    sdk = {"go/" + path[4:]: value for path, value in files.items() if path.startswith("sdk/")}
    found = set()
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as package:
            for name, value in sdk.items():
                with package.open(name) as stream:
                    assert hashlib.file_digest(stream, "sha256").hexdigest() == value, name
                found.add(name)
    else:
        with tarfile.open(archive, "r:gz") as package:
            for member in package:
                if member.name in sdk:
                    assert member.isfile()
                    with package.extractfile(member) as stream:
                        assert hashlib.file_digest(stream, "sha256").hexdigest() == sdk[member.name], member.name
                    found.add(member.name)
    assert found == set(sdk)
    compiler = "go/bin/go" + (".exe" if target.startswith("windows") else "")
    assert sdk[compiler] == cap["go"]["binary_sha256"]
    assert not re.search(rb"/Users/[^/]+/\.hermes|/private/var|/var/folders|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY", raw)
    return {"target": target, "fixture": row["fixture"], "fixture_sha256": digest(raw), "raw_root": str(art), "job": row["job"], "case_count": 13, "path_control_count": 9, "command_count": len(cap["commands"]), "raw_streams_verified": streams, "sdk_inputs_verified": len(found), "module_inputs_reproduced": len(modules), "embedded_inputs_bound": sorted(embedded), "official_sdk_sha256": checksum, "verified": True}


def main():
    manifest = json.loads((ROOT / "source-5fc5299-manifest.json").read_bytes())
    assert manifest["source_commit"] == HEAD and len(manifest["files"]) == 630
    assert all(digest((SOURCE / item["path"]).read_bytes()) == item["sha256"] for item in manifest["files"])
    locations = json.loads((ROOT / "fresh-5fc-native-locations.json").read_bytes())
    assert locations["head"] == HEAD and locations["run"] == 37107725386
    assert {row["target"] for row in locations["captures"]} == set(OFFICIAL)
    results = []
    for row in locations["captures"]:
        result = verify(row)
        mutated = copy.deepcopy(json.loads((ROOT / row["fixture"]).read_bytes()))
        value = mutated["observations"]["cases"]["FS-001"]["outcomes"]["valid/file"]["ok"]
        assert type(value) is bool
        mutated["observations"]["cases"]["FS-001"]["outcomes"]["valid/file"]["ok"] = not value
        try:
            verify(row, mutated)
        except AssertionError as error:
            assert str(error) == "original Go case bytes differ", str(error)
        else:
            raise AssertionError("modified observation accepted against original native raw stream")
        result["actual_observation_mutation_rejected"] = True
        results.append(result)
        print(json.dumps(result, sort_keys=True), flush=True)
    report = {"source_commit": HEAD, "native_capture_run": 37107725386, "source_files": 630, "verifier_sha256": digest(Path(__file__).read_bytes()), "captures": results, "scope": "complete original Go/native provenance verification; independent anchor decision and native Rust acceptance still required"}
    (ROOT / "fresh-5fc-full-verification.json").write_bytes((json.dumps(report, indent=2) + "\n").encode())


if __name__ == "__main__":
    main()
