"""Regression checks for the fail-closed CI merge gate."""
from pathlib import Path
import json
import os
import re
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_merge_gate  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "ci_merge_gate.py"
WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
FULL_JOBS = ("rust-foundation", "rust-update-signed", "port-contract")


def needs(full_result, **overrides):
    result = {job: {"result": "success"} for job in ci_merge_gate.ALWAYS}
    result.update({job: {"result": full_result} for job in FULL_JOBS})
    result.update({job: {"result": value} for job, value in overrides.items()})
    return result


def workflow_jobs():
    """Map top-level job id -> its YAML block text."""
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = lines.index("jobs:") + 1
    jobs, current = {}, None
    for line in lines[start:]:
        match = re.fullmatch(r"  ([A-Za-z0-9_-]+):", line)
        if match:
            current = match.group(1)
            jobs[current] = []
        elif current:
            jobs[current].append(line)
    return {job: "\n".join(body) for job, body in jobs.items()}


class EvaluateTests(unittest.TestCase):
    def test_full_scope_requires_every_job_success(self):
        self.assertEqual(ci_merge_gate.evaluate(needs("success"), "true"), [])

    def test_docs_scope_requires_full_jobs_skipped(self):
        self.assertEqual(ci_merge_gate.evaluate(needs("skipped"), "false"), [])

    def test_failed_or_cancelled_native_job_blocks(self):
        for bad in ("failure", "cancelled"):
            problems = ci_merge_gate.evaluate(needs("success", **{"rust-foundation": bad}), "true")
            self.assertTrue(any("rust-foundation" in p for p in problems), bad)

    def test_skipped_native_job_blocks_full_scope(self):
        problems = ci_merge_gate.evaluate(needs("success", **{"rust-update-signed": "skipped"}), "true")
        self.assertTrue(any("rust-update-signed" in p for p in problems))

    def test_unconditional_job_cannot_be_skipped(self):
        problems = ci_merge_gate.evaluate(needs("skipped", lint="skipped"), "false")
        self.assertTrue(any(p.startswith("lint:") for p in problems))

    def test_failed_scope_selector_blocks(self):
        problems = ci_merge_gate.evaluate(needs("skipped", changes="failure"), "")
        self.assertTrue(problems)

    def test_missing_unconditional_dependency_blocks(self):
        partial = needs("success")
        del partial["apidiff"]
        problems = ci_merge_gate.evaluate(partial, "true")
        self.assertTrue(any("apidiff" in p for p in problems))

    def test_cli_fails_closed_on_missing_or_empty_results(self):
        base = {k: v for k, v in os.environ.items() if k not in ("NEEDS_JSON", "CI_FULL_SCOPE")}
        for extra in ({}, {"NEEDS_JSON": "{}", "CI_FULL_SCOPE": "true"}, {"NEEDS_JSON": "not json"}):
            run = subprocess.run([sys.executable, "-B", str(SCRIPT)], env={**base, **extra},
                                 capture_output=True, text=True, check=False)
            self.assertEqual(run.returncode, 1, extra)

    def test_cli_passes_satisfied_results(self):
        env = {**os.environ, "NEEDS_JSON": json.dumps(needs("success")), "CI_FULL_SCOPE": "true"}
        run = subprocess.run([sys.executable, "-B", str(SCRIPT)], env=env,
                             capture_output=True, text=True, check=False)
        self.assertEqual(run.returncode, 0, run.stderr)


class WorkflowCoverageTests(unittest.TestCase):
    def test_gate_needs_every_pull_request_job(self):
        jobs = workflow_jobs()
        gate = jobs["merge-gate"]
        match = re.search(r"^    needs:\n((?:      - .+\n?)+)", gate + "\n", re.M)
        self.assertIsNotNone(match, "merge-gate must list needs as a block sequence")
        gated = set(re.findall(r"      - ([A-Za-z0-9_-]+)", match.group(1)))
        dispatch_only = {
            job for job, body in jobs.items()
            if re.search(r"^    if: github\.event_name == 'workflow_dispatch' &&", body, re.M)
        }
        expected = set(jobs) - dispatch_only - {"merge-gate"}
        self.assertEqual(gated, expected)
        self.assertLessEqual(ci_merge_gate.ALWAYS, gated)

    def test_gate_always_runs_and_reads_scope(self):
        gate = workflow_jobs()["merge-gate"]
        self.assertIn("    if: always() && github.event_name != 'workflow_dispatch'", gate)
        self.assertIn("NEEDS_JSON: ${{ toJSON(needs) }}", gate)
        self.assertIn("CI_FULL_SCOPE: ${{ needs.changes.outputs.full }}", gate)


if __name__ == "__main__":
    unittest.main()
