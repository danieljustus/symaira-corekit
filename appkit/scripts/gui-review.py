#!/usr/bin/env python3
"""Mechanical review of Swift sources against GUIDELINES.md.

Usage:
    python3 scripts/gui-review.py [--format text|json] [--fail-on error|warn] ROOT...
    python3 scripts/gui-review.py --self-test

Checks only what a regular expression can decide. The manual checklist in
GUIDELINES.md section 13 remains the reviewer's job. Output is grouped by file
in `path:line - RULE-ID severity message` form; project-level absences are
reported once under `## project`.

Point it at product sources. Scanning `Sources/SymairaTheme` itself is noise:
the library defines the raw colors and legacy aliases that products must not
use.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXCLUDED_PARTS = {
    ".build",
    ".swiftpm",
    ".worktrees",
    ".app-test-build",
    "DerivedData",
    "Tests",
    "target-run",
    "docs",
}

# (rule, severity, pattern, message)
LINE_RULES = [
    ("COLOR-1", "error", r"Color\(hex:", "hex color; use a SymairaTokens role"),
    (
        "COLOR-1",
        "error",
        r"\b(foregroundStyle|foregroundColor|background|fill|tint|stroke|border)\("
        r"\s*(Color\.)?\.?(red|green|orange|yellow|blue|purple|pink|gray|white|black)\b",
        "raw system color; use SymairaTokens.ink/positive/warning/critical",
    ),
    (
        "TYPE-1",
        "error",
        r"\.font\(\.system\(size",
        "fixed-size system font; use SymairaTypography or .symairaText(_:)",
    ),
    (
        "TYPE-1",
        "warn",
        r"\.font\(\.(largeTitle|title|title2|title3|headline|subheadline|body|callout|caption|caption2|footnote)\)",
        "system text style; use a SymairaTypography role (bundled Google Sans Flex/Inter)",
    ),
    (
        "ICON-1",
        "warn",
        r"Image\(systemName:|systemImage:\s*\"",
        "SF Symbol string; use SymairaIcon (SymairaIconView, Label(_:symairaIcon:), icon: initializers)",
    ),

    (
        "ACTION-1",
        "warn",
        r"Button\(\s*\"(OK|Okay|Continue|Yes|No|Submit|Go|Proceed)\"",
        "vague button label; name the verb",
    ),
    ("COPY-3", "warn", r"\"[^\"\n]*\.\.\.[^\"\n]*\"", "three dots; use the ellipsis character …"),
    (
        "MOTION-4",
        "error",
        r"\b(LinearGradient|RadialGradient|AngularGradient|EllipticalGradient)\(",
        "gradient on a surface; Liquid Topography uses flat roles",
    ),
    ("MOTION-4", "info", r"\.shadow\(", "shadow; allowed only on floating elements (menus, popovers, composer)"),
    (
        "MOTION-6",
        "warn",
        r"\b(SymairaBackdrop|BlueprintGrid|AmbientGlows)\b|\.glassCard\(|\.glassmorphicPanel\(|Color\.symaira[A-Z]",
        "legacy compatibility API; use the current Liquid Topography components",
    ),
    ("FORM-1", "info", r"^\s*(Form\s*\{|GroupBox\b)", "native Form/GroupBox; use SymairaFormSection/SymairaFormRow"),
    (
        "SHELL-1",
        "info",
        r"\bNavigationSplitView\b",
        "NavigationSplitView; on macOS use SymairaWorkspace (iOS keeps native split/tab views)",
    ),
    ("MOTION-1", "info", r"\bSymairaTopoView\(", "direct topography view; pass topography: to SymairaWorkspace"),
]

ICON_ONLY = re.compile(r"\.labelStyle\(\.iconOnly\)")
A11Y_LABEL = re.compile(r"accessibilityLabel")
ICON_ONLY_WINDOW = 6
BARE_PROGRESS = re.compile(r"ProgressView\(\)")
PROGRESS_LABEL = re.compile(r"accessibilityLabel|Text\(")
PROGRESS_WINDOW = 3

# (rule, severity, pattern, message) -- reported once when no file in the root matches
PROJECT_RULES = [
    ("KEY-1", "info", r"\.keyboardShortcut\(|\bSymairaCommands\s*\(", "no keyboard shortcuts in this source root"),
    ("SHELL-9", "info", r"\.commands\s*\{|CommandMenu\(|CommandGroup\(|\bSymairaCommands\s*\(", "no app menu commands"),
    ("POINTER-2", "info", r"\.contextMenu\b", "no context menus on rows or cards"),
    ("POINTER-3", "info", r"\.help\(", "no tooltips on icon-only controls"),
    ("SHELL-7", "info", r"\b(?:Settings|SymairaSettingsScene)\s*(?:\{|\(\s*(?:content\s*:)?\s*\{)", "no Settings scene (the gear and ⌘, need one)"),
]

SEVERITY_RANK = {"info": 0, "warn": 1, "error": 2}
COMPILED_LINE_RULES = [(r, s, re.compile(p), m) for r, s, p, m in LINE_RULES]
COMPILED_PROJECT_RULES = [(r, s, re.compile(p, re.MULTILINE), m) for r, s, p, m in PROJECT_RULES]


def swift_files(root: Path):
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*.swift")):
        if EXCLUDED_PARTS.isdisjoint(path.relative_to(root).parts):
            yield path


def review_text(text: str, display: str) -> list[dict]:
    findings = []
    lines = text.splitlines()
    for index, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith("//") or stripped.startswith("import "):
            continue
        for rule, severity, pattern, message in COMPILED_LINE_RULES:
            if pattern.search(line):
                findings.append({"file": display, "line": index, "rule": rule, "severity": severity, "message": message})
        if BARE_PROGRESS.search(line):
            following = lines[index : index + PROGRESS_WINDOW]
            if not any(PROGRESS_LABEL.search(l) for l in following):
                findings.append(
                    {
                        "file": display,
                        "line": index,
                        "rule": "STATE-1",
                        "severity": "warn",
                        "message": 'bare ProgressView(); use SymairaLoadingState("Loading <noun>…") or add a label',
                    }
                )
        if ICON_ONLY.search(line):
            lo = max(0, index - 1 - ICON_ONLY_WINDOW)
            hi = min(len(lines), index + ICON_ONLY_WINDOW)
            if not any(A11Y_LABEL.search(l) for l in lines[lo:hi]):
                findings.append(
                    {
                        "file": display,
                        "line": index,
                        "rule": "ICON-2",
                        "severity": "warn",
                        "message": "icon-only label without accessibilityLabel nearby",
                    }
                )
    return findings


def review_roots(roots: list[Path]) -> tuple[list[dict], list[dict], int]:
    findings: list[dict] = []
    corpus: list[str] = []
    scanned = 0
    for root in roots:
        base = root if root.is_dir() else root.parent
        for path in swift_files(root):
            text = path.read_text(encoding="utf-8", errors="replace")
            scanned += 1
            corpus.append(text)
            findings.extend(review_text(text, path.relative_to(base).as_posix() if path != root else path.name))
    joined = "\n".join(corpus)
    project = [
        {"file": "project", "line": 0, "rule": rule, "severity": severity, "message": message}
        for rule, severity, pattern, message in COMPILED_PROJECT_RULES
        if scanned and not pattern.search(joined)
    ]
    return findings, project, scanned


def render_text(findings: list[dict], project: list[dict], scanned: int) -> str:
    out: list[str] = []
    by_file: dict[str, list[dict]] = {}
    for item in findings:
        by_file.setdefault(item["file"], []).append(item)
    for file in sorted(by_file):
        out.append(f"## {file}")
        for item in sorted(by_file[file], key=lambda i: (i["line"], i["rule"])):
            out.append(f"{file}:{item['line']} - {item['rule']} {item['severity']} {item['message']}")
        out.append("")
    if project:
        out.append("## project")
        for item in project:
            out.append(f"project - {item['rule']} {item['severity']} {item['message']}")
        out.append("")
    counts = {level: 0 for level in SEVERITY_RANK}
    for item in findings + project:
        counts[item["severity"]] += 1
    out.append(
        f"{scanned} Swift files scanned, {len(by_file)} with findings: "
        f"{counts['error']} error, {counts['warn']} warn, {counts['info']} info"
    )
    return "\n".join(out)


def self_test() -> int:
    fixture = """
import SwiftUI
// Image(systemName: "comment") must be ignored
struct Fixture: View {
    var body: some View {
        Text("Hi").foregroundStyle(.red)
        Text("Loading...")
        Image(systemName: "gear")
        Text("x").font(.system(size: 12))
        Text("y").font(.headline)
        ProgressView()
        Button("OK") {}
        Rectangle().fill(LinearGradient(colors: [], startPoint: .top, endPoint: .bottom))
        Label("Settings", systemImage: "gearshape").labelStyle(.iconOnly)
        SymairaBadge("ok", tone: .positive, systemImage: "checkmark")
        Text("fine").symairaText(.body).foregroundStyle(SymairaTokens.ink)
        SymairaLoadingState("Loading jobs…")
    }
}
"""
    found = review_text(fixture, "fixture.swift")
    expected = {"COLOR-1", "COPY-3", "ICON-1", "TYPE-1", "STATE-1", "ACTION-1", "MOTION-4", "ICON-2"}
    got = {item["rule"] for item in found}
    clean_lines = {17, 18}
    leaked = [item for item in found if item["line"] in clean_lines]
    comment_hits = [item for item in found if item["line"] == 3]
    project = [
        rule
        for rule, _, pattern, _ in COMPILED_PROJECT_RULES
        if not pattern.search(fixture)
    ]
    problems = []
    if got != expected:
        problems.append(f"rules: expected {sorted(expected)}, got {sorted(got)}")
    if leaked:
        problems.append(f"clean lines flagged: {leaked}")
    if comment_hits:
        problems.append(f"comment line flagged: {comment_hits}")
    if set(project) != {r for r, _, _, _ in PROJECT_RULES}:
        problems.append(f"project rules: {project}")
    shell_rules = {"KEY-1", "SHELL-7", "SHELL-9"}
    shell_cases = [
        ("", shell_rules),
        ("SymairaSettingsButton()", shell_rules),
        ("SymairaCommands(destinations: destinations, selection: $selection)", {"SHELL-7"}),
        ("SymairaSettingsScene { ProductSettings() }", {"KEY-1", "SHELL-9"}),
        ("SymairaSettingsScene(content: { ProductSettings() })", {"KEY-1", "SHELL-9"}),
        ("SymairaCommands(destinations: [], selection: $selection)\nSymairaSettingsScene { Text(\"Settings\") }", set()),
        ('.commands { CommandMenu("Navigate") { Button("Overview") {}.keyboardShortcut("1") } }\nSettings { Text("Settings") }', set()),
        ("let SymairaCommandsPreview = 1\nlet SymairaSettingsScenePreview = 1", shell_rules),
    ]
    for source, expected_absences in shell_cases:
        absences = {
            rule for rule, _, pattern, _ in COMPILED_PROJECT_RULES
            if rule in shell_rules and not pattern.search(source)
        }
        if absences != expected_absences:
            problems.append(f"shell fixture {source!r}: expected {sorted(expected_absences)}, got {sorted(absences)}")
    if problems:
        print("self-test FAILED\n" + "\n".join(problems))
        return 1
    print(f"self-test passed: {len(found)} findings on the fixture, {len(project)} project-level absences")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("roots", nargs="*", type=Path, help="Swift source roots or files")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--fail-on", choices=("error", "warn"), help="exit 1 when a finding of this severity or higher exists")
    parser.add_argument("--self-test", action="store_true", help="run the built-in fixture check and exit")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.roots:
        parser.error("at least one ROOT is required (or --self-test)")
    missing = [str(r) for r in args.roots if not r.exists()]
    if missing:
        parser.error(f"not found: {', '.join(missing)}")

    findings, project, scanned = review_roots(args.roots)
    if args.format == "json":
        print(json.dumps({"scanned": scanned, "findings": findings, "project": project}, indent=2, ensure_ascii=False))
    else:
        print(render_text(findings, project, scanned))

    if args.fail_on:
        threshold = SEVERITY_RANK[args.fail_on]
        if any(SEVERITY_RANK[item["severity"]] >= threshold for item in findings + project):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
