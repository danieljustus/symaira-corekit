#!/usr/bin/env python3
"""Validate CoreKit's dual-language release manifest without publishing.

The checked-in manifest is a release *plan*.  This verifier deliberately has
no publish mode: a future release job must make publication an explicit,
reviewed step after replacing the dry-run provenance marker with an immutable
commit and obtaining crates.io read-back evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, NoReturn

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = Path(__file__).with_name("manifest.json")
SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
TAG = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
SHA = re.compile(r"^[0-9a-f]{40}$")


class VerificationError(ValueError):
    """A release manifest or local release input is invalid."""


def fail(message: str) -> NoReturn:
    raise VerificationError(message)


def run(command: list[str], *, cwd: Path = ROOT) -> str:
    try:
        return subprocess.check_output(command, cwd=cwd, text=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as error:
        output = error.output.strip()
        detail = f": {output}" if output else ""
        fail(f"command failed ({' '.join(command)}){detail}")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"cannot read {path.relative_to(ROOT)}: {error}")
    if not isinstance(value, dict):
        fail(f"{path.relative_to(ROOT)} must contain an object")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_tag(value: object) -> str:
    if not isinstance(value, str) or not TAG.fullmatch(value):
        fail("release.tag must be a stable vMAJOR.MINOR.PATCH tag")
    return value


def validate_public_metadata(crate: dict[str, Any]) -> None:
    metadata = crate.get("public_metadata")
    if not isinstance(metadata, dict):
        fail(f"{crate.get('name', '<unknown>')}: publishable crates need public_metadata")
    required = {"description", "readme", "keywords", "categories"}
    missing = required - metadata.keys()
    if missing:
        fail(f"{crate['name']}: public_metadata is missing {sorted(missing)}")
    if not isinstance(metadata["description"], str) or not metadata["description"].strip():
        fail(f"{crate['name']}: public_metadata.description must be non-empty")
    if len(metadata["description"].encode("utf-8")) > 1_000:
        fail(f"{crate['name']}: public_metadata.description exceeds crates.io's 1000-byte limit")
    if (
        not isinstance(metadata["readme"], str)
        or not metadata["readme"]
        or Path(metadata["readme"]).is_absolute()
        or "\\" in metadata["readme"]
    ):
        fail(f"{crate['name']}: public_metadata.readme must be a relative POSIX path")
    for key in ("keywords", "categories"):
        values = metadata[key]
        if not isinstance(values, list) or not values or any(
            not isinstance(value, str) or not value.strip() for value in values
        ):
            fail(f"{crate['name']}: public_metadata.{key} must be a non-empty string array")


def validate_manifest_shape(manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schema_version") != 1:
        fail("manifest: unsupported schema_version")
    repository = manifest.get("repository")
    if not isinstance(repository, dict):
        fail("manifest: repository must be an object")
    for key in ("slug", "url", "go_module"):
        if not isinstance(repository.get(key), str) or not repository[key]:
            fail(f"manifest.repository.{key} must be non-empty")
    if repository["slug"] != "danieljustus/symaira-corekit":
        fail("manifest: repository slug is not CoreKit")
    release = manifest.get("release")
    if not isinstance(release, dict):
        fail("manifest: release must be an object")
    validate_tag(release.get("tag"))
    if release.get("source_revision") != "HEAD" and not SHA.fullmatch(str(release.get("source_revision", ""))):
        fail("release.source_revision must be HEAD for a dry-run or a 40-hex commit")
    if release.get("publish") is not False:
        fail("release.publish must remain false; this tool never publishes")
    if release.get("publication_status") != "not-run":
        fail("release.publication_status must be not-run until external publication is verified")
    if release.get("registry") != "https://crates.io":
        fail("release.registry must be crates.io")
    if not isinstance(release.get("planned_publish_order"), list):
        fail("release.planned_publish_order must be an array")
    crates = release.get("crates")
    if not isinstance(crates, list) or not crates:
        fail("release.crates must be a non-empty array")
    names: set[str] = set()
    for crate in crates:
        if not isinstance(crate, dict):
            fail("release.crates entries must be objects")
        required = {"name", "manifest", "version", "adopted", "publishable", "adopters", "reason"}
        missing = required - crate.keys()
        if missing:
            fail(f"release crate is missing {sorted(missing)}")
        name = crate["name"]
        if not isinstance(name, str) or not name or name in names:
            fail("release crate names must be unique non-empty strings")
        names.add(name)
        if not isinstance(crate["manifest"], str) or not crate["manifest"]:
            fail(f"{name}: manifest must be a non-empty path")
        if not isinstance(crate["version"], str) or not SEMVER.fullmatch(crate["version"]):
            fail(f"{name}: version must be stable SemVer without v prefix")
        if not isinstance(crate["adopted"], bool) or not isinstance(crate["publishable"], bool):
            fail(f"{name}: adopted and publishable must be booleans")
        if not isinstance(crate["adopters"], list) or any(
            not isinstance(adopter, str) or not adopter for adopter in crate["adopters"]
        ):
            fail(f"{name}: adopters must be a string array")
        if not isinstance(crate["reason"], str) or not crate["reason"].strip():
            fail(f"{name}: reason must be non-empty")
        if crate["publishable"] and not crate["adopted"]:
            fail(f"{name}: a non-adopted crate cannot be publishable")
        if crate["adopted"] and len(set(crate["adopters"])) < 2:
            fail(f"{name}: adopted crates need at least two independent adopters")
        if not crate["adopted"] and crate["adopters"]:
            fail(f"{name}: non-adopted crates must have no adopters")
        if crate["publishable"]:
            validate_public_metadata(crate)
        elif "public_metadata" in crate:
            fail(f"{name}: non-publishable crates must not declare public_metadata")
    order = release["planned_publish_order"]
    if len(order) != len(set(order)):
        fail("release.planned_publish_order contains duplicates")
    if set(order) - names:
        fail(f"release.planned_publish_order references unknown crates: {sorted(set(order) - names)}")
    adopted = {crate["name"] for crate in crates if crate["adopted"]}
    if set(order) != adopted:
        fail("release.planned_publish_order must contain every adopted crate and no other crate")
    provenance = release.get("provenance")
    if not isinstance(provenance, dict):
        fail("release.provenance must be an object")
    if not SHA.fullmatch(str(provenance.get("oracle_commit", ""))):
        fail("release.provenance.oracle_commit must be a 40-hex commit")
    inputs = provenance.get("input_files")
    if not isinstance(inputs, list) or not inputs or any(not isinstance(path, str) for path in inputs):
        fail("release.provenance.input_files must be a non-empty string array")
    if not isinstance(provenance.get("source_revision_policy"), str) or not provenance["source_revision_policy"].strip():
        fail("release.provenance.source_revision_policy must explain dry-run provenance")
    sbom = release.get("sbom")
    if not isinstance(sbom, dict) or sbom.get("required") is not True:
        fail("release.sbom.required must be true")
    if sbom.get("format") != "cargo-metadata-json" or not isinstance(sbom.get("command"), str):
        fail("release.sbom must declare the cargo metadata command")
    return release


def cargo_metadata() -> dict[str, Any]:
    output = run(["cargo", "metadata", "--locked", "--all-features", "--format-version", "1", "--no-deps"])
    try:
        value = json.loads(output)
    except json.JSONDecodeError as error:
        fail(f"cargo metadata returned invalid JSON: {error}")
    if not isinstance(value, dict) or not isinstance(value.get("packages"), list):
        fail("cargo metadata did not return packages")
    return value


def validate_workspace(release: dict[str, Any], metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    packages: dict[str, dict[str, Any]] = {
        package["name"]: package
        for package in metadata["packages"]
        if isinstance(package, dict) and isinstance(package.get("name"), str)
    }
    manifest_crates = {crate["name"]: crate for crate in release["crates"]}
    package_names = set(packages)
    manifest_names = set(manifest_crates)
    if package_names != manifest_names:
        fail(
            "manifest workspace coverage differs: "
            f"missing={sorted(package_names - manifest_names)} "
            f"extra={sorted(manifest_names - package_names)}"
        )
    for name, crate in manifest_crates.items():
        package = packages[name]
        expected_manifest = (ROOT / crate["manifest"]).resolve()
        try:
            expected_manifest.relative_to(ROOT.resolve())
        except ValueError:
            fail(f"{name}: manifest path escapes repository")
        actual_manifest = Path(package.get("manifest_path", "")).resolve()
        if actual_manifest != expected_manifest:
            fail(f"{name}: manifest path does not match cargo metadata")
        if package.get("version") != crate["version"]:
            fail(f"{name}: manifest version {crate['version']} differs from Cargo metadata {package.get('version')}")
        if crate["publishable"]:
            publish = package.get("publish")
            if publish is not None:
                fail(f"{name}: release marks crate publishable but Cargo does not allow crates.io publication")
            public_metadata = crate["public_metadata"]
            if package.get("description") != public_metadata["description"]:
                fail(f"{name}: Cargo description differs from release manifest public_metadata")
            if package.get("keywords") != public_metadata["keywords"]:
                fail(f"{name}: Cargo keywords differ from release manifest public_metadata")
            if package.get("categories") != public_metadata["categories"]:
                fail(f"{name}: Cargo categories differ from release manifest public_metadata")
            readme_value = Path(str(package.get("readme", "")))
            readme = (expected_manifest.parent / readme_value).resolve() if not readme_value.is_absolute() else readme_value.resolve()
            expected_readme = (expected_manifest.parent / public_metadata["readme"]).resolve()
            try:
                readme.relative_to(expected_manifest.parent.resolve())
            except ValueError:
                fail(f"{name}: Cargo readme path escapes the crate directory")
            if readme != expected_readme or not readme.is_file():
                fail(f"{name}: Cargo readme does not match release manifest public_metadata")
        elif package.get("publish") != []:
            fail(f"{name}: non-publishable crates must have Cargo publish = false")
        if not expected_manifest.is_file():
            fail(f"{name}: manifest does not exist")
    return manifest_crates


def validate_adoption(release: dict[str, Any]) -> None:
    evidence = read_json(ROOT / "testdata/rust-port/adoption/evidence.json")
    expected: dict[str, set[str]] = {}
    for consumer in evidence.get("consumers", []):
        if isinstance(consumer, dict) and isinstance(consumer.get("crate"), str) and isinstance(consumer.get("repository"), str):
            expected.setdefault(consumer["crate"], set()).add(consumer["repository"])
    for crate in release["crates"]:
        if crate["adopted"]:
            observed = set(crate["adopters"])
            if observed != expected.get(crate["name"], set()):
                fail(f"{crate['name']}: adopter list differs from tracked RUST-005 evidence")


def validate_git_provenance(release: dict[str, Any], selected_tag: str | None) -> str:
    tag = selected_tag or release["tag"]
    validate_tag(tag)
    if selected_tag is not None and selected_tag != release["tag"]:
        fail(f"selected tag {selected_tag} does not match manifest release tag {release['tag']}")
    current = run(["git", "rev-parse", "HEAD"]).strip()
    source_revision = release["source_revision"]
    resolved = current if source_revision == "HEAD" else source_revision
    if source_revision != "HEAD":
        run(["git", "cat-file", "-e", f"{source_revision}^{{commit}}"])
    tags = run(["git", "tag", "--list"]).splitlines()
    if any(tag_name.startswith(("rust-v", "rust/", "crate-v")) for tag_name in tags):
        fail("repository contains a Rust-specific tag; Go v* tags must remain the only release namespace")
    if not current:
        fail("cannot resolve current repository revision")
    return resolved


def package_candidates(release: dict[str, Any]) -> list[dict[str, Any]]:
    return [crate for crate in release["crates"] if crate["name"] in release["planned_publish_order"]]


def dry_run_packages(candidates: list[dict[str, Any]]) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="corekit-release-") as directory:
        target = Path(directory) / "target"
        for crate in candidates:
            run(
                [
                    "cargo",
                    "package",
                    "--locked",
                    "--target-dir",
                    str(target),
                    "--package",
                    crate["name"],
                    "--allow-dirty",
                ]
            )
            archive = target / "package" / f"{crate['name']}-{crate['version']}.crate"
            if not archive.is_file():
                fail(f"{crate['name']}: cargo package produced no expected archive")
            results.append((crate["name"], sha256(archive)))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="validate packaging and provenance without publishing")
    parser.add_argument("--tag", help="explicit vMAJOR.MINOR.PATCH tag to validate")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.dry_run:
        parser.error("only --dry-run is supported; publishing and tagging are intentionally unavailable")
    manifest_path = args.manifest.resolve()
    manifest = read_json(manifest_path)
    release = validate_manifest_shape(manifest)
    if manifest_path != MANIFEST_PATH.resolve():
        # Test callers may use a copied manifest, but paths still resolve from the repository.
        pass
    metadata = cargo_metadata()
    validate_workspace(release, metadata)
    validate_adoption(release)
    resolved_revision = validate_git_provenance(release, args.tag)
    for relative in release["provenance"]["input_files"]:
        path = (ROOT / relative).resolve()
        try:
            path.relative_to(ROOT.resolve())
        except ValueError:
            fail(f"provenance input escapes repository: {relative}")
        if not path.is_file():
            fail(f"missing provenance input: {relative}")
    candidates = package_candidates(release)
    if not candidates:
        fail("release.planned_publish_order has no candidates")
    package_results = dry_run_packages(candidates)
    input_digests = [f"{path}={sha256((ROOT / path).resolve())}" for path in release["provenance"]["input_files"]]
    print(f"ok: dry-run tag={args.tag or release['tag']} source_revision={resolved_revision}")
    print(f"ok: workspace_packages={len(metadata['packages'])} publish_candidates={len(candidates)} order={','.join(crate['name'] for crate in candidates)}")
    print("ok: package_archives=" + ",".join(f"{name}:{digest}" for name, digest in package_results))
    print(f"ok: sbom=cargo-metadata-json packages={len(metadata['packages'])}")
    print("ok: provenance_inputs=" + ",".join(input_digests))
    print("external gate: crates.io publication, ownership, and public-byte readback not run")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, VerificationError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
