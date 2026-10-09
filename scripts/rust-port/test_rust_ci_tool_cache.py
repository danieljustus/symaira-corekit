"""Structural regression checks for pinned Rust CI tool caching.

Cache-hit/miss assertions below simulate the workflow's GitHub expression;
they do not execute actions/cache or claim remote cache evidence.
"""
from pathlib import Path
import re
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
CACHE_ACTION = "actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9"
INSTALL_ROOT = "${{ runner.temp }}/corekit-cargo-install-root"
CACHE_KEY = (
    "rust-tools-${{ runner.os }}-${{ runner.arch }}-rust-1.98.0-"
    "nextest-0.9.143-hack-0.6.45-llvm-cov-0.9.0-"
    "audit-0.22.2-deny-0.20.2"
)
INSTALL_COMMANDS = (
    "cargo install cargo-nextest --version 0.9.143 --locked",
    "cargo install cargo-hack --version 0.6.45 --locked",
    "cargo install cargo-llvm-cov --version 0.9.0 --locked",
    "cargo install cargo-audit --version 0.22.2 --locked",
    "cargo install cargo-deny --version 0.20.2 --locked",
)


def job_block(text, job_id):
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line == f"  {job_id}:"), None)
    if start is None:
        return ""
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if re.fullmatch(r"  [A-Za-z0-9_-]+:", lines[i])
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def step_block(job, name):
    lines = job.splitlines()
    marker = f"      - name: {name}"
    start = next((i for i, line in enumerate(lines) if line == marker), None)
    if start is None:
        return ""
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if lines[i].startswith("      - ")
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def install_step_runs(cache_hit):
    """Simulate `outputs.cache-hit != 'true'` for absent/miss/hit outputs."""
    return cache_hit != "true"


class RustToolCacheWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.job = job_block(cls.text, "rust-rust013-hardening")

    def test_job_has_exact_cache_root_key_and_no_broad_restore(self):
        block = step_block(self.job, "Cache Rust verification tools")
        self.assertIn("id: rust_tools_cache", block)
        self.assertIn(f"uses: {CACHE_ACTION} # v6.1.0", block)
        self.assertIn(f"path: {INSTALL_ROOT}", block)
        self.assertIn(f"key: {CACHE_KEY}", block)
        self.assertNotIn("restore-keys:", block)

    def test_miss_installs_all_exact_locked_tool_versions(self):
        block = step_block(self.job, "Install pinned Rust gate tools on cache miss")
        self.assertIn("if: steps.rust_tools_cache.outputs.cache-hit != 'true'", block)
        self.assertIn(f"CARGO_INSTALL_ROOT: {INSTALL_ROOT}", block)
        commands = tuple(line.strip() for line in block.splitlines() if line.strip().startswith("cargo install "))
        self.assertEqual(commands, INSTALL_COMMANDS)

    def test_missing_cold_and_warm_cache_controls(self):
        # Synthetic output values only; no cache action or runner is invoked.
        self.assertTrue(install_step_runs(""), "missing cache-hit output must install")
        self.assertTrue(install_step_runs("false"), "cold cache miss must install")
        self.assertFalse(install_step_runs("true"), "exact cache hit may skip installs")
        block = step_block(self.job, "Install pinned Rust gate tools on cache miss")
        self.assertIn("if: steps.rust_tools_cache.outputs.cache-hit != 'true'", block)

    def test_path_is_added_unconditionally_before_unchanged_hardening_gate(self):
        block = step_block(self.job, "Add Rust verification tools to PATH")
        self.assertIn(f"CARGO_INSTALL_ROOT: {INSTALL_ROOT}", block)
        self.assertIn('echo "$CARGO_INSTALL_ROOT/bin" >> "$GITHUB_PATH"', block)
        self.assertNotRegex(block, r"(?m)^\s+if:")
        self.assertLess(
            self.job.index("      - name: Add Rust verification tools to PATH"),
            self.job.index("      - name: Run complete dual-language hardening gate\n        run: make rust-hardening"),
        )


if __name__ == "__main__":
    unittest.main()
