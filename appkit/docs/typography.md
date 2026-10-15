# Live typography roles

`SymairaTypography` and `SymairaTextRole.font` now return `SymairaFontRole`,
not a pre-resolved SwiftUI `Font`. `SymairaFont.font(size:weight:relativeTo:)`
also returns a role. This is an intentional source-breaking API change.

```swift
Text("Status").font(SymairaTypography.body)
Text("Status").symairaText(.body)
let role: SymairaFontRole = SymairaTypography.body
```

The `.font(role)` overload keeps existing ordinary View call sites intact.
It returns `some View`, not `Text`. Change stored `Font` values to
`SymairaFontRole`; change functions explicitly returning styled `Text` to
`some View`. Perform Text-only composition before applying the role to the
resulting view. Attributed-string font attributes cannot hold a role: apply
it at the rendered View boundary instead. Do not turn roles back into cached
point-sized fonts, since that reintroduces the live-scaling bug.

On iOS the modifier uses public `@ScaledMetric` in the receiving view's
Dynamic Type environment. Only then does it construct the Core Text font
with the approved weight and `opsz` 18. The absent-font system fallback uses
the same live point size. Monospaced roles retain semantic system fonts.
macOS retains the original fixed sizes and font construction. Font resources
are unchanged; no private font provider or modified asset is used.

## Native regression

Run the ordinary suite and strict formatter through `make test` and `make lint`.
The separate native host below checks an already-mounted iOS hierarchy; it
is not part of any shipped library. It uses only Python's standard library
and Xcode, without XcodeGen or third-party test dependencies.

With a booted iOS 26+ simulator, run from the repository:

```sh
python3 -B scripts/test_live_typography.py \
  --device SIMULATOR-UDID \
  --build-dir /absolute/external/build-directory \
  --evidence-dir /absolute/fresh/evidence-directory
```

For hosts requiring an external-build guard, add
`--build-launcher /absolute/path/to/dev-external` and run that guard's
`--status` first. Keep generated build/evidence paths outside this repository.
The runtime must be iOS 26+ for public `Font.resolve` axis inspection; the
product and host still compile with deployment target iOS 17. The runner
verifies both the bundle's minimum OS/device families and Mach-O minimum OS.

The runner builds the real local package, records a source manifest, mounts
15 shared roles plus four modifier/tabular samples, and changes `.large` to
`.accessibility5` and back in the same process. It checks measured layout,
restoration, resolved family/weights/effective optical size and equal-width
digits. Core Text omits default axes, so effective axes combine reported
values with the font's own declared defaults. It repeats the run in a copied
app with the original TTF omitted, exercising the real missing-resource
branch without changing production resources. Fresh PID-bound results,
command exit codes, images and app/resource hashes are retained.

These checks do not claim physical-device, VoiceOver, keyboard-focus or
consumer-screen acceptance. Those are separate gates.
