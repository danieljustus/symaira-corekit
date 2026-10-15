---
version: alpha
name: Symaira Liquid Topography
description: Graue, ruhige Arbeitsflächen im Codex-Stil. Champagner nur als Akzent. Eine fluide, reaktive Topografie als einziges Markenornament.
colors:
  # Hell (Standardwerte) und Dunkel (Suffix -dark). Jede Rolle existiert in beiden Modi.
  # Freigegeben im Cockpit-Designpiloten (Revision 08, 2026-10-15).
  primary: "#E0D2BA"
  primary-dark: "#E0D2BA"
  on-primary: "#1A1814"
  on-primary-dark: "#1A1814"
  primary-soft: "#E2DED5"
  primary-soft-dark: "#312F2B"
  selected: "#141413"
  selected-dark: "#E0D2BA"
  on-selected: "#E1E0DA"
  on-selected-dark: "#1A1814"
  focus: "#141413"
  focus-dark: "#E0D2BA"
  canvas: "#EEEDEA"
  canvas-dark: "#1C1C1B"
  sidebar: "#E1E0DA"
  sidebar-dark: "#171716"
  surface: "#E1E0DA"
  surface-dark: "#141413"
  raised: "#EEEDEA"
  raised-dark: "#2B2B2A"
  selection: "#B0AEA9"
  selection-dark: "#2D2D2C"
  line: "#B0AEA9"
  line-dark: "#30302E"
  ink: "#141413"
  ink-dark: "#EEEDEA"
  ink-2: "#2B2B2A"
  ink-2-dark: "#B0AEA9"
  ink-3: "#62615D"
  ink-3-dark: "#97958F"
  positive: "#34694A"
  positive-dark: "#93C49F"
  warning: "#7E5310"
  warning-dark: "#E9BC73"
  critical: "#9A4634"
  critical-dark: "#E39C8A"
  on-critical: "#E1E0DA"
  on-critical-dark: "#141413"
  critical-soft: "#F2DED8"
  critical-soft-dark: "#3A2925"
  topo: "#2B2B2A"
  topo-dark: "#E1E0DA"
typography:
  # Google Sans Flex mit fester optischer Größe opsz 18 (siehe Abschnitt Typography).
  display:
    fontFamily: Google Sans Flex
    fontSize: 26px
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  stat:
    fontFamily: Google Sans Flex
    fontSize: 27px
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  readout:
    fontFamily: Google Sans Flex
    fontSize: 18px
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.015em"
  headline:
    fontFamily: Google Sans Flex
    fontSize: 16px
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  title:
    fontFamily: Google Sans Flex
    fontSize: 14px
    fontWeight: 650
    lineHeight: 1.35
  body-lg:
    fontFamily: Google Sans Flex
    fontSize: 14.5px
    fontWeight: 500
    lineHeight: 1.5
  body:
    fontFamily: Google Sans Flex
    fontSize: 13.5px
    fontWeight: 500
    lineHeight: 1.5
  label:
    fontFamily: Google Sans Flex
    fontSize: 12.5px
    fontWeight: 600
    lineHeight: 1.4
  caption:
    fontFamily: Google Sans Flex
    fontSize: 11.5px
    fontWeight: 600
    lineHeight: 1.4
  mono:
    fontFamily: SF Mono
    fontSize: 12.5px
    fontWeight: 500
    lineHeight: 1.65
rounded:
  sm: 6px
  md: 10px
  lg: 14px
  xl: 20px
  pill: 999px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    typography: "{typography.label}"
    rounded: "{rounded.lg}"
    padding: 12px 20px
  button-primary-dark:
    backgroundColor: "{colors.ink-dark}"
    textColor: "{colors.surface-dark}"
    rounded: "{rounded.lg}"
  button-secondary:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.lg}"
    padding: 9px 16px
  button-secondary-dark:
    backgroundColor: "{colors.raised-dark}"
    textColor: "{colors.ink-dark}"
  segment-selected:
    backgroundColor: "{colors.selected}"
    textColor: "{colors.on-selected}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
  segment-selected-dark:
    backgroundColor: "{colors.selected-dark}"
    textColor: "{colors.on-selected-dark}"
  segment-rail:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.lg}"
    padding: 4px
  segment-rail-dark:
    backgroundColor: "{colors.raised-dark}"
    textColor: "{colors.ink-2-dark}"
  switch-on:
    backgroundColor: "{colors.selected}"
    textColor: "{colors.on-selected}"
    rounded: "{rounded.pill}"
  switch-on-dark:
    backgroundColor: "{colors.selected-dark}"
    textColor: "{colors.on-selected-dark}"
  pill:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: 6px 14px
  pill-dark:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.ink-2-dark}"
  chip:
    backgroundColor: "{colors.primary-soft}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: 4px 12px
  chip-dark:
    backgroundColor: "{colors.primary-soft-dark}"
    textColor: "{colors.ink-dark}"
  sidebar-item:
    backgroundColor: "{colors.sidebar}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.md}"
    padding: 8px 12px
  sidebar-item-dark:
    backgroundColor: "{colors.sidebar-dark}"
    textColor: "{colors.ink-2-dark}"
  sidebar-item-selected:
    backgroundColor: "{colors.selection}"
    textColor: "{colors.ink}"
  sidebar-item-selected-dark:
    backgroundColor: "{colors.selection-dark}"
    textColor: "{colors.ink-dark}"
  canvas-meta:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink-3}"
    typography: "{typography.caption}"
  canvas-meta-dark:
    backgroundColor: "{colors.canvas-dark}"
    textColor: "{colors.ink-3-dark}"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: 14px 16px
  card-dark:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.ink-dark}"
  user-bubble:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.xl}"
    padding: 11px 16px
  user-bubble-dark:
    backgroundColor: "{colors.raised-dark}"
    textColor: "{colors.ink-dark}"
  composer:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body-lg}"
    rounded: "{rounded.xl}"
    padding: 14px 12px 10px 18px
  composer-dark:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.ink-dark}"
  code-block:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.mono}"
    rounded: "{rounded.lg}"
  code-block-dark:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.ink-dark}"
  stat-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.stat}"
    rounded: "{rounded.lg}"
  stat-card-dark:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.ink-dark}"
  code-addition:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.positive}"
  code-addition-dark:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.positive-dark}"
  alert-critical:
    backgroundColor: "{colors.critical-soft}"
    textColor: "{colors.critical}"
    typography: "{typography.title}"
    rounded: "{rounded.lg}"
    padding: 16px 18px
  alert-critical-dark:
    backgroundColor: "{colors.critical-soft-dark}"
    textColor: "{colors.critical-dark}"
  button-danger:
    backgroundColor: "{colors.critical}"
    textColor: "{colors.on-critical}"
    typography: "{typography.label}"
    rounded: "{rounded.lg}"
    padding: 9px 16px
  button-danger-dark:
    backgroundColor: "{colors.critical-dark}"
    textColor: "{colors.on-critical-dark}"
  brand-mark:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
  brand-mark-dark:
    backgroundColor: "{colors.primary-dark}"
    textColor: "{colors.on-primary-dark}"
  focus-ring:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.focus}"
  focus-ring-dark:
    backgroundColor: "{colors.canvas-dark}"
    textColor: "{colors.focus-dark}"
  alert-warning:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.warning}"
    typography: "{typography.title}"
    rounded: "{rounded.lg}"
    padding: 16px 18px
  alert-warning-dark:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.warning-dark}"
  divider:
    backgroundColor: "{colors.line}"
    textColor: "{colors.ink}"
  divider-dark:
    backgroundColor: "{colors.line-dark}"
    textColor: "{colors.ink-dark}"
  topo-layer:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.topo}"
  topo-layer-dark:
    backgroundColor: "{colors.canvas-dark}"
    textColor: "{colors.topo-dark}"
---

## Overview

Symaira Liquid Topography ist das gemeinsame Designsystem für alle Symaira-Produkte: Brain, Desktop, Cockpit, Vault, EraseMe, Fritz und symaira.com. Vorbild ist die Codex-Desktop-App. Die Oberfläche besteht aus ruhigen grauen Flächen mit einer zentrierten Inhaltsspalte, einer schwebenden Eingabebox und sehr wenig Dekoration. Eigenständig wird Symaira durch zwei Dinge:

1. **Champagner** als einzige Akzentfarbe, sparsam eingesetzt.
2. **Die Liquid Topography**, eine fluide topografische Hintergrundebene. Sie reagiert auf Zustand, Maus und GUI-Elemente, ohne je die Lesbarkeit zu stören.

Die Wirkung soll ruhig, präzise und hochwertig sein, wie eine Landkarte in einem stillen Raum. Werkzeug geht vor Show.

## Colors

Jede Rolle gibt es hell (Standardwert) und dunkel (Suffix `-dark`). Code nutzt immer die Rolle, nie den Hexwert.

- **canvas / sidebar / surface / raised:** Graustufen mit minimaler Wärme. Von hinten nach vorne: canvas, sidebar, surface (Karten, Eingabebox), raised (Nutzer-Blase, Hover).
- **ink / ink-2 / ink-3:** Haupttext, Sekundärtext, Metadaten. Selbst `ink-3` erreicht auf canvas mindestens 4.5:1. Noch blasseren Text gibt es nicht.
- **primary (Champagner `#E0D2BA`):** Markenakzent, in beiden Modi derselbe Wert. Auf hellen Flächen erreicht er nur 1,1 bis 1,3:1 und ist dort **nie** ein Zustandsmerkmal.
- **selected / on-selected:** Auswahlzustand für Segmente, Schalter (an), Häkchen und Reglergriffe. Dunkel: Champagner mit dunkler Schrift. Hell: Tinte `#141413` mit heller Schrift (Variante A, 15,7:1 gegen die Schiene). Code nutzt immer `selected`, nie `primary`, für Zustände.
- **focus:** 2px-Fokusring. Dunkel Champagner, hell Tinte.
- **Primäraktion:** gefüllte Tinte mit Flächenfarbe als Schrift (`button-primary`), in beiden Modi. Höchstens eine Primäraktion pro Ansicht.
- **critical / warning / positive:** nur für Status, immer zusätzlich mit Text oder Symbol, nie allein über die Farbe. Der helle Modus hat eigene, dunklere Töne (mindestens 4,5:1 auf `surface`). Grün nur für echte Live-Messwerte; Beispiel- oder Testdaten bekommen ein neutrales Symbol und den Text „Beispiel“.
- **Gesperrte Bedienelemente:** zusätzlich zum ausgegrauten Zustand den Text „Gesperrt“ zeigen. Reine Transparenz ist kein Sperrsignal.
- **topo:** Farbe der Höhenlinien. Sie wird nur mit sehr geringer Deckkraft verwendet (siehe Liquid Topography).

## Typography

**Google Sans Flex** ist die Marken- und UI-Schrift auf allen Plattformen, SF Mono bleibt für Code. Die Schrift wird als unveränderte Originaldatei mitgeliefert (SIL Open Font License 1.1, Lizenz- und Markenhinweis liegen neben der Datei). Kein Google-Fonts-CDN, keine Teilmengen oder Umbenennungen: eine veränderte Fassung darf den Namen nicht tragen.

- **Feste optische Größe `opsz 18`**, keine automatische Anpassung. Automatisch wird Text unter 14px um 5 bis 8 % breiter und wirkt gesperrt. Web: `tokens.css` setzt `font-optical-sizing: none; font-variation-settings: 'opsz' 18` bewusst mit `!important`, weil jede `font`-Kurzschreibweise beide Werte zurücksetzt und über Spezifität sonst gewinnt. Weitere Variationsachsen nur über `font-weight`/`font-stretch` steuern, nicht über eigene `font-variation-settings`. Apple: Variationsachse `opsz` explizit setzen (`SymairaFont`).
- **Gewichte:** Fließtext 500, Labels und Buttons 600, Titel 650, Überschriften und Messwerte 700.
- **Ziffern** in Messwerten tabellarisch (`tnum` bzw. `.monospacedDigit()`).
- **Dynamic Type:** Größen skalieren relativ zum zugehörigen Textstil.
- **Keine Symbole als Schriftzeichen.** Google Sans Flex enthält unter anderem ⓘ → ✓ ✕ ⌥ nicht; der Browser würde eine Ersatzschrift einsetzen. Symbole sind SVG bzw. SF Symbols.
- Web-Fallback-Kette: `"Google Sans Flex", -apple-system, BlinkMacSystemFont, system-ui, sans-serif`.

## Layout

- App-Fenster: Sidebar mit 272px, Hauptbereich mit Kopfzeile von 56px, Inhaltsspalte maximal 640 bis 720px, zentriert.
- Großzügige Innenabstände: Buttons 7–8px × 15–16px, Pills 6×14px, Sidebar-Einträge 8×12px, Eingabebox 14/12/10/18px.
- Abstandsraster in 4px-Schritten, gängig sind 8, 12, 16, 20 und 24px.
- Touch-Ziele mindestens 44pt auf iOS und 32px bei Mausbedienung.

## Elevation & Depth

Tiefe entsteht fast nur durch Flächenstufen und 1px-Linien (`line`). Schatten gibt es nur bei schwebenden Elementen (Eingabebox, Panels, Menüs): `0 1px 2px rgba(0,0,0,.05), 0 10px 28px rgba(0,0,0,.10)`. Kein Glas über Text. Die Topografie liegt immer auf der untersten Ebene.

### Liquid Glass (nur Apple-Plattformen)

Zwei Ebenen mit getrennten Aufgaben: **Liquid Glass ist die Bedienschicht, Liquid Topography der Hintergrund.**

- **Glas:** Seitenleiste, Toolbar, Tab-Leiste, schwebende Bedienelemente (z. B. Senden, Zustandsauswahl). Native APIs (`NavigationSplitView`, Toolbars, `glassEffect`, `GlassEffectContainer`) auf macOS 26 / iOS 26 und neuer, darunter Systemmaterial. Die Topografie darf unter dem Glas leicht durchscheinen.
- **Deckend:** alle Inhaltsflächen mit Text: Karten, Code, Nutzer-Blasen, Eingabebox, Tabellen, Meldungen. Sie bleiben `surface`/`raised`.
- **Web und andere Plattformen:** nur deckende Flächen, keine Glas-Imitation per `backdrop-filter`.
- „Transparenz reduzieren“ ersetzt Glas durch deckendes `sidebar`.

## Shapes

Radien: 6px für Code-Inline, 10px für Buttons und Einträge, 14px für Karten, 20px für Eingabebox und Blasen sowie 999px für Pills und Chips. Icons sind Linien-Icons mit 2.0 Strichstärke, runden Enden und 16–17px Größe. Der Senden-Pfeil hat 2.4. Auf Apple-Plattformen werden SF Symbols mit Gewicht `.semibold` verwendet.

## Components

Siehe `components:` oben. Varianten sind eigene Einträge (`button-primary-dark`). Fokus wird immer mit einem 2px-Ring in `focus` und 2px Abstand dargestellt (`:focus-visible`), nie nur durch eine Farbänderung.

- **Auswahl** über Füllung (`selected`) plus Gewicht 700, ohne Rahmen oder Schatten. Segmentschiene `raised`, 14px Radius, 4px Innenabstand.
- **Navigation:** Auswahl über `selection`-Fläche und Gewicht 700 in beiden Modi; die Fläche allein ist kein Zustandsmerkmal.
- **Schalter:** 56 × 32px Spur, 24px Knopf, an = `selected`. Trefferfläche mindestens 44px auf Touch-Geräten.
- **Messwerte** in `ink`, unabhängig davon, ob sie sich ändern. Champagner gehört zu Auswahl, aktiven Bedienelementen und Fokus.
- **Karten:** `surface` mit 1px `line`, 14px Radius. Die Fläche hebt sich nur schwach vom Hintergrund ab (1,1:1); die Linie trägt die Abgrenzung.

## Liquid Topography (Topografie-Ebene)

Die Hintergrundebene ist ein Shader. Im Web läuft er über WebGL2 (`web/symaira-topo.js`), auf macOS und iOS über Metal (`apple/SymairaTopo.metal`). Beide nutzen denselben Algorithmus. Parameter stehen in `topo.json`.

**Bild:** 16 Höhenstufen aus Rauschen mit Domain-Warp. Jede fünfte Linie ist eine weiche Zähllinie. Die Zwischenflächen sind minimal abgestuft, der Talkessel um den Inhalt wird zu 70 % freigestellt.

**Reaktionen:**

| Eingang | Wirkung |
|---|---|
| Zustand `idle` | ruhig fließend, Tempo 0.018 |
| Zustand `thinking` | Tempo 0.04, leicht stärkerer Warp, dezentes Atmen, sanfte Welle alle 1.4s vom Statuspunkt |
| Zustand `problem` | fast Stillstand, körnige Unruhe, leichte Tönung in `critical` |
| Zustand `input` | Ringe laufen auf das Element zu, das eine Eingabe braucht, Tönung in `primary` |
| Zeiger | Linien weichen in kleinem Radius (70px) linsenartig aus, stärker bei schneller Bewegung |
| Klick / Halten / Ziehen | Klick: kleine Welle. Halten: Mulde, die Linien ziehen sich ringförmig um den Zeiger zusammen. Ziehen: Wellenspur alle 70px |
| GUI-Ereignis | Element bewegt oder vergrößert sich um mehr als 24px (Aufklappen, Verschieben): Welle vom Element. Fokus, Tippen: Welle vom Feld |
| Layout | Seitenleiste auf/zu bzw. Fensterbereich verschoben: Welle läuft von der Kante über die Fläche |
| GUI-Elemente | Inhaltsflächen wirken als Hügel, um den sich die Linien legen |

**Lesbarkeitsgarantien (nicht verhandelbar):**

1. Jedes Element mit Text oder Bedienfunktion ist eine Schutzzone. Dort wird keine Linie gezeichnet. Ein schmaler 2–8px-Übergang ersetzt den früheren breiten Halo. Überlappende Masken und Konturverformungen werden nicht aufsummiert; sie dürfen keine künstlichen Schatten bilden. Die Flächentönung der Höhenstufen beträgt nur 0.018.
2. Die Deckkraft der Linien ist hart auf 0.26 begrenzt. Zustände, Wellen und Zeiger können sie nicht überschreiten.
3. Zustände ändern Tempo, Form und Tönung, aber keine Information. Die Information steht immer im Text (`role="status"` / `role="alert"`).
4. Bei `prefers-reduced-motion` bzw. „Bewegung reduzieren“ bleibt das Bild statisch, ohne Wellen und ohne Zeigerreaktion. Gleiches gilt für den Stromsparmodus unter iOS.
5. Höchstens 30 fps, auf Apple-Geräten 20 fps. Native Fenster-Sichtbarkeit und Scene-Phase pausieren die Timeline; im Web pausiert ein verstecktes Dokument. Bei reduzierter Bewegung zeichnet das Web nur nach Zustands-, Layout- oder Theme-Änderungen neu, nicht per Dauertimer. Bei mehr als 20 sichtbaren Schutzzonen wird deren gemeinsame Umhüllung geschützt: Dekoration darf entfallen, Textschutz niemals.

**Einsatz:** In Apps liegt die Ebene hinter der Hauptansicht, nicht hinter Einstellungen, Tabellen oder dichten Listen. Auf symaira.com liegt sie hinter dem Hero und den Leerflächen.

## Do's and Don'ts

- ✅ Rollen statt Hexwerte. ✅ Eine Primäraktion pro Ansicht. ✅ Status immer als Text.
- ✅ Neue Elemente mit Text bekommen `data-topo="protect"` (Web) bzw. `.topoProtected()` (SwiftUI).
- ❌ Keine weiteren Akzentfarben, keine Verläufe auf Flächen, kein Glas über Text.
- ❌ Die Topografie nie heller, dichter oder schneller einstellen als in `topo.json` festgelegt.
- ❌ Keine Bilder oder Texturen als Hintergrundersatz für die Topografie.

## Iteration Guide

1. `DESIGN.md` und `topo.json` sind die einzige Quelle. Nach jeder Änderung `python3 build.py` ausführen. Es erzeugt `dist/` und prüft Kontraste.
2. `npx -y @google/design.md lint DESIGN.md` muss ohne Fehler durchlaufen.
3. Komponenten einzeln ändern und über ihren Namen in `components:` referenzieren.
4. Generierte Dateien in `dist/` nie von Hand bearbeiten.

## Known Gaps

- Energie: Die erste Instruments-Stichprobe war kein Vorher/Nachher-Vergleich. Der reproduzierbare CPU-Vergleich und seine Grenzen stehen in `VERIFICATION.md`. Das Unsichtbar-Pausieren senkt die CPU-Last deutlich; eine Einsparung bei sichtbarer Animation ist bisher nicht belegt. GPU-Last, Watt und reale iPhone-Akkulaufzeit bleiben ungemessen. Die freigegebene Bildrate bleibt vorerst unverändert.
- iOS-Simulator: läuft (`build-ios.sh`). Metal für den Simulator muss mit `-target air64-apple-ios26.0-simulator` kompiliert werden, sonst ignoriert SwiftUI den Shader stillschweigend. Echtes Gerät nicht getestet.
- Tabellen, Menüs, Dialoge, Formulare, Einstellungen und Leer-/Fehlerzustände sind als interaktive Web-Referenz in `web/catalog.html` gestaltet. Native Umsetzung, VoiceOver-Abnahme und vollständiges Onboarding bleiben offen.
- Logo und App-Icons (A3 „Verzahnt“) sind noch nicht an die graue Palette angepasst.
- Google Sans Flex ist in SwiftUI und im Web nur in Chrome (Pilot) geprüft. Safari/WebKit-Darstellung und VoiceOver bleiben offen.
- Die Navigationsauswahl erreicht als Fläche weniger als 3:1 und wird zusätzlich über Fettdruck markiert.
