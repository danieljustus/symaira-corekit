#!/usr/bin/env python3
"""Generate llmkit/providers.json from the contracts/llm_providers.json SSOT.

Replaces the retired Go generator `llmkit/gen` (v0.18.3) byte for byte:
same field order, the same omitempty rules, two-space indent, no HTML
escaping and a trailing newline. `symaira-core-llm` embeds the output.

    python3 scripts/rust-port/llm_providers_gen.py          # rewrite
    python3 scripts/rust-port/llm_providers_gen.py --check  # fail on drift
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "contracts/llm_providers.json"
TARGET = ROOT / "llmkit/providers.json"
CAPABILITIES = ("streaming", "tool_use", "embeddings", "vision", "system_prompt")


def _str(value) -> str:
    return value if isinstance(value, str) else ""


def generate(source: bytes) -> bytes:
    src = json.loads(source)
    providers = []
    for p in src.get("providers") or []:
        auth = p.get("auth") or {}
        models = p.get("models") or {}
        caps = p.get("capabilities") or {}
        q = {
            "id": _str(p.get("id")),
            "display_name": _str(p.get("display_name")),
            "base_url": p["base_url"] if isinstance(p.get("base_url"), str) else None,
            "base_url_overridable": bool(p.get("base_url_overridable")),
        }
        if p.get("base_url_required_override"):
            q["base_url_required_override"] = True
        q["auth_scheme"] = _str(auth.get("scheme"))
        if _str(auth.get("header")):
            q["auth_header"] = auth["header"]
        headers = p.get("extra_headers") or {}
        if headers:
            q["extra_headers"] = dict(sorted(headers.items()))
        q["dialect"] = _str(p.get("dialect"))
        if p.get("dialect_configurable"):
            q["dialect_configurable"] = True
        q["capabilities"] = {name: bool(caps.get(name)) for name in CAPABILITIES}
        out_models = {"mode": _str(models.get("mode"))}
        if _str(models.get("discovery_path")):
            out_models["discovery_path"] = models["discovery_path"]
        out_models["default"] = _str(models.get("default"))
        q["models"] = out_models
        if _str(p.get("credential_ref_env_default")):
            q["credential_env_default"] = p["credential_ref_env_default"]
        providers.append(q)
    # Go encodes the nil slice of an empty registry as null and always escapes
    # U+2028/U+2029, even with HTML escaping disabled.
    out = {"schema_version": int(src.get("schema_version") or 0), "providers": providers or None}
    text = json.dumps(out, indent=2, ensure_ascii=False).replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return (text + "\n").encode("utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail when llmkit/providers.json drifts")
    args = parser.parse_args(argv)
    generated = generate(SOURCE.read_bytes())
    if args.check:
        if TARGET.read_bytes() != generated:
            print("llmkit/providers.json differs from contracts/llm_providers.json; "
                  "run scripts/rust-port/llm_providers_gen.py", file=sys.stderr)
            return 1
        print("PASS llmkit/providers.json matches contracts/llm_providers.json")
        return 0
    TARGET.write_bytes(generated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
