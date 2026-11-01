# llmkit/providers.json

`providers.json` is the provider descriptor registry embedded by the Rust crate
`symaira-core-llm` (`rust/symaira-core-llm/src/provider.rs`). It is generated
from the shared contract source of truth
[`contracts/llm_providers.json`](../contracts/llm_providers.json); never edit it
by hand.

```sh
python3 scripts/rust-port/llm_providers_gen.py          # regenerate
python3 scripts/rust-port/llm_providers_gen.py --check  # drift gate (make rust-llm-contract)
```

The Go `llmkit` package was retired from `main` after v0.18.3
([ADR 0005](../docs/adr/0005-go-library-retirement.md)); Go consumers keep using
it at `v0.18.x`. The generator reproduces the former Go `llmkit/gen` output
byte for byte. The contract itself is documented in
[`docs/llm-provider-contract.md`](../docs/llm-provider-contract.md).
