# FS-001-RUST-STRICT-v1

`symaira_core_fs::validate_path` retains its existing Rust safety policy. This is an explicit, versioned deviation from Go `fsutil.ValidatePath`, not a universal accept/reject parity claim.

| Boundary | Pinned Go public API | Rust strict contract v1 |
| --- | --- | --- |
| NUL and U+001F | Reject | Reject |
| U+0020 and U+007E | Accept within an otherwise valid relative path | Accept |
| DEL, U+007F | Accept | Reject |
| C1 controls, U+0080 through U+009F | Accept | Reject |
| NBSP, U+00A0 | Accept | Accept |

The Rust control predicate remains `char::is_control()`. Do not weaken it to Go's `r < 0x20` merely to obtain a parity label. Changing this rejection boundary requires a new contract version and migration review. The crate remains unpublished at `0.0.0`; this records an existing behavior rather than introducing a released breaking change.

## Executable evidence

- `scripts/rust-port/go-oracle/cmd/fssecret/main.go --path-controls` calls the real public Go API from pinned revision `f3d3eb79b9b1f31b4f973d2ed518a8292cedf588`. Input scalars and keys are constructed as ASCII hexadecimal, avoiding transports that strip literal C1 characters.
- `scripts/rust-port/fs-path-control-differential.py` uses the existing disposable pinned Go builder, isolated HOME/XDG/temp/cache paths and nine actual observations. It explicitly executes `fs001_strict_v1_replays_go_controls`, including the four sampled DEL/C1 deviations, and rejects an actually mutated Go acceptance.
- Native Linux/macOS/Windows CI runs this differential in the existing RUST-003 job and retains `fs-path-control-native.json` with exact source HEAD, production/helper digests, recorded Go values and actual Rust exit codes.
- Existing thirteen FS/SEC observable rows continue through `diff_fs_secret.py`; no normalization conceals this separate, explicitly versioned control-character boundary.

These are execution requirements, not a claim that pending CI already passed. The earlier ad-hoc C1 stdout capture was incomplete because literal C1 characters were removed in transit; it is not accepted evidence for those cases.

## Error adaptation

Go's wrappable `ErrInvalidPath` sentinel maps to typed Rust `FsError::InvalidPath`. Consumers classify the variant rather than comparing formatted messages or expecting Go `errors.Is` identity. Filesystem capability, symlink, mode, atomic-write and rollback protections remain unchanged.
