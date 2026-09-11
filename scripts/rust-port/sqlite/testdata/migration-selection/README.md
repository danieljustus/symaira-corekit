# SQL-003 migration filename selection

One case, `SQL-003/migration-selection`, closes a previously unproven part of
SQL-003. The existing Rust-only sorting test and two-file differential corpus
did not exercise `.sql` directories, uppercase/backup extensions or repeated
suffixes against generated Go observations.

`cases.json` is language-neutral input. `main.go` calls production
`sqlitekit.Migrate` from commit `f3d3eb79b9b1f31b4f973d2ed518a8292cedf588`,
using Go 1.26.6, `CGO_ENABLED=0`, and the pinned module graph. It records actual
reads, persisted versions, schema SQL and ordered rows. The Go filesystem
boundary is `fs.FS`; Rust feeds the identical entries through `MigrationSource`.
The Rust entry list deliberately retains the unsorted manifest order.

Comparison modes:

- Semantic JSON: exact scalar types, array order and all observed fields;
  JSON object key order and serialization whitespace are insignificant.
- SQLite: exact `sqlite_master` SQL strings, versions ordered by version,
  and data ordered by integer row ID. Row IDs expose lexical execution order
  (`10_add.sql` precedes `2_add.sql`). Only the final `.sql` suffix is removed.
- Bytes: SHA-256 of pinned production/test sources and executed harness/input
  bytes must match on regeneration. SQL strings receive no whitespace rewrite.
- Filesystem: no filesystem equality claim; both migration sources and databases
  are in memory. Applied timestamps, database file bytes, errors and locking are
  outside this filename-selection slice. There are no observation normalizers.

Run from the assigned checkout, with an internal scratch directory and a
candidate-specific build directory (external storage on Daniel's Mac):

```sh
python3 scripts/rust-port/sqlite/testdata/migration-selection/capture.py \
  --scratch-root "$scratch" --build-root "$build" --evidence-root "$evidence"
# Repeat with --check; this regenerates through Go and rejects any drift.
python3 -m unittest discover -s scripts/rust-port/sqlite/testdata/migration-selection -p 'test_*.py' -v
cargo test --manifest-path "$manifest" --locked -p symaira-core-sqlite \
  --test migration_selection migration_selection_matches_pinned_go -- --exact --nocapture
```

Capture verifies source/module directories, dependency versions and compiler/runtime
identity separately. It also executes the pinned `TestMigrate` with `-count=1`
and rejects a zero-match run. HOME/XDG/temp roots are fresh; Go build outputs
stay under `--build-root`. Shared toolchain/download caches are reused; this is
path/environment isolation, not an OS sandbox. No credential or user-data APIs
are involved. Declare `CARGO_TARGET_DIR` per candidate and isolate HOME/XDG/temp
when running Rust. Capture evidence records commands and raw Go stdout.

This fixture does not complete SQL-003 or RUST-006. Native platform, independent
source review, consumer integration and cost gates remain coordinator work.
Existing broad fixture/source manifests are deliberately not refreshed here.
