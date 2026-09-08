# symaira-core-version

A small, dependency-light version handshake payload for Symaira command-line
tools. It preserves the shared `{tool, version, schema_version}` JSON contract
and provides compact JSON and plain-text writers.

## Example

```rust
use symaira_core_version::new;

let info = new("symvault", "1.2.3", 1);
assert_eq!(info.to_string(), "symvault 1.2.3");
```

Use [`Info::json`](https://docs.rs/symaira-core-version/0.1.0/symaira_core_version/struct.Info.html#method.json)
for compact JSON bytes or [`Info::write`](https://docs.rs/symaira-core-version/0.1.0/symaira_core_version/struct.Info.html#method.write)
to write the JSON payload followed by exactly one newline.

The crate is Apache-2.0 licensed and requires Rust 1.98 or newer.
