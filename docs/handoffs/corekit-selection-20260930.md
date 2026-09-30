# Selected CoreKit cache/provider continuation

The maintainer authorized candidate selection and completion after the three-way
comparison. The selected source is `handoff/20260930-provider-repair` at
`f33920eb9a0938dd7cc0bfad326834f4d56a04f1`, reconciled onto
`handoff/20260930-cloud` starting at `43e059c9bfbba971d015d494d210ddc2f0bf5315`.
The alternative `signed-acceptance` has identical code; its name is not evidence
of signed-release acceptance. Both original alternative branches remain intact.

Only the provider/cache implementation and its tests were adopted, rather than
merging either branch or replacing the cloud handoff index. The selected changes
preserve ordered Go JSON field assignment and make Ollama Ping request the fixed
`/api/tags` endpoint even when model discovery is configured as static.

The comparison also exposed inherited cache gaps that are corrected here:

- Network JSON decoding accepts the first complete value, matching Go
  `Decoder.Decode`; persistent-cache decoding continues to require EOF.
- Cache serialization follows Go struct declaration order and HTML/line-separator
  escaping. RFC3339 timestamps omit unnecessary fractional trailing zeroes.
- Cache directories/files are created with Unix `0700`/`0600` permissions.
  Cache replacement uses a unique sibling file, sync, close, and handle-relative
  rename. Failed writes remove staging files and leave the prior entry intact.
  Windows uses the same bounded rename retry as the Go helper.

The live Go/Rust persistence differential checks timestamp-normalized bytes,
duplicate fields, trailing JSON, permissions under `umask 022`, hardlink
preservation on all native targets, Unix inode replacement, and deterministic
timestamp formatting. Additional tests preserve the old target and clean staging
files after a failed replacement, and clean dot components before creating parent
directories. It uses a new Go command
and a transient observation file. The original seven-case oracle, committed
fixtures, Oracle pins, Cargo.lock and frozen SQLite source captures are unchanged.
The capability filesystem adapter uses the already-pinned `cap-std` dependency,
so the change does not invalidate the frozen workspace build inputs.

## Reproduction and acceptance boundaries

Use Rust `1.98.0` and Go `1.26.6`, a fresh build-output directory for the reconciled
candidate, and no live provider credentials or application state:

```sh
umask 022
make rust-update-contract
make rust-llm-contract
cargo test --workspace --all-features --locked
python3 scripts/rust-port/generate.py --check-source
python3 scripts/rust-port/generate.py --check
python3 -m unittest discover -s scripts/rust-port/sqlite -p 'test_*.py'
```

The existing Apply test oracle creates initial executable files with the process
umask, while its Rust replay explicitly restores requested modes. Use the CI
runner's `022` umask for that broader gate; `077` exposes a pre-existing setup-mode
difference. This is recorded rather than changing its frozen oracle/fixture.

`make rust-update-signed-contract` verifies the existing pinned public Vault
release with real Cosign and applies it only to a disposable target. The CI
workflow now runs this separate acceptance gate with checksum-pinned Cosign
`v3.0.5`. It creates no release, tag or installed-product update. A local attempt
in the managed cloud failed because its network policy denied the Sigstore TUF
endpoint; no trust settings or network policy were bypassed. CI evidence at the
new exact PR head is required, including the native Windows contract/workspace
jobs. Prior successful candidate-head runs cannot certify the changed source.

Keep PR #358 draft while broader product acceptance remains incomplete. RUST-007
is still `in_progress`; UPD-005/009/010/011/012 are not promoted by this targeted
cache/provider repair. The full migration, distribution and release gates remain
separate. Preserve frozen evidence and Oracle ancestry; no history rewrite,
force-push, release, tag or branch-protection exception is authorized.
