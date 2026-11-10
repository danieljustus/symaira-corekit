# Liquid Topography verification

## Reproduce the checks

From the repository root:

```sh
make test
node design/liquid-topography/web/symaira-topo.test.mjs
python3 design/liquid-topography/build.py
```

The web contract test uses a stub WebGL context to check scheduling and mask
uniforms. It is not a GPU rendering test. The native XCTest suite also renders
an actual Metal-backed view and checks pixels inside/outside a protection zone.

## Passive demo CPU experiment

Build the demo with `design/liquid-topography/apple/Demo/build.sh` and an explicit
output directory. Then run:

```sh
python3 design/liquid-topography/apple/Demo/benchmark.py \
  '/path/to/Liquid Topography Demo.app' /path/to/results.json --repeats 3
```

This test launches a fresh demo process for each sample. It measures process CPU
time (one core = 100%) over six seconds after a separate three-second warm-up.
Modes are off, static, idle, modeled pointer/press interaction, and hidden.
The hidden mode verifies the actual window is hidden before sampling. The
interaction mode supplies deterministic model inputs; it does not prove mouse
event delivery. No agents, hardware-control services or credentials are used.

### Exploratory result

This is the lifecycle-fix experiment at `870e236`, before the later calmer
motion and narrower protection-transition tuning. It is not a new energy
measurement of that visual revision.

macOS 27.0.1, Xcode 27.0, AC power, unchanged 20 fps and animation parameters.
Three fresh process launches per mode; baseline first, candidate second. This
small, non-interleaved experiment is sufficient to identify the missing pause,
but not to claim improved foreground performance or battery life.

| Mode | Baseline median CPU % | Candidate median CPU % |
|---|---:|---:|
| No topography | 0.17 | 0.17 |
| Static topography | 0.00 | 0.00 |
| Visible idle | 6.99 | 7.32 |
| Modeled interaction | 6.65 | 7.82 |
| Hidden window | 6.49 | 0.17 |

Hidden-window ranges: baseline 6.16–10.82%; candidate 0.00–0.17%.
Zero means below the CPU-time sampling resolution, not literally zero energy.
The baseline is commit `7f1c07b` plus the same benchmark harness and static-mode
switch as the candidate. An earlier attempt did not actually hide the window;
its hidden-mode measurements were rejected, not mixed into this table.

Foreground savings are **not demonstrated**. More repeated interleaved trials,
GPU measurements, real-device battery testing and thermal checks are still
required before a production energy budget can be claimed.

## Readability and lifecycle contract

- Every registered visible element remains protected. Above the 20-region
  budget, a conservative union masks all of them; decorative detail may vanish.
- Native coordinates are converted from the content space to the shader space.
- Hidden native windows and background scenes pause the timeline.
- Web hidden tabs cancel scheduled frames; repeated resume notifications never
  create multiple loops.
- Web reduced motion uses event-driven redraws rather than recurring timers.
  Ancestor theme changes and viewport resize still update the static image.

Current browser verification covers four state buttons, pointer down/drag/up,
light/dark, mobile sizing and reduced-motion quiescence using Chromium with
SwiftShader. That verifies actual shader compilation/rendering and input
handlers, not hardware-GPU efficiency, VoiceOver or a physical iPhone.
