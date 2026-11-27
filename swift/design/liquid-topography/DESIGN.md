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
  # Kontur von Bedienelementen (Textfelder, deckender Sekundär-Fallback), mindestens 3:1
  # gegen raised, surface und canvas (WCAG 1.4.11). `line` bleibt die ruhige Linie für Karten
  # und Trenner (Practical UI: stroke strong vs. stroke weak). Entschieden 2026-11-27 (#515).
  control-outline: "#827F78"
  control-outline-dark: "#74746F"
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
  # Rollennamen = SymairaTypography (Apple) in kebab-case, damit Web und Apple dieselben Namen nutzen.
  # Nur die größten Überschriften (display, title) und die Wortmarke: Google Sans Flex, opsz 18.
  # Alle übrigen Texte: Figtree (siehe Abschnitt Typography).
  display:
    fontFamily: Google Sans Flex
    fontSize: 26px
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  title:
    fontFamily: Google Sans Flex
    fontSize: 20px
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.015em"
  stat:
    fontFamily: Figtree
    fontSize: 27px
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  readout:
    fontFamily: Figtree
    fontSize: 18px
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.015em"
  heading:
    fontFamily: Figtree
    fontSize: 16px
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  subheading:
    fontFamily: Figtree
    fontSize: 14px
    fontWeight: 650
    lineHeight: 1.35
  # Nur Web (Eingabebox); Apple hat keine Composer-Komponente.
  body-lg:
    fontFamily: Figtree
    fontSize: 14.5px
    fontWeight: 450
    lineHeight: 1.5
  body:
    fontFamily: Figtree
    fontSize: 13.5px
    fontWeight: 450
    lineHeight: 1.5
  body-medium:
    fontFamily: Figtree
    fontSize: 13.5px
    fontWeight: 550
    lineHeight: 1.5
  body-emphasized:
    fontFamily: Figtree
    fontSize: 13.5px
    fontWeight: 600
    lineHeight: 1.5
  label:
    fontFamily: Figtree
    fontSize: 12.5px
    fontWeight: 550
    lineHeight: 1.4
  callout:
    fontFamily: Figtree
    fontSize: 12.5px
    fontWeight: 450
    lineHeight: 1.5
  caption:
    fontFamily: Figtree
    fontSize: 11.5px
    fontWeight: 450
    lineHeight: 1.4
  micro:
    fontFamily: Figtree
    fontSize: 11.5px
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "0.05em"
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
  # Seitenaktionen (GUIDELINES CTRL-1): 36pt-Kapsel, 8px + 20px Zeilenhöhe + 8px.
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    typography: "{typography.body-emphasized}"
    rounded: "{rounded.pill}"
    padding: 8px 20px
  button-primary-dark:
    backgroundColor: "{colors.ink-dark}"
    textColor: "{colors.surface-dark}"
    rounded: "{rounded.pill}"
  # Deckende Fassung: Web, „Transparenz reduzieren“ und Systeme vor macOS/iOS 26.
  # Apple nutzt sonst natives Liquid Glass in derselben Geometrie (UI-Katalog E02).
  button-secondary:
    backgroundColor: "{colors.raised}"
    borderColor: "{colors.control-outline}"
    textColor: "{colors.ink}"
    typography: "{typography.body-emphasized}"
    rounded: "{rounded.pill}"
    padding: 8px 20px
  button-secondary-dark:
    backgroundColor: "{colors.raised-dark}"
    borderColor: "{colors.control-outline-dark}"
    textColor: "{colors.ink-dark}"
  input:
    backgroundColor: "{colors.raised}"
    borderColor: "{colors.control-outline}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: 8px 12px
  input-dark:
    backgroundColor: "{colors.raised-dark}"
    borderColor: "{colors.control-outline-dark}"
    textColor: "{colors.ink-dark}"
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
    padding: 4px 12px
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
    padding: 16px
  card-dark:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.ink-dark}"
  user-bubble:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.xl}"
    padding: 12px 16px
  user-bubble-dark:
    backgroundColor: "{colors.raised-dark}"
    textColor: "{colors.ink-dark}"
  composer:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body-lg}"
    rounded: "{rounded.xl}"
    padding: 16px 12px 8px 16px
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
    typography: "{typography.subheading}"
    rounded: "{rounded.lg}"
    padding: 12px
  alert-critical-dark:
    backgroundColor: "{colors.critical-soft-dark}"
    textColor: "{colors.critical-dark}"
  # Apple: .symairaButtonStyle(.destructive), Geometrie wie button-primary (GUIDELINES ACTION-4).
  button-danger:
    backgroundColor: "{colors.critical}"
    textColor: "{colors.on-critical}"
    typography: "{typography.body-emphasized}"
    rounded: "{rounded.pill}"
    padding: 8px 20px
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
    typography: "{typography.subheading}"
    rounded: "{rounded.lg}"
    padding: 12px
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

**Gemeinsame Quelle:** Wiederverwendbare Design- und Interaktionsregeln, die in
einem Symaira-Produkt abgestimmt werden, werden hier und in `SymairaTheme`
implementiert und getestet. Produkte konsumieren diese Grundlage, statt lokale
Kopien zu pflegen. Fachlogik, Navigation und bestehende Einstellungs-Schlüssel
bleiben im Produkt. Native Zuordnung und Migrationsgrenzen stehen in
[`docs/workspace-foundation.md`](../../docs/workspace-foundation.md).

## Colors

Jede Rolle gibt es hell (Standardwert) und dunkel (Suffix `-dark`). Code nutzt immer die Rolle, nie den Hexwert.

- **canvas / sidebar / surface / raised:** Graustufen mit minimaler Wärme. Von hinten nach vorne: canvas, sidebar, surface (Karten, Eingabebox), raised (Nutzer-Blase, Hover). Hell ist `raised` gleich `canvas`: deckende Bedienelemente (Textfelder, Sekundär-Button ohne Glas) tragen deshalb in beiden Modi eine 1px-Kontur in `control-outline`.
- **line / control-outline:** zwei Konturstärken nach Practical UI. `line` ist die ruhige, dekorative Linie für Karten, Trenner und Tabellen (unter 3:1, bewusst). `control-outline` begrenzt Bedienelemente und erreicht mindestens 3:1 gegen `raised`, `surface` und `canvas` (WCAG 1.4.11). „Kontrast erhöhen“ verstärkt beide.
- **ink / ink-2 / ink-3:** Haupttext, Sekundärtext, Metadaten. Selbst `ink-3` erreicht auf canvas mindestens 4.5:1. Noch blasseren Text gibt es nicht.
- **primary (Champagner `#E0D2BA`):** Markenakzent, in beiden Modi derselbe Wert. Auf hellen Flächen erreicht er nur 1,1 bis 1,3:1 und ist dort **nie** ein Zustandsmerkmal.
- **selected / on-selected:** Auswahlzustand für Segmente, Schalter (an), Häkchen und Reglergriffe. Dunkel: Champagner mit dunkler Schrift. Hell: Tinte `#141413` mit heller Schrift (Variante A, 15,7:1 gegen die Schiene). Code nutzt immer `selected`, nie `primary`, für Zustände.
- **focus:** 2px-Fokusring. Dunkel Champagner, hell Tinte.
- **Primäraktion:** gefüllte Tinte mit Flächenfarbe als Schrift (`button-primary`), in beiden Modi. Höchstens eine Primäraktion pro Ansicht.
- **critical / warning / positive:** nur für Status, immer zusätzlich mit Text oder Symbol, nie allein über die Farbe. Der helle Modus hat eigene, dunklere Töne (mindestens 4,5:1 auf `surface`). Grün nur für echte Live-Messwerte; Beispiel- oder Testdaten bekommen ein neutrales Symbol und den Text „Beispiel“. Eine eigene Info-Farbe (etwa Blau) gibt es nicht: Hinweise ohne Status sind neutral, `ink-2` plus Info-Symbol.
- **Gesperrte Bedienelemente:** zusätzlich zum ausgegrauten Zustand den Text „Gesperrt“ zeigen. Reine Transparenz ist kein Sperrsignal.
- **topo:** Farbe der Höhenlinien. Sie wird nur mit sehr geringer Deckkraft verwendet (siehe Liquid Topography).

## Typography

**Google Sans Flex** ist die Markenschrift und bleibt den größten Überschriften vorbehalten: Wortmarke „Symaira“, Display (H1, Hero) und der Bildschirmtitel. **Figtree** setzt alle übrigen Texte: Abschnitts- und Kartenüberschriften, Messwerte, Fließtext, Labels, Buttons und Captions. SF Mono bleibt für Code. Beide Schriften stehen unter der SIL Open Font License 1.1, sind also kommerziell und auf allen Plattformen (Apple, Web, Windows, Android, Print) nutzbar, und werden als unveränderte Originaldateien mitgeliefert; Lizenz- und Markenhinweise liegen neben den Dateien. Kein Google-Fonts-CDN, keine Teilmengen oder Umbenennungen: eine veränderte Fassung darf den Namen nicht tragen. SF Pro ist keine Alternative: Apple lizenziert sie nur als Systemschrift auf Apple-Geräten, nicht zum Einbetten, als Webfont oder auf anderen Plattformen.

- **Feste optische Größe** für Google Sans Flex: `opsz 18`, keine automatische Anpassung (automatisch wird sie unter 14px um 5 bis 8 % breiter und wirkt gesperrt). Figtree hat nur eine Gewichtsachse (300 bis 900). Web: `tokens.css` setzt `font-optical-sizing: none; font-variation-settings: 'opsz' var(--sym-opsz)` bewusst mit `!important`, weil jede `font`-Kurzschreibweise beide Werte zurücksetzt und über Spezifität sonst gewinnt; Figtree ignoriert den Wert. Elemente in Google Sans Flex (`.sym-type-display`, `.sym-font-brand`, eigene H1 und Wortmarke) setzen `--sym-opsz: 18`. Weitere Variationsachsen nur über `font-weight`/`font-stretch` steuern, nicht über eigene `font-variation-settings`. Apple: Variationsachse `opsz` nur für Google Sans Flex explizit setzen (`SymairaFont`).
- **Gewichte:** Figtree: Fließtext und Captions 450, Labels und Buttons 550, Hervorhebung und Gruppenlabels 600, Unterüberschriften 650, Überschriften und Messwerte 700. Google Sans Flex: Display und Titel 700.
- **Dunkelmodus:** Kleine graue Sekundärtexte (Captions, Sekundärtext neben Bedienelementen) bekommen im Dunkelmodus +0.01em Laufweite, damit helle Glyphen auf dunklem Grund nicht zusammenlaufen. Apple: `SymairaTextRole.secondary`/`.caption` über `.symairaText(_:)`. Web: `--sym-tracking-quiet` (hell 0, dunkel 0.01em) in `.sym-type-caption` und `.sym-text-quiet`.
- **Antialiasing:** Graustufen statt Subpixel. Web: `tokens.css` setzt `-webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale` auf `body`. Apple: macOS (seit 10.14) und iOS glätten Schrift bereits in Graustufen; nichts deaktivieren (`CGContext.setShouldAntialias(false)` o. ä. ist verboten).
- **Ziffern** in Messwerten tabellarisch (`tnum` bzw. `.monospacedDigit()`).
- **Rollen:** Die Namen im Front Matter sind die Apple-Rollen in kebab-case (`body-emphasized` = `SymairaTypography.bodyEmphasized`). `display` setzt den Seitentitel von `SymairaPage`, `title` Überschriften in Onboarding und Sheets. `micro` ist das Gruppenlabel (`.sectionLabel`, Versalien vom Aufrufer). `body-lg` gibt es nur im Web (Eingabebox). Monospace nutzt auf Apple die System-Monospace in Textstilgröße (`mono` = `.body`, `monoSmall` = `.caption`) mit Systemzeilenabstand.
- **Zeilenhöhe:** Die `lineHeight`-Werte gelten auf allen Plattformen. Apple setzt sie über `.font(role)` bzw. `.symairaText(_:)` als zusätzlichen Zeilenabstand über der natürlichen Zeilenhöhe der Schrift (Figtree 1,2, Google Sans Flex 1,25). Einzeilige Texte und Bedienelemente bleiben gleich hoch.
- **Zeilenlänge:** Fließtext höchstens etwa 75 Zeichen (Refactoring UI 45–75, Practical UI 40–80). Apple: `SymairaMetrics.proseMeasure` (440pt, Figtree 13,5pt ≈ 71–73 Zeichen); die Seitenspalte `readableContentWidth` trägt Karten, Formulare und Listen, nicht Absätze.
- **Dynamic Type:** Größen skalieren relativ zum zugehörigen Textstil. Auf iOS sind alle Rollen um 15/13,5 größer (`SymairaMetrics.textScale`), Fließtext also 15pt bei Standardgröße; die 17pt der Apple-Richtlinien wirkten in dichten Symaira-Ansichten zu groß (#523). tvOS nutzt den Plattformfaktor 2.
- **Keine Symbole als Schriftzeichen.** Die Schriften enthalten nicht jedes Symbol (Google Sans Flex etwa kein ⓘ → ✓ ✕ ⌥); der Browser würde eine Ersatzschrift einsetzen. Symbole sind SVG bzw. auf Apple-Plattformen `SymairaIcon`.
- Web-Fallback-Ketten: `--sym-font` `"Google Sans Flex", -apple-system, BlinkMacSystemFont, system-ui, sans-serif`; `--sym-font-text` `"Figtree", -apple-system, BlinkMacSystemFont, system-ui, sans-serif`.

## Layout

- Desktop-Arbeitsfenster: ein eigenständiges Hauptpanel mit 20pt Rundung und 8pt Abstand rechts/unten. Seitenleiste und native Toolbar bilden eine gemeinsame Chromfläche; keine zusätzliche harte Trennlinie neben der Panelkante. Scrollleiste und Topografie bleiben im Panel.
- Sidebar: Standardbreite 272pt, per Trennkante auf 224–360pt verstellbar, eingeklappt eine 64pt-Iconleiste. Die 10pt breite Ziehfläche zeigt beim Hover den horizontalen Größenänderungs-Cursor. Unter 144pt vorgeschlagener Breite klappt die Leiste ein; Ziehen nach rechts öffnet sie wieder. Der Toolbar-Button mit ⌃⌘S bleibt erhalten und merkt sich die gewählte Breite.
- Bei ausgeklappter Sidebar bleiben mindestens 568pt für den Inhalt. Engere Fenster verwenden vorübergehend die Iconleiste. Breitenänderungen dürfen Inhalt, Entwürfe, Scrollposition und laufende Bedienung nicht neu erzeugen; Schutzzonen folgen dem tatsächlichen Layout.
- Prosa bleibt in einer lesbaren, zentrierten Spalte; Tabellen, Grids und Dashboards dürfen einen breiteren produktspezifischen Inhaltsrahmen nutzen. Native Toolbar-Höhen werden nicht durch eine zweite feste Kopfzeile verdoppelt.
- Großzügige Innenabstände: Inhaltsaktionen 20pt horizontal, Pills 4×12px, Sidebar-Einträge 8×12px, Karten 16px, Eingabebox 16/12/8/16px.
- Abstandsraster in 4px-Schritten, gängig sind 8, 12, 16, 20 und 24px. Auch Komponenten-Innenabstände liegen auf dem Raster.
- Touch-Ziele mindestens 44pt auf iOS. Primär-/Sekundäraktionen auf macOS 36pt (Seitenaktionen) bzw. 28pt (Werkbank, GUIDELINES CTRL-1), mit identischer Geometrie und Schrift in beiden Rollen. Ein Zustandswechsel darf den Button nicht schmaler oder flacher machen; für wechselnde Beschriftungen eine stabile Label-Fläche reservieren.

## Elevation & Depth

Tiefe entsteht fast nur durch Flächenstufen und 1px-Linien (`line`). Schatten gibt es nur bei schwebenden Elementen (Eingabebox, Panels, Menüs): `0 1px 2px rgba(0,0,0,.05), 0 10px 28px rgba(0,0,0,.10)`. Kein Glas über Text. Die Topografie liegt immer auf der untersten Ebene.

### Liquid Glass (nur Apple-Plattformen)

Zwei Ebenen mit getrennten Aufgaben: **Liquid Glass ist die Bedienschicht, Liquid Topography der Hintergrund.**

- **Glas:** Seitenleiste, Toolbar, Tab-Leiste, schwebende Bedienelemente (z. B. Senden, Zustandsauswahl). Native APIs (`NavigationSplitView`, Toolbars, `glassEffect`, `GlassEffectContainer`) auf macOS 26 / iOS 26 und neuer, darunter Systemmaterial. Die Topografie darf unter dem Glas leicht durchscheinen.
- **Deckend:** alle Inhaltsflächen mit Text: Karten, Code, Nutzer-Blasen, Eingabebox, Tabellen, Meldungen. Sie bleiben `surface`/`raised`.
- **Web und andere Plattformen:** nur deckende Flächen, keine Glas-Imitation per `backdrop-filter`.
- „Transparenz reduzieren“ ersetzt Glas durch deckendes `sidebar`.

## Shapes

Radien: 6px für Code-Inline, 10px für Einträge, Eingabefelder und Hinweise, 14px für Karten, 20px für Eingabebox, Blasen und das Hauptpanel sowie 999px (Kapsel) für Seitenaktionen (Primär, Sekundär, Destruktiv; GUIDELINES CTRL-1), Pills und Chips. Native Controls (Segmente, Schalter, Werkbank-Buttons, Glas-Icon-Buttons) bringen ihre Form vom System mit. Icons sind die eigenen Symaira-Icons aus `Brand/Icons/icons.svg` (Apple: `SymairaIcon`): Linien mit 2.0 Strichstärke, runden Enden und 16–17px Größe. Der Senden-Pfeil hat 2.4. SF Symbols sind nur eine Übergangslösung, solange für eine Bedeutung noch kein Symaira-Icon existiert; dann mit Gewicht `.semibold` (`SymairaTokens.iconWeight`), und das fehlende Icon wird in `icons.svg` ergänzt.

## Components

Siehe `components:` oben. Varianten sind eigene Einträge (`button-primary-dark`). Fokus wird immer mit einem 2px-Ring in `focus` und 2px Abstand dargestellt (`:focus-visible`), nie nur durch eine Farbänderung.

- **Native Controls (UI-Katalog 2026-11-25):** Apple nutzt für Segmente, Schalter, Menüs, Regler, Formulare, Fortschritt, Sheets und Dialoge die nativen Controls; Segmente und Schalter mit Tint `selected`, Regler mit `ink`. Im Web tragen native HTML-Elemente die Symaira-Grundlage (Figtree, Tokenfarben, `accent-color: selected`); Buttons, Menü, Regler, Hinweis, Leerzustand, Sheet und Aufklapper sind voll gestaltet. Entscheidungen je Element: `../ui-catalog/ui-catalog.md`.
- **Segmente:** auf Apple der native `Picker(.segmented)` mit Tint `selected` (`SymairaSegmentedControl`), im Web eine native Radiogruppe (UI-Katalog E07). Eine eigene Segmentschiene gibt es nicht mehr.
- **Navigation:** Auswahl über `selection`-Fläche und Gewicht 700 in beiden Modi; die Fläche allein ist kein Zustandsmerkmal.
- **Schalter:** nativ (Apple `Toggle(.switch)`, Web `<input type=checkbox switch>`), an = `selected`. Trefferfläche mindestens 44px auf Touch-Geräten.
- **Messwerte** in `ink`, unabhängig davon, ob sie sich ändern. Champagner gehört zu Auswahl, aktiven Bedienelementen und Fokus.
- **Balken und Regler:** die leere Schiene ist eine ruhige Rinne in `raised` mit 1px-Kontur in `line`, die Füllung ist `ink`, in beiden Modi. So liest sich 0 % nie als voller Balken; `ink-3` ist eine Textrolle und für Schienen zu hell. Speicher-, Nutzungs- und Prozessbalken verwenden dieselben Rollen wie native Regler. Warnungen bleiben als Text/Symbol sichtbar.
- **Darstellung:** `System / Light / Dark` steht nur im Einstellungsfenster, neben den übrigen Einstellungen. Das Zahnrad in der Toolbar öffnet dieses Fenster direkt, ohne Zwischenmenü; eine Darstellungsauswahl in der Toolbar gibt es nicht. „System“ entfernt die Vorgabe und folgt macOS weiter live, statt dessen aktuellen Zustand einzufrieren. Produkte behalten ihre bisherigen Speicherschlüssel; passive Vorschauen schreiben keine Einstellungen.
- **Karten:** `surface` mit 1px `line`, 14px Radius, 16px Innenabstand. Die Fläche hebt sich nur schwach vom Hintergrund ab (1,1:1); die Linie trägt die Abgrenzung. Karten sind keine Bedienelemente und bleiben bei `line`.
- **Textfelder** außerhalb von Formularen (`input`): `raised` mit 1px `control-outline`, 10px Radius; Fokus 2px `focus`.
- **Destruktive Aktion** (`button-danger`): deckende `critical`-Kapsel mit `on-critical`-Schrift, Geometrie der Primäraktion. Für den bestätigenden Schritt oder die eine destruktive Seitenaktion; Zeilenaktionen bleiben im Kontextmenü.

## Liquid Topography (Topografie-Ebene)

Die Hintergrundebene ist ein Shader. Im Web läuft er über WebGL2 (`web/symaira-topo.js`), auf macOS und iOS über Metal (`apple/SymairaTopo.metal`). Beide nutzen denselben Algorithmus. Parameter stehen in `topo.json`.

**Bild:** 16 Höhenstufen aus Rauschen mit Domain-Warp. Jede fünfte Linie ist eine weiche Zähllinie. Zwischen den Linien bleibt die Fläche reines `canvas`, ohne Tönung pro Höhenstufe und ohne Abdunklung; der Talkessel um den Inhalt wird zu 70 % freigestellt.

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

1. Jedes Element mit Text oder Bedienfunktion ist eine Schutzzone. Dort wird keine Linie gezeichnet. Ein schmaler 2–8px-Übergang ersetzt den früheren breiten Halo. Überlappende Masken und Konturverformungen werden nicht aufsummiert; sie dürfen keine künstlichen Schatten bilden. Eine Tönung pro Höhenstufe ist ausgeschlossen: Sie zeichnet sichtbare Kanten entlang einzelner Höhenlinien.
2. Die Deckkraft der Linien ist hart auf 0.26 begrenzt. Zustände, Wellen und Zeiger können sie nicht überschreiten.
3. Zustände ändern Tempo, Form und Tönung, aber keine Information. Die Information steht immer im Text (`role="status"` / `role="alert"`).
4. Bei `prefers-reduced-motion` bzw. „Bewegung reduzieren“ bleibt das Bild statisch, ohne Wellen und ohne Zeigerreaktion. Gleiches gilt für den Stromsparmodus unter iOS.
5. Jede Einblendung beginnt an einer zufälligen Stelle des Rauschfelds (Zeitachse 0–100), damit Fenster und Seitenwechsel neues Gelände zeigen. Höchstens 30 fps, auf Apple-Geräten 20 fps im Ruhezustand. Solange der Zeiger über der Fläche ist, rendert Apple mit der Bildrate des Displays, damit die Zeigerreaktion flüssig bleibt; beim Verlassen gilt wieder die Ruhe-Obergrenze. Auf macOS pausiert die Sichtbarkeit des zugehörigen Fensters die Bildschleife, auf iOS und tvOS die Scene-Phase; ein AppKit-Hostingfenster darf nicht durch eine dauerhaft als `background` gemeldete SwiftUI-Phase eingefroren werden. Auf allen Apple-Plattformen zeichnet eine eigene `CAMetalLayer`-Fläche (`TopoMetalSurface`), nie eine SwiftUI-`TimelineView`: macOS treibt sie mit einem `Timer`, iOS und tvOS mit einem `CADisplayLink` (`preferredFrameRateRange`: im Ruhezustand fest 20 fps, interaktiv bis `maximumFramesPerSecond` des Displays; auf iPhones mit ProMotion braucht ein Host dafür `CADisableMinimumFrameDurationOnPhone`). Integration, Eingabebeobachtung und Pausenregeln liegen plattformneutral in `TopoMetalDriver` und `TopoFramePacing`; Reduce Motion, `animationEnabled: false`, Low Power Mode und eine Scene im Hintergrund stoppen die Schleife (statisches Bild), das Entfernen aus dem Fenster macht den Display-Link ungültig (kein Retain-Zyklus, schwacher Proxy). Änderungen der Schutzzonen (`model.rects`, z. B. beim Scrollen) beobachtet die Fläche selbst und zeichnet nativ neu, ohne die SwiftUI-Hierarchie zu invalidieren. `symairaTopography(model, animationEnabled: false)` bleibt das explizite Statisch-Schalten (iOS und tvOS). Auf tvOS rechnet die Fläche im Symaira-Maßstab (`SymairaMetrics.platformScale` = 2): ein Topografie-Punkt sind zwei Bildschirmpunkte, also sind Gelände, Linienbreite, Wellen, Zeigerradius und Schutzränder doppelt so groß und das Höhenraster liegt bei 8 pt; die Modellkoordinaten bleiben Punkte. Statt eines Zeigers folgt das Feld der Fokus-Engine: die Mitte des fokussierten Elements verbiegt die Linien wie ein Zeiger, jeder Fokuswechsel sendet eine Welle der Stärke 0,6 (gedrosselt wie Layoutwellen, damit schnelles Durchblättern einer Reihe keine Wellen stapelt). Der Fokus setzt nie den interaktiven Zustand, weil auf dem Fernseher immer etwas fokussiert ist: es gilt die Ruhe-Obergrenze, nur laufende Wellen heben die Bildrate bis zum Abklingen. Im Web pausiert ein verstecktes Dokument. Wellenalter bleiben nichtnegativ, auch bei Layoutänderungen während einer Pause. Bei reduzierter Bewegung zeichnet das Web nur nach Zustands-, Layout- oder Theme-Änderungen neu, nicht per Dauertimer. Bei mehr als 20 sichtbaren Schutzzonen wird deren gemeinsame Umhüllung geschützt: Dekoration darf entfallen, Textschutz niemals.

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
- Figtree für alle Texte außer den größten Überschriften ist neu (15.11.2026) und noch nicht im vollständigen Cockpit-Piloten abgenommen; die von Inter übernommenen Gewichte 450/550/600 sind ein Startwert.
- Google Sans Flex ist in SwiftUI und im Web nur in Chrome (Pilot) geprüft. Safari/WebKit-Darstellung und VoiceOver bleiben offen.
- Die Navigationsauswahl erreicht als Fläche weniger als 3:1 und wird zusätzlich über Fettdruck markiert.
- `line` liegt bewusst unter 3:1 (1,68:1 hell, 1,39:1 dunkel auf `surface`), weil es nur noch Karten, Trenner und Tabellen begrenzt. Bedienelemente tragen `control-outline` (mindestens 3:1, entschieden 2026-11-27).
