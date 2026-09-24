# Bounded-allocation DOM truncation

## Measurement contract (recorded before the implementation change)

Baseline: `05d3702f468c8a2817483385373ca229e157ce22` plus the identical benchmark
and reference test files used for the candidate. CoreKit is a library: there
is no application binary to time. This experiment exercises its actual public
`Truncate` and `Render` APIs, not an installed consumer or a remote website.

Hypothesis: `takeRunesFromEnd` allocates a rune slice for the entire source
although only the final half-budget is needed. `Truncate` also recounts the
whole source. Bound the tail conversion to the retained suffix and reuse the
initial rune count; preserve byte-for-byte output, including malformed UTF-8.
No cache, parallelism, new dependency, API or wire-format change.

Workloads are generated local text, not captured production data. The fixed
paragraph contains ASCII, German, CJK and emoji. Use 10 (small/untruncated),
1,000 (typical truncated document), and 16,000 (large document) paragraphs,
with the existing 15,000-rune default budget. Measure standalone truncation,
full HTML-to-Markdown rendering, and full raw-HTML rendering; retain the
existing `BenchmarkRenderParseOnce` as a rich-page neighboring-flow control.
The input generators and expected-output checks stay identical for both builds.

Primary metric: allocated bytes per complete public API call, smaller is
better. Acceptance: remove at least 3 MiB per large truncation, retain the
saving in full `Render`, and do not increase small-input allocations. This
budget targets the unnecessary four-byte-per-rune whole-document copy, not
an arbitrary speed percentage. Secondary metric: ns/op; retain only if no
repeatable latency regression exceeds both 5% and the observed run-to-run
spread for the typical/small complete render. Claim latency improvements
only outside measured noise. No p95 estimate from benchmark run averages.

Go 1.26.6, CGO disabled, same host, normal optimized test binaries, one CPU
(`GOMAXPROCS=1`, `-test.cpu=1`). Each independent process runs 100 ms per
benchmark after calibration. One complete warm-up process per variant is
saved separately, followed by ten processes per variant in alternating
AB/BA order. Retain every raw observation (no outlier removal), report medians
and full min–max ranges. These are warmed in-process API measurements; fresh
processes do not make them cold-start measurements. There is no meaningful
library startup contract here, and no disk/network/cache-purge workload.

Profiling is a separate diagnostic run, never part of the before/after
comparison. Record CPU/OS/toolchain, power source/mode, thermal status and
background load. Do not run owned builds or other benchmarks concurrently.
Background desktop activity is a limitation, not a reason to silently drop
runs. Allocation counts provide the less noisy structural cross-check.

## Results

Measured on September 22, 2026, Apple M4 Pro, 24 GiB RAM, macOS 27.0
(26A428), Go 1.26.6 darwin/arm64. Battery power, `powermode 0`; no recorded
thermal/performance warning before or after the run. Desktop background
activity (including Spotlight and WindowServer) was present; no owned builds,
profiling, fuzzing or other benchmarks ran during the paired comparison.

Text input sizes are 670 / 67,000 / 1,072,000 runes, respectively
760 / 76,000 / 1,216,000 UTF-8 bytes, plus a fixed HTML wrapper for Render.
The full Render timing includes parsing, metadata, rendering and truncation,
and the new benchmarks compare each output against the old rune-slice
semantics. It excludes network and browser work. Fixtures are deliberately
text-heavy; DOMs with many small elements can be dominated by parsing instead.

All ten measured process samples per variant are retained in
[`domkit-truncate-raw.txt`](domkit-truncate-raw.txt), together with the separate
warm-ups, preliminary baseline, exact flags, binary SHA-256 values and source
hashes. The candidate is the baseline plus this PR's `domkit/truncate.go`
change; the benchmark/reference sources are identical in both binaries.

| Workload | Before median [min–max], µs | After median [min–max], µs | Median reduction | Bytes/op before → after |
|---|---:|---:|---:|---:|
| Rich-page Render control | 11.438 [10.992–29.183] | 11.343 [10.910–14.682] | 0.83% | 13,496 → 13,496 |
| Small Markdown Render | 8.300 [8.212–11.748] | 8.315 [8.269–10.070] | -0.17% | 9,592 → 9,592 |
| Small raw Render | 4.564 [4.487–15.124] | 4.609 [4.473–5.028] | -1.01% | 6,752 → 6,752 |
| Typical Markdown Render | 853.730 [835.190–1251.871] | 739.842 [726.992–1213.910] | 13.34% | 1,140,193 → 902,624 |
| Typical raw Render | 474.430 [469.615–696.621] | 363.491 [356.356–471.208] | 23.38% | 674,504 → 436,936 |
| Large Markdown Render | 11212.713 [10982.125–13191.162] | 9762.108 [9557.795–12776.844] | 12.94% | 17,630,734 → 13,370,881.5 |
| Large raw Render | 6072.275 [5967.524–6878.067] | 4272.816 [4220.647–5115.258] | 29.63% | 9,767,664 → 5,507,824 |
| Small Truncate | 0.280 [0.271–0.429] | 0.276 [0.272–0.293] | 1.39% | 0 → 0 |
| Typical Truncate | 218.774 [213.925–971.693] | 117.621 [115.111–150.534] | 46.24% | 332,648 → 95,080 |
| Large Truncate | 2371.269 [2340.082–6982.969] | 537.710 [525.451–588.697] | 77.32% | 4,354,959 → 95,112 |

**Decision:** keep the change. Large truncation saves 4,259,847 allocated
bytes/call (4.063 MiB, 97.82%); the complete raw and Markdown Render paths
also save approximately 4.26 MB/call. Small/control allocations are unchanged.
Allocation *counts* are unchanged for every workload: this shrinks one
allocation rather than eliminating it. Bytes/op are allocation volume, not
peak RSS or retained heap.

The large raw Render and both truncated Truncate latency ranges do not
overlap between variants. Markdown and typical raw Render medians improve,
but their full ranges overlap: those percentages are descriptive, not a
separate claim of noise-free latency improvement. Small/control timing
differences are within noise. No observations were dropped, including the
large baseline outliers. No tail-latency percentile is inferred.

The separate baseline allocation profile attributes 98.32% of sampled space
to `takeRunesFromEnd`; the CPU profile also shows full-string rune conversion
and repeated counting. This is diagnostic attribution, not the speedup.
The retained suffix still passes through `[]rune` so each invalid UTF-8 byte
is replaced exactly as before; returning a raw substring would change that
contract. A full O(input) rune-count scan remains necessary for the marker.
No claim is made about installed consumer speed, network time or startup.

## Reproduce

Run from the candidate repository root. Python uses only the standard
library. Build both binaries before running the serial comparison; keep the
created directory for evidence. Do not run parallel builds or benchmarks.

```sh
export GOTOOLCHAIN=go1.26.6
OUT=$(mktemp -d "${TMPDIR%/}/domkit-perf.XXXXXX")
BASE="$OUT/base"
git worktree add --detach "$BASE" 05d3702f468c8a2817483385373ca229e157ce22
cp domkit/truncate_benchmark_test.go domkit/truncate_parity_test.go "$BASE/domkit/"
(cd "$BASE" && CGO_ENABLED=0 go test -c -o "$OUT/baseline.test" ./domkit)
CGO_ENABLED=0 go test -c -o "$OUT/candidate.test" ./domkit
python3 scripts/bench-domkit.py "$OUT/baseline.test" "$OUT/candidate.test" "$OUT/paired"
```

`paired/summary.json` contains medians and full ranges. The script requires
all ten workload rows per process and ten measured samples per variant,
keeps warm-up logs separate and records execution order and binary hashes.
The latency reduction formula is `(before - after) / before * 100`.

Separate diagnostic profiling command (not used for the comparison):

```sh
GOMAXPROCS=1 "$OUT/baseline.test" -test.run='^$' \
  -test.bench='BenchmarkTruncate/paragraphs=16000$' -test.benchtime=2s \
  -test.cpu=1 -test.cpuprofile="$OUT/baseline.cpu" -test.memprofile="$OUT/baseline.mem"
go tool pprof -top -alloc_space "$OUT/baseline.test" "$OUT/baseline.mem"
go tool pprof -top -nodecount=12 "$OUT/baseline.test" "$OUT/baseline.cpu"
```

## Correctness and local gates

All commands passed with Go 1.26.6. The unchanged baseline build and race
suite passed before editing. The differential fuzz target covers Unicode,
combining sequences, emoji, malformed UTF-8, NUL, odd/single/disabled budgets
and arbitrary generated strings; its reference is independent of the new
reverse-scan implementation. The 15-second run completed 778,144 executions.

```sh
export GOTOOLCHAIN=go1.26.6
export PATH="$(go env GOROOT)/bin:$PATH"
CGO_ENABLED=0 go test -count=1 ./domkit
CGO_ENABLED=0 go test ./domkit -run='^$' -fuzz=FuzzTruncateParity -fuzztime=15s -parallel=1
make build
make test
make lint
CGO_ENABLED=0 go test -count=1 -timeout=5m ./...
go mod verify
python3 scripts/rust-port/generate.py --check-source
python3 scripts/rust-port/generate.py --check
```

No Rust code, frozen oracle inputs, dependencies or product boundaries are
changed. Remote CI status belongs to the exact PR head, not this static
measurement report. No timing threshold is added to CI.
