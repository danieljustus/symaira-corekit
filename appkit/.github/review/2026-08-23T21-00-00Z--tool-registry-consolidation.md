# Review — SymairaToolRegistry lists tools that no longer exist

**Date:** 2026-08-23
**Scope:** `Sources/SymairaToolKit/SymairaTool.swift`
**Type:** contract violation (code, not docs)

## Finding

`SymairaToolRegistry` registers 18 tool ids:

```
symbrain symdesk symeraseme symfetch symfritz symguard symingest symmeet
symmemory symoperate symprint symrelate symscope symseek symskills symtune
symvault symvibe
```

Twelve of them no longer exist as binaries after the 2026-08 repo
consolidation (27 → 13 repositories):

| Registered id | Reality |
|---|---|
| `symfetch` | absorbed into `symbrowse`; repo archived, formula deprecated |
| `symguard`, `symmemory`, `symskills` | absorbed into `symbrain` |
| `symingest`, `symmeet`, `symprint`, `symrelate`, `symseek` | absorbed into `symdesk` |
| `symoperate`, `symscope`, `symtune` | absorbed into `symcockpit` |

`symroom` is the one absorbed tool whose binary still ships (with the symdesk
release) and it is absent from the registry.

## Why it matters

`ToolDetector` resolves these ids over `PATH`. A GUI client built on appkit
will therefore keep probing for binaries that Homebrew now refuses to install
— surfacing "not installed" for capabilities the user does have, because they
are inside `symbrain`, `symdesk`, `symbrowse` or `symcockpit`.

The consolidation decision anticipated this: `docs/repo-konsolidierung.md` §6
lists "`SymairaTool`-Registry in appkit anpassen" as required per merge. It
was not carried out for any of the eight steps.

## Suggested work

1. Reduce the registry to the ids that resolve to a real binary: `symbrain`,
   `symbrowse`, `symcockpit`, `symdesk`, `symeraseme`, `symfritz`, `symroom`,
   `symterminal`, `symvault`, `symvibe`.
2. Decide what a client should do for an absorbed capability — most likely
   detect the *product* and then ask it, rather than probing a dead id.
3. Check `SymairaIngestContract`'s assumptions about being talked to over a
   `symingest` process boundary, which no longer exists in that form.

Not fixed here: this is Swift source, and a docs pass must not change code.
