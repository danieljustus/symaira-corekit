# ADR 0001: authkit — geteilte Session-/Auth-Schicht & Biometrie-Broker

> **Status**: Zurückgestellt — Design akzeptiert, Umsetzung gated auf einen echten Zweit-Consumer (siehe „Reality-Check"). Phase 2 zusätzlich an ADR-0002 *Unified Identity* (vault-pro) gekoppelt.
> **Date**: 2026-06-18
> **Scope**: corekit (`authkit`), Erst-Consumer `symmemory`; optionaler Broker-Agent als Phase 2
> **Verwandt**: vault-pro `docs/adr/unified-account.md` (Unified Billing & Identity), vault `internal/session`, `../ECOSYSTEM.md`

## Context

Jedes Tool fordert Auth heute getrennt an. Konkrete Reibung im Code:

- **vault** hat bereits einen vollwertigen Stack in `internal/session`: OS-Keychain-Cache (`zalando/go-keyring`, CGO-frei), TTL mit Sliding-Window (`LastAccess` wird pro Zugriff verlängert), separater AES-256-GCM-Wrap-Key (Defense-in-Depth) und einen optionalen TouchID-Layer (`biometric.go` Interface + `touchid_darwin.go`, `//go:build darwin && cgo`). Sessions sind **per-vault-dir** gescoped (`"symvault:" + vaultDir`).
- **memory** teilt davon **nichts**: `internal/security/crypto.go` leitet den Key bei *jedem* Aufruf frisch via PBKDF2 (600k Iterationen) aus einer getippten Passphrase ab — **kein Keyring, kein Caching, keine Biometrie**, keinerlei Abhängigkeit zu vaults session-Paket.

Die eigentliche Lücke ist also nicht „TouchID nervt", sondern **zwei kryptografisch unabhängige Modelle ohne gemeinsame Auth-/Session-Schicht**.

### Constraints (nicht verhandelbar)

1. **Standalone-first** (corekit `AGENTS.md`, wörtlich): „this library must not make any consumer require another Symaira tool at build time or startup." Jedes Tool muss allein voll funktionsfähig bleiben.
2. **corekit ist 100 % CGO-frei** (`CGO_ENABLED=0` für linux/darwin/windows; bewusst `modernc.org/sqlite`). TouchID braucht CGO (LocalAuthentication) und darf damit **nicht** in corekit.
3. **memory ist Zero-CGO** (eigenes `CLAUDE.md`). Es darf TouchID nicht in-process einbinden.
4. **Sprach-Policy:** Go = cross-platform CLIs/MCP (corekit-gestützt); Swift = native macOS-Apps/Hardware; kein geteiltes Swift-Lib (tune/operate/terminal haben je eigenen Core).

## Reality-Check (2026-06-18, vor Umsetzung verifiziert)

Bei der Ausarbeitung des Extraktionsplans wurde die Ausgangsprämisse am Code geprüft und **teilweise widerlegt**:

- **Nur `vault` hat Decrypt-on-Read.** memory (OSS *und* Pro), seek und fetch ver-/entschlüsseln beim normalen Zugriff nichts. Memorys PBKDF2 (`internal/security/crypto.go`) wird **ausschließlich** vom optionalen `backup --password`-Flag benutzt — kein Prompt bei `list`/`search`/`set`. Die Context-Aussage „memory leitet bei jedem Aufruf frisch ab" ist damit **nur für den Backup-Pfad** korrekt, nicht für den Alltag.
- **Session-Caching existiert ökosystemweit nur in vault** (`zalando/go-keyring` ausschließlich in vaults `go.mod`).
- **vaults Default-`sessionTimeout` ist 15 min** (`config.go:30`), per Config / `--ttl` überschreibbar. Das ist die eigentliche Quelle des gefühlten „jedes Mal".

**Konsequenz für diese ADR:** Es gibt **heute keinen zweiten Consumer**. Die `authkit`-Extraktion (D1) wäre damit Verschieben funktionierenden Codes über eine Repo-Grenze für einen Verbraucher, der noch nicht existiert. Der konkrete Nutzer-Use-Case (einmal entsperren → 8 h Ruhe) ist für das einzige betroffene Tool **ohne Code** über `sessionTimeout: 8h` lösbar.

→ **Trigger für Umsetzung:** Erst starten, wenn ein echtes zweites Tool Decrypt-on-Read bekommt (z. B. memory-pro E2E-Cloud-Sync) **oder** ADR-0002 grünes Licht gibt. Die folgenden Design-Entscheidungen (D1–D6) bleiben als *vorab geklärtes* Zielbild gültig; nur die Dringlichkeit/der Auslöser (D7) ist revidiert.

## Decision

### D1 — `authkit` kommt nach corekit (CGO-freier Teil)

`vault/internal/session` wird nach `corekit/authkit` gehoben — aber nur der CGO-freie Anteil:

| Bestandteil | nach corekit? | Begründung |
|---|---|---|
| Keychain-Session-Cache + TTL + Sliding-Window | ✅ ja | `zalando/go-keyring` ist CGO-frei (ruft `/usr/bin/security`) |
| Biometrie-**Interface** + No-op-Fallback | ✅ ja | reines Go |
| TouchID-**Implementierung** (`touchid_darwin.go`) | ❌ nein | `darwin && cgo` bricht den CGO-Vertrag |

Das ist exakt das Muster, das vault intern schon nutzt: `biometric.go` definiert `BiometricAuthenticator` + No-op; die echte TouchID wird per `SetBiometricAuthenticator` injiziert. Hochziehen = Dependency-Injection, kein Umbau.

### D2 — Standalone bleibt: Library, kein Daemon-Zwang

Eine geteilte **Library** macht ein Tool nicht unselbständig (corekit ist heute schon überall drin, jedes Binary bleibt statisch + eigenständig). Was Standalone bräche, wäre ein **harter Daemon-Zwang** — den vermeiden wir über das **ssh / ssh-agent-Modell**: Resolution-Kette pro Tool

1. Broker-Agent läuft & Session gültig → Key von dort (Komfort-Pfad),
2. sonst → eigener Keychain-Session-Cache (D1),
3. sonst → tooleigene Passphrase-Abfrage (heutiges Verhalten).

→ Bei **0 laufenden Agents** ist jedes Tool voll funktionsfähig. Der Agent ist optionaler Beschleuniger, nie Voraussetzung.

### D3 — Kein separates macOS-corekit

Ein „corekit-darwin" widerspricht **beiden** etablierten Mustern: Go-Seite teilt Infra *CGO-frei* (corekit); Native/Swift-Seite teilt *gar kein* Lib (jedes Tool self-contained). Für aktuell ~eine Datei wäre es Modul-Wildwuchs. **Verworfen.**

### D4 — Wohin TouchID: drei Ebenen, keine davon ein neues Shared-Lib

| Ebene | Ort | CGO |
|---|---|---|
| Biometrie-Interface + No-op | `corekit/authkit` | nein |
| **In-process**-Impl (standalone vault) | **im Tool selbst**, build-tag `darwin && cgo` | ja — im *App*-Binary, nicht in der Lib |
| **Cross-tool**-Impl | **im Broker-Agent** (Phase 2) | ja, auf eine getaggte Datei begrenzt |

Schlüssel: Der CGO-freie Vertrag gilt für die **Library** (corekit), nicht für **Apps**. vault darf intern CGO (tut es heute schon). TouchID braucht damit **nie** ein eigenes geteiltes Modul.

### D5 — Broker-Agent ist Go, nicht Swift

Der Agent ist zu ~90 % Session-/Keyring-/Socket-Logik (genau das, was `authkit` schon kann) und zu ~10 % ein `LAContext`-Aufruf. Swift hieße, die TTL-/Keyring-Logik neu zu bauen. Also **Go-Agent, der `authkit` wiederverwendet**, mit TouchID in derselben `darwin && cgo`-Datei, die vault hat. Die „native = Swift"-Policy zielt auf Apps/Hardware (GUI, SMC, AX) — nicht auf einen headless Broker.

**Ausnahme (YAGNI-Grenze):** Erst *wenn* zwei Go-Binaries in-process TouchID brauchen (standalone-vault **und** Agent), ein **eng geschnittenes** `symaira-biometric` (darwin+cgo), das beide importieren — ausdrücklich **kein** breites macOS-Sammelbecken. Bei einem Consumer: die ~50-Zeilen-Datei dort lassen/duplizieren.

### D6 — Security-Posture: gestuft, nicht „global alles 8 h offen"

Single-Unlock-für-alles ist ein realer Downgrade (jeder lokale Prozess / jeder am offenen Mac liest in den 8 h alle Secrets). Deshalb gestuft:

- **Low-value** (memory, seek …): entsperren für das TTL-Fenster.
- **High-value** (Produktions-vault): darf weiter Re-Auth **pro Zugriff** verlangen — vault kann das per-Read-Biometric-Gating bereits.
- **Leitplanken:** zusätzlicher Idle-Timeout neben der Obergrenze; Screen-Lock-/Sleep-Hook (`com.apple.screenIsLocked`) flusht den Agent; Master-Material nie auf Disk, nur Agent-RAM + Keychain-Item mit `kSecAccessControlUserPresence`.

### D7 — Phasing *(revidiert nach Reality-Check)*

- **Phase 0 (jetzt, ohne Code):** Nutzer-Use-Case über vault-Config lösen — `sessionTimeout: 8h` (gestuft: Dev-Vaults länger, Produktions-Vaults kürzer). Deckt „einmal entsperren → 8 h" für das einzige Tool mit Friktion ab.
- **Phase 1 (zurückgestellt, *nicht* mehr „jetzt"):** `authkit` aus vault extrahieren → corekit — **erst wenn ein echter Zweit-Consumer existiert** (memory-pro E2E o. Ä.). Ohne zweiten Consumer ist es voreilige Infra. Memory ist entgegen der ursprünglichen Annahme **kein** sinnvoller Erst-Consumer (kein Decrypt-on-Read).
- **Phase 2 (zurückgestellt):** Broker-Agent nur bauen, wenn Phase 1 ausgelöst hat **und** der Cross-Tool-Schmerz real ist, **oder** ADR-0002 (Unified Identity, vault-pro) grünes Licht gibt. Der Agent ist technisch fast deckungsgleich mit dem Kern dieser Entscheidung — dort verdient sich seine Angriffsfläche, nicht als isoliertes Dev-Komfort-Feature.

## Extraction Notes (die eigentliche Phase-1-Arbeit)

1. `session.go` hängt an `internal/crypto` (`Wipe`) und `internal/metrics` → Wipe-Helfer mitnehmen oder inline; Metrics hinter Interface/No-op entkoppeln.
2. Key-Namespace generalisieren: fix `"symvault:" + vaultDir` → Parameter, damit memory `"symmemory:<scope>"` etc. übergeben kann.
3. `memory` andocken — Zero-CGO bleibt: es bekommt Caching; Biometrie liefert später der Agent.
4. vault auf `corekit/authkit` umstellen, `touchid_darwin.go` als injizierte CGO-Impl in vault belassen.

## Consequences

**Positiv:** memory/seek/fetch gewinnen Session-Caching standalone; eine getestete Auth-Schicht statt Drift; CGO/Zero-CGO-Trennung sauber; respektiert Standalone- und Sprach-Policy; Phase 2 bleibt optional.

**Kosten/Risiken:** Extraktion berührt vault (Regressionsrisiko an sensibler Stelle → Test-Parität vor Umstieg). Cross-tool-Komfort erst mit Phase 2. Broker-Agent ist hochwertiges Angriffsziel → bewusst an Unified Identity gekoppelt, nicht beiläufig gebaut.

## Non-Goals

- Kein macOS-corekit (D3). Kein geteiltes Swift-Lib.
- Kein gemeinsames Schlüsselmaterial über Tools hinweg — jedes Tool behält seine eigene Krypto (AES/age/PBKDF2); der Broker verwahrt nur opake Per-Tool-Secrets hinter *einem* Biometrie-Gate.
- Kein Daemon-Zwang für irgendein Tool.

---

*Phase 1 ist akzeptiert. Phase 2 erfordert Daniels explizite Freigabe bzw. die Unified-Identity-Entscheidung.*
