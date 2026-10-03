# ADR 0003: Pin native macOS CI to the supported ARM64 compatibility runner

Status: accepted, 2026-10-03.

## Decision

Run the macOS lanes on GitHub's `macos-15` ARM64 runner. Verify `uname -m` is
`arm64` and print `sw_vers` in every native macOS job. Keep Linux and Windows,
all contract case counts, mutation controls, strict byte/source binding,
security/Miri, API and real signed-release acceptance gates.

Existing check contexts such as `test (macos-26)` retain their historical names
for branch-protection compatibility. The matrix value is a **legacy check
context**, not a statement of the executing macOS version. `runs-on`, the
recorded runner identity and job logs identify the actual supported runner.
Artifact names may retain that same context; no historical observation or
provenance record is relabeled as a new capture.

## Reasoning

Required macOS-26 jobs remained queued for more than seven hours while their
Linux/Windows peers completed. GitHub's public status reported Actions
operational, so there is no evidence to blame a general outage. The supported
[runner image catalog](https://github.com/actions/runner-images) lists both
`macos-15` and `macos-26` as ARM64; `macos-15-intel` is a different architecture.
Pinning the older supported native runtime also tests compatibility below the
newest operating system and avoids a moving `macos-latest` alias.

This changes runner selection, not acceptance. Genuine Darwin/ARM64 frozen Go
captures keep their original bytes and capture identity. Actual Rust still
replays their observations natively, and source-bound reports remain required.
Never count queued, skipped, zero-case or cross-compiled runs as native proof.
A runner selection cannot prove another OS version has been tested.

## Maintenance

Move to a newer supported runner before macOS 15 is retired, after exact-source
native contract and security acceptance there. A future check-name cleanup
must migrate protected required contexts atomically with repository settings;
until then preserving their names avoids removing an enforced gate. Do not
disable branch protection or merge through failing required checks.

For transient infrastructure failures, permit one bounded rerun on the same
source only after examining its actual error. An observed Linux `ETXTBSY` when
starting a freshly written test fixture is such a candidate; reproducible
failure requires a fix. A rerun does not replace a passing test or alter its
assertions, inputs or process-cleanup requirements.
