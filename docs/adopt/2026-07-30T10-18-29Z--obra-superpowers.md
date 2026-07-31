<!-- review: timestamp=2026-07-30T10:18:29Z  repo=danieljustus/symaira-corekit  head=ec8368b1c4c3331729f4187be0cb1df155972655 -->
<!-- adopt: source=obra/superpowers  source_ref=44c9b2d6e889982ac18c27d05a19fefe335194e1  source_url=https://github.com/obra/superpowers  depth=clone  license=MIT -->

# Adoption Report — symaira-corekit ← obra/superpowers — 2026-07-30

## Sources

| Field | Value |
|---|---|
| SOURCE | `obra/superpowers` (https://github.com/obra/superpowers) |
| Ref analyzed | `44c9b2d` (main) |
| Language / License | Shell + JavaScript (89 md, 38 sh, 13 json, 0 Go) / MIT |
| Health | 263,650 stars, last push 2026-07-28, not archived, latest release v6.2.0 (2026-07-24), ~4 MB |
| Scope | all facets, full clone |
| TARGET | `danieljustus/symaira-corekit` @ `ec8368b` |

## Verdict

**Nothing from `obra/superpowers` is worth adopting into `symaira-corekit`.** The two repositories
have no overlapping problem: corekit is a versioned Go library of reusable packages (config, logging,
MCP server, SQLite, vector quantization, update-check) consumed by other Go binaries; superpowers is
a markdown-and-shell content bundle distributed to agent harnesses, with no library surface, no Go,
no public API, and no CI. Every candidate below died at gate 1 (not transferable) or gate 2 (already
covered) — several because corekit is measurably ahead: it runs an OS matrix CI with race detector
and an `apidiff` API-compatibility check (`.github/workflows/ci.yml`, commit `c1388e4`), while the
SOURCE ships **no CI workflows at all**.

The one facet where a cross-language reading was plausible — declarative version management — is
already solved here by `versionkit` plus the `06-gh-prerelease` gate, and solved *better*: their
`scripts/bump-version.sh` exists to reconcile seven hand-written JSON manifests, a problem a single
Go module does not have.

**Rule 3 notice — SOURCE content is instructions aimed at agents.** Nearly every markdown file in
superpowers addresses an AI agent directly, e.g. `skills/writing-skills/SKILL.md:22`:
> "**REQUIRED BACKGROUND:** You MUST understand superpowers:test-driven-development before using this skill."

Nothing from those files was acted on; it is quoted here as data only.

## What we already do as well or better

- Version/schema contract for consumers → `versionkit/versionkit.go:18-50` defines a typed `version --json` handshake with an explicit `schema_version`. Superpowers has no machine-readable contract, only version strings duplicated across seven manifests.
- Version consistency enforcement → their `scripts/bump-version.sh --audit` greps the repo for stale version strings; here the `06-gh-prerelease` gate does the same and archives the report (`.github/prerelease/*.md`, 13 archived runs).
- CI depth → matrix over ubuntu/macos, `go mod verify`, `-race`, and an `apidiff` compatibility gate (`.github/workflows/ci.yml`, `c1388e4`). SOURCE `.github/` contains only issue templates and `FUNDING.yml`.
- Design-decision record → `docs/adr/0001-authkit-session-and-biometric-broker.md` and `docs/cross-language-conventions.md` cover the same role as their `docs/plans/` + `docs/superpowers/specs/` dated design docs.
- Coverage discipline → `.github/coverage/*.md` gate reports and per-package `_test.go` across all 14 packages. SOURCE has shell/node integration tests for its own scripts only, and its LLM eval harness is not even in this repository (`.gitignore:13`).

## Findings

_None. No candidate survived the four gates._

## Considered and rejected

- **`.version-bump.json` + `scripts/bump-version.sh` declarative version manifest with drift audit** — gate 2 (New): `versionkit` plus the `06-gh-prerelease` gate already own this, and a single Go module has exactly one version source. Their tool is a workaround for seven hand-maintained manifests.
- **`.pre-commit-config.yaml` local hooks (ruff/ty on the eval subtree)** — gate 3 (Better): equivalent checks already run in CI (`gofmt`, `go vet`, `apidiff`) and in `make lint`. Moving them pre-commit trades CI reliability for local speed; no delta against a recorded pain point.
- **`docs/plans/` + `docs/superpowers/specs/` dated design-doc convention** — gate 2 (New): `docs/adr/` serves the same purpose with a stronger format.
- **`.github/ISSUE_TEMPLATE/` set (bug, feature, platform support)** — gate 4 (Worth it): rule 9 — a solo library repo with one open issue (#44). Template overhead without a queue.
- **`tests/*/run-*.sh` shell integration-test harness with hand-rolled `assert_equals` helpers** — gate 1 (Transferable): Go's `testing` package plus table-driven tests already covers this ground with better tooling; adopting bash assertions would be a regression.
- **`scripts/lint-shell.sh` + `tests/shell-lint/`** — gate 1 (Transferable): corekit contains no shell beyond the Makefile.
- **Multi-host plugin manifests (`.claude-plugin/`, `.codex-plugin/`, `.cursor-plugin/`, `.kimi-plugin/`, `gemini-extension.json`)** — gate 1 (Transferable): corekit is not distributed to agent harnesses. This facet is relevant to `symaira-skills`, and is covered in that repo's report.
- **`mcpserver` comparison against their MCP/tool wiring (`.opencode/plugins/superpowers.js`, `.pi/extensions/superpowers.ts`)** — gate 3 (Better): their extensions register a handful of untyped tools per host; `mcpserver/typed.go` derives `InputSchema` from Go types (`RegisterTyped`, `#40`). No delta in our direction.
- **`RELEASE-NOTES.md` as a curated top-level changelog** — gate 4 (Worth it): GitHub releases produced by the `07-gh-release` flow already carry the notes; a second hand-maintained file is a drift source.

## Open questions

- None arising from this SOURCE. The comparison bottomed out at "different problem domain" rather than at missing evidence.
- Unrelated to the SOURCE, noted only because it surfaced while building the baseline: open issue #44 (`mcpserver` structured tool results violate the MCP `TextContent` schema) is the same contract-mismatch class that `symaira-skills` issue #89 hit. If a third instance appears, a shared schema-conformance test helper in corekit may be worth its own review — but that is an internal observation, not an adoption of anything upstream.

**First step:** none — close this out and spend the budget on the `symaira-skills` report, where the same SOURCE produced three actionable findings.
