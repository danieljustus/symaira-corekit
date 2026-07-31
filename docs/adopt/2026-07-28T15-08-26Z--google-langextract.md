<!-- review: timestamp=2026-07-28T15:08:26Z  repo=danieljustus/symaira-corekit  head=213217c66b6cfb6666179018dd7cb59a9685d1e9 -->
<!-- adopt: source=google/langextract  source_ref=b5fe0baf807ac35ec95b968a71e4d03f198a1b60  source_url=https://github.com/google/langextract  depth=clone  license=Apache-2.0 -->

# Adoption Report — symaira-corekit ← google/langextract — 2026-07-28

## Sources

| Field | Value |
|---|---|
| SOURCE | `google/langextract` (https://github.com/google/langextract) |
| Ref analyzed | `b5fe0baf807ac35ec95b968a71e4d03f198a1b60` (main) |
| Language / License | Python / Apache-2.0 |
| Health | 37,909 stars, last push 2026-07-25, active (v1.6.0 released 2026-07-02, monthly release cadence), full CI |
| Scope | all facets, full clone |
| TARGET | `danieljustus/symaira-corekit` @ `213217c66b6cfb6666179018dd7cb59a9685d1e9` |

## Verdict

LangExtract is Google's Python library for LLM-based structured extraction with source
grounding — the same problem `evidencekit` (corekit's grounded-extraction contract package,
built 2026-07-08 for `symaira-memory` issue #318) exists to solve, and #318's own issue body
already cites LangExtract's "reject ungrounded facts" pattern as the design inspiration. Most
of LangExtract is out of scope for corekit by design: it is a full LLM extraction pipeline
(prompting, schema-constrained generation, chunking, multi-pass extraction, provider plugins,
HTML visualization), and `evidencekit`'s own doc comment deliberately excludes "cloud, LLM, or
tool-specific dependencies" — that logic belongs in a consumer (`symaira-memory`), not corekit.
What *is* in scope, and the highest-value takeaway: LangExtract's alignment resolver
(`langextract/resolver.py`) has a token-based fuzzy-matching fallback that `evidencekit.Align`
completely lacks — today, anything that isn't a byte-identical or whitespace-collapsed
substring match is unconditionally discarded as ungrounded, which will silently gut recall the
moment a consumer moves from regex-extracted (always-verbatim) facts to LLM-extracted
(sometimes-paraphrased) facts.

## What we already do as well or better

- LangExtract's core grounding contract (locate evidence text in source, mark unmatched
  extractions so grounded-only consumers can reject them) → we already have this:
  `evidencekit.Align`/`evidencekit.Validate` (`evidencekit/evidencekit.go:119-144`) implement
  exact-match and whitespace-normalized-match grounding with the same "unmatched → caller must
  reject" contract as LangExtract's `char_interval = None` filtering convention.
- LangExtract's JSONL extraction sidecar format → we already have this:
  `evidencekit.EncodeJSONL`/`DecodeJSONL` (`evidencekit/evidencekit.go:148-179`).
- LangExtract's Apache-2.0 licensing and "define the contract once, no cloud/LLM coupling"
  boundary → corekit already enforces a stricter version of this via the Standalone-First
  Contract in `README.md:12-19`, which is *more* disciplined than LangExtract's own layering
  (LangExtract bundles the contract, the LLM calls, and the prompting logic in one package;
  corekit deliberately keeps `evidencekit` free of all three).

## Findings

- [ ] **[Architecture] Add a fuzzy-alignment fallback to `evidencekit.Align`**
  - **Status quo:** `evidencekit.Align` (`evidencekit/evidencekit.go:119-127`) tries only
    `AlignExact` then `AlignNormalized` (whitespace-collapse); anything else becomes
    `AlignmentUnmatched` and is rejected by `Validate` (`evidencekit/evidencekit.go:133-144`).
    This is invisible today because the only current producer,
    `symaira-memory/internal/extractor/pattern.go:127-135` (`groundEvidence`), always grounds a
    verbatim sentence copied straight out of the source text, so exact match never fails. It
    stops being invisible the moment a consumer grounds LLM-generated extraction text, which
    routinely paraphrases, reorders, or drops filler words relative to the source — exactly the
    gap `symaira-memory` issue #318 (which cites LangExtract by name as the reason evidence
    spans matter) will hit if it ever adds LLM-based extraction, and #318 explicitly scoped
    "mandatory LLM extraction" out for now rather than solve this. Upstream, LangExtract hits
    the identical problem and solves it in `langextract/resolver.py:591-715`
    (`_fuzzy_align_extraction`, token-level `difflib.SequenceMatcher` sliding-window match with
    a token-overlap pre-check) and `langextract/resolver.py:717-787`
    (`_lcs_fuzzy_align_extraction`, an LCS-based variant with coverage/density thresholds) —
    both only run on extractions that already failed exact matching, and both are pure
    text-processing with no LLM or network dependency.
  - **Proposed solution:** Pattern adoption only, no code copied (rule 5) — LangExtract's
    algorithms are Python/`difflib`-specific and would need a from-scratch Go implementation
    (e.g. token diff via LCS or Go's `github.com/agnivade/levenshtein`-style edit distance).
    Add an `AlignFuzzy` step to `evidencekit.Align` behind a new `AlignmentFuzzy` status (a
    fourth `AlignmentStatus`, additive — does not break the existing three-value cross-repo JSON
    contract) that runs only after exact and normalized matching fail, using a token-overlap
    threshold (LangExtract's is a tunable ratio, default around 0.75-0.79 based on
    `_FUZZY_ALIGNMENT_MIN_THRESHOLD`) below which the extraction still falls through to
    `AlignmentUnmatched`. Keep `Validate` strict by default and let a grounded-only caller opt
    out of accepting `AlignmentFuzzy` if it wants exact-only guarantees. Pair with a planted-span
    test corpus (LangExtract's `tests/fuzzy_alignment_cases_test.py` generates random source
    text with known-truth spans and asserts exact recovered offsets) — `evidencekit_test.go`
    today only has hand-written fixed cases, and the rune/byte offset math in
    `normalizeWithMap`/`runeByteOffsets` is exactly the kind of code where a property-style
    regression net pays for itself.
  - **Effort/Impact:** Medium effort (self-contained algorithm + tests, no new runtime
    dependency required, stays inside `evidencekit`'s no-LLM/no-cloud contract) / medium-high
    impact — this is a latent gap, not a firing one, so it does not block anything today, but it
    is the one piece of grounded-extraction infrastructure LangExtract has that corekit does
    not, and it is cheaper to build before a consumer depends on the current always-exact
    assumption than to retrofit after.

- [ ] **[Architecture] Give `evidencekit.Validate` sentinel errors**
  - **Status quo:** `evidencekit.Validate` (`evidencekit/evidencekit.go:133-144`) returns three
    distinct failure modes — unmatched alignment, empty evidence text, invalid span — all as ad
    hoc `errors.New`/`fmt.Errorf` values with no sentinel, so a caller cannot
    `errors.Is()`-branch on which one occurred. This is the one package in corekit that does
    this: every sibling package with fallible, callable-distinguishable errors already exports
    sentinels — `updatecheck/extract/extract.go:25,29` (`ErrBinaryNotFound`,
    `ErrPathTraversal`), `ollamakit/ollamakit.go:41-50` (`ErrUnreachable`, `ErrModelNotFound`,
    `ErrStream`, `ErrResponse`), `fsutil/pathutil.go:12` (`ErrInvalidPath`),
    `updatecheck/installmethod/detect.go:45` (`ErrEmptyBinaryPath`),
    `vectorkit/turboquant/codec.go:91-95` (four sentinels). This matters concretely for
    `symaira-memory` issue #318's own acceptance criteria ("PII/secrets are not leaked through
    evidence text when redaction/sensitivity policy applies") — a caller enforcing grounded-only
    ingestion needs to tell "this extraction is simply ungrounded, skip it" apart from "this
    extraction is malformed, that's a bug" and currently can only do that by parsing error
    strings. Upstream, LangExtract solves the general version of this with a typed exception
    hierarchy rooted at `LangExtractError` (`langextract/core/exceptions.py:38-45`), with
    `ResolverParsingError(exceptions.LangExtractError)` (`langextract/resolver.py:208`) as the
    alignment-specific case — the same "let callers catch by category" motivation, Go's idiom
    for it is sentinel errors rather than exception subclassing.
  - **Proposed solution:** Pattern adoption, Go-idiomatic (not a class hierarchy port). Add
    `var ErrUnmatched`, `ErrEmptyEvidence`, `ErrInvalidSpan` sentinels to `evidencekit.go`
    following the exact convention already used four times elsewhere in this repo, wrap them
    with `%w` in the existing `Validate` messages, and change the three `errors.New`/`fmt.Errorf`
    call sites to reference the sentinels so `errors.Is(err, evidencekit.ErrUnmatched)` works.
  - **Effort/Impact:** Low effort (mechanical, ~10 lines, no behavior change to error message
    text) / low-medium impact — small correctness/ergonomics fix, worth bundling with the fuzzy-
    alignment finding above since both touch the same file and the fuzzy-alignment work will
    want a clean way to distinguish "unmatched" from "fuzzy-rejected below threshold" for callers
    anyway.

## Considered and rejected

- **LangExtract's full extraction pipeline (chunking, multi-pass extraction, parallel workers,
  `langextract/chunking.py`, `langextract/extraction.py`, `langextract/factory.py`)** — gate 1
  (Transferable): this is LLM-inference-pipeline logic. `evidencekit`'s own doc comment
  (`evidencekit/evidencekit.go:11-13`) states it "has no cloud, LLM, or tool-specific
  dependencies," and corekit's README Standalone-First Contract scopes corekit to "domain-free
  infrastructure," not extraction orchestration. `symaira-memory` #318 explicitly scoped
  "mandatory LLM extraction on import" out. If `symaira-memory` later adds an LLM-based
  extractor, this belongs in a fresh `gh-adopt` pass against that repo, not corekit.
- **Interactive HTML visualization of extractions (`langextract/visualization.py`)** — gate 1
  (Transferable): application/presentation layer, not a corekit concern; corekit ships no
  extraction consumers or UI.
- **Schema-constrained generation / few-shot prompt validation
  (`langextract/schema.py`, `langextract/prompt_validation.py`)** — gate 1 (Transferable):
  requires an LLM call in the loop (Gemini/OpenAI controlled generation); corekit's `ollamakit`
  is a plain HTTP client with no prompting/schema layer, and adding one would be new
  domain-specific surface with no recorded consumer request.
- **Provider plugin registry (`langextract/providers/`, `langextract/registry.py`,
  entry-points-based custom model providers)** — gate 3 (Better): no recorded pain point;
  corekit has no multi-provider extensibility need today (`ollamakit` targets Ollama only,
  by design), and the registry only pays for itself once there are several providers to swap.
- **Shipping a `SKILL.md` agent-usage skill alongside the library
  (`skills/langextract-usage/`)** — gate 4 (Worth it): corekit is consumed by sibling Go repos
  writing normal Go imports, not by agents composing ad hoc LLM-extraction calls against a wide
  API surface; usage is already documented in `README.md`'s package table plus
  `docs/cross-language-conventions.md`. Revisit if corekit ever grows a large, agent-facing
  surface that isn't just "import the package."
- **Fork-PR-safe CI (secret-gated live API testing on `pull_request_target`, PR-size labeling,
  `check-linked-issue`, `auto-update-pr`)** — gate 4 / scale fit (rule 9): this defends against
  malicious external-contributor PRs at a 37.9k-star, many-contributor scale. `symaira-corekit`
  is solo-maintained; this tooling is pure overhead here.
- **Richer `AlignmentStatus` granularity (LangExtract's `MATCH_EXACT`/`MATCH_GREATER`/
  `MATCH_LESSER`/`MATCH_FUZZY`, distinguishing exact token-boundary matches from matches that
  overshoot/undershoot token boundaries)** — gate 4 (Worth it) as a *separate* finding: folded
  into the fuzzy-alignment finding above instead of listed on its own, since it only makes sense
  once fuzzy matching exists at all.

## Open questions

- LangExtract tunes its fuzzy-alignment acceptance threshold empirically
  (`_FUZZY_ALIGNMENT_MIN_THRESHOLD`, `_FUZZY_ALIGNMENT_MIN_DENSITY` in `resolver.py`) against a
  large internal eval set spanning clinical notes, literature, and structured forms. Corekit has
  no equivalent extraction corpus yet, so the right default threshold for `AlignFuzzy` can't be
  derived from evidence today — it would need to be chosen conservatively and revisited once
  `symaira-memory` has real LLM-extracted evidence to validate against.
- Whether `symaira-memory` actually plans an LLM-based extractor (which would make the fuzzy-
  alignment finding load-bearing rather than preventative) isn't settled in any open issue;
  #318's "Out of Scope" section only says "mandatory" LLM extraction is deferred, not ruled out.

**Single best first step:** implement the sentinel-errors finding first (it's a 10-line,
zero-risk change to the same file), then use the newly errors.Is-able `Validate` as the seam for
adding `AlignFuzzy`/`AlignmentFuzzy` right after it.
