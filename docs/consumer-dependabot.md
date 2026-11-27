# Consumer Dependabot setup

A CoreKit release reaches every consumer through Dependabot. This page is the
setup each consumer repository carries; [ADR 0002](adr/0002-rust-distribution-git-pins.md)
(amendment 2026-11-16) explains why the pins look the way they do.

## What lands a release

1. **Pins Dependabot can move.** Cargo: `tag = "vX.Y.Z"`, never `rev` or
   `branch`. Swift: `exact: "X.Y.Z"` in `Package.swift`, `exactVersion` in an
   XcodeGen `project.yml`. Dependabot reads Swift pins only from a tracked
   `Package.swift` or a tracked `*.xcodeproj`; a `project.yml` whose Xcode
   project is git-ignored is invisible to it.
2. **`dependabot.yml`** groups the CoreKit pins per ecosystem, checks daily and
   exempts them from the cooldown (template below).
3. **`.github/workflows/corekit-dependabot.yml`** calls the composite action
   [`.github/actions/dependabot-corekit`](../.github/actions/dependabot-corekit/action.yml).
   For a pull request that bumps only CoreKit it copies the new version into
   the files Dependabot never edits (`project.yml`, a
   `[workspace.dependencies]` tag in `Cargo.toml`, a root `Package.swift` and
   its `Package.resolved` behind a local `.package(path:)` package that pins
   CoreKit too), pushes that commit with a
   write deploy key of the repository and enables auto-merge. A push made with
   `GITHUB_TOKEN` starts no workflow; the deploy-key push makes the pull
   request's own CI run on the synced commit. The repository's required status
   checks decide the merge; any other dependency update is left for review.
4. **Deploy key** `corekit-dependabot-sync` (write access, this repository
   only) whose private half is the Dependabot secret
   `COREKIT_SYNC_DEPLOY_KEY`. Workflows started by Dependabot read only
   Dependabot secrets.

`corekit_pins.py` (next to the action) is also the consumer's local check:
`python3 -I corekit_pins.py` fails on drift or a non-tag Cargo pin, `--fix`
repairs the drift.

## Private repositories

GitHub Free offers no required status checks or auto-merge for private
repositories, so step 3 cannot gate a merge there. Private consumers keep
steps 1 and 2; a scheduled job on the maintainer's Mac checks out each open
CoreKit pull request, runs `corekit_pins.py --fix`, builds and tests the app
and merges only on success. It also bumps a `project.yml` whose Xcode project
is git-ignored, which Dependabot cannot see.

## Templates

`dependabot.yml` entries (keep the directories that hold a CoreKit pin):

```yaml
  - package-ecosystem: "cargo"
    directory: "/"
    schedule:
      interval: "daily"
    cooldown:
      exclude: ["symaira-core-*"]
    groups:
      symaira-corekit:
        patterns: ["symaira-core-*"]
      # Any broader cargo group must exclude the CoreKit crates, or it wins
      # and Dependabot drops their Git tag bump.

  - package-ecosystem: "swift"
    directories: ["/", "/app"]
    schedule:
      interval: "daily"
    cooldown:
      exclude: ["*symaira-corekit*"]
    groups:
      symaira-corekit:
        patterns: ["*symaira-corekit*"]

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      symaira-corekit:
        patterns: ["danieljustus/symaira-corekit*"]
```

`.github/workflows/corekit-dependabot.yml` (public repositories):

```yaml
name: CoreKit Dependabot
on:
  pull_request:
    branches: [main]
permissions:
  contents: write
  pull-requests: write
  actions: write
jobs:
  corekit:
    if: github.event.pull_request.user.login == 'dependabot[bot]'
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: danieljustus/symaira-corekit/.github/actions/dependabot-corekit@<full-sha> # vX.Y.Z
        with:
          ssh-key: ${{ secrets.COREKIT_SYNC_DEPLOY_KEY }}
```

Deploy key and secret, from a maintainer shell (the private key never leaves
the pipe and the temporary directory):

```sh
repo=danieljustus/<consumer>; d="$(mktemp -d)"
ssh-keygen -q -t ed25519 -N '' -C corekit-dependabot-sync -f "$d/k"
gh api "repos/$repo/keys" -f title=corekit-dependabot-sync -f key="$(cat "$d/k.pub")" -F read_only=false
gh secret set COREKIT_SYNC_DEPLOY_KEY --app dependabot -R "$repo" <"$d/k"
rm -rf "$d"
```

The repository needs "Allow auto-merge" enabled and a ruleset or branch
protection with required status checks; without one, `gh pr merge --auto`
merges at once.
