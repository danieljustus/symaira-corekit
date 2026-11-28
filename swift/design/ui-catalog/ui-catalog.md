# UI-Katalog: Symaira (Apple + Web)

Stand: 2026-11-25, Auswahl von Daniel im Board am 2026-11-25 (33/33 entschieden, maschinenlesbar in `selection.json`).

Ergebnis Apple: 16 nativ, 3 nativ mit Symaira-Tint, 4 Liquid Glass, 10 Symaira-Eigenbau (E02 und E07 am 2026-11-26 im Soundworks-Pilot auf Liquid Glass geändert). Web: 25 Browser-nativ (W1), 8 natives Element mit Symaira-Tokens (W2).

Spalten: **Apple** / **Web** = gewählte Variante (`Out` = Element wird nicht gebraucht), **Prio** = Must / Should / Later / Out.


## Aktionen

| ID | Element | Apple-Varianten | Web-Varianten | Apple | Web | Prio | Gebaut |
|---|---|---|---|---|---|---|---|
| E01 | Primär-Button | A: Apple nativ, Systemakzent<br>B: Nativ mit Symaira-Tint<br>C: Liquid Glass prominent<br>D: Symaira heute | W1: Browser-nativ<br>W2: Natives <button> mit Symaira-Tokens | **D** | **W2** | Must | [ ] |
| E02 | Sekundär-Button | A: Apple nativ<br>B: Liquid Glass<br>C: Ohne Rahmen<br>D: Symaira heute | W1: Browser-nativ<br>W2: Natives <button> mit Symaira-Tokens<br>W3: Textlink-Button | **B** | **W2** | Must | [ ] |
| E03 | Destruktiv-Button | A: Apple nativ, Rolle destructive<br>B: Prominent rot<br>C: Symaira-Tokens (kein eigenes Control vorhanden) | W1: Browser-nativ<br>W2: Symaira-Tokens | **B** | **W1** | Must | [ ] |
| E04 | Icon-Button | A: Apple nativ, rund<br>B: Liquid Glass, rund<br>C: Symaira heute | W1: Browser-nativ<br>W2: Symaira-Tokens | **B** | **W1** | Must | [ ] |
| E05 | Toolbar-Gruppe | A: Native Glasgruppe<br>B: ControlGroup<br>C: Symaira heute | W1: Browser-nativ<br>W2: Symaira-Tokens, deckend | **A** | **W1** | Must | [ ] |
| E06 | Menü / Filter | A: Apple nativ<br>B: Picker als Menü<br>C: Symaira heute | W1: Browser-nativ<br>W2: Natives <select> mit Tokens<br>W3: Popover-Menü | **B** | **W2** | Must | [ ] |

## Auswahl

| ID | Element | Apple-Varianten | Web-Varianten | Apple | Web | Prio | Gebaut |
|---|---|---|---|---|---|---|---|
| E07 | Segmentauswahl | A: Apple nativ<br>B: Nativ mit Symaira-Tint<br>C: Symaira, Liquid Glass mit Symaira-Tint | W1: Browser-nativ (Radiogruppe)<br>W2: Radiogruppe als Segmentschiene | **B** | **W1** | Must | [ ] |
| E08 | Schalter | A: Apple nativ<br>B: Nativ mit Symaira-Tint<br>C: Checkbox (nur macOS)<br>D: Symaira heute | W1: Browser-nativ Checkbox<br>W2: Checkbox als Schalter (switch)<br>W3: Eigenbau-Schalter heute | **B** | **W1** | Must | [ ] |
| E09 | Auswahlliste | A: Apple nativ, Popup<br>B: Radiogruppe (macOS) / Inline (iOS)<br>C: Symaira-Formularzeile | W1: Browser-nativ<br>W2: Radiogruppe mit Tokens | **A** | **W1** | Must | [ ] |
| E10 | Regler | A: Apple nativ<br>B: Nativ mit Symaira-Tint | W1: Browser-nativ<br>W2: Range mit Tokens | **B** | **W2** | Must | [ ] |
| E11 | Stepper | A: Apple nativ | W1: Browser-nativ<br>W2: Number mit −/+ Buttons | **A** | **W1** | Must | [ ] |
| E12 | Datum/Uhrzeit | A: Apple nativ, kompakt<br>B: Feld (macOS) / Rad (iOS)<br>C: Kalender | W1: Browser-nativ<br>W2: Natives Feld mit Tokens | **A** | **W1** | Must | [ ] |

## Eingabe

| ID | Element | Apple-Varianten | Web-Varianten | Apple | Web | Prio | Gebaut |
|---|---|---|---|---|---|---|---|
| E13 | Textfeld | A: Apple nativ<br>B: In nativer Form<br>C: Symaira heute | W1: Browser-nativ<br>W2: Natives <input> mit Tokens | **C** | **W1** | Must | [ ] |
| E14 | Passwortfeld | A: Apple nativ<br>B: Symaira heute | W1: Browser-nativ<br>W2: Mit Tokens + Anzeigen-Button | **B** | **W1** | Must | [ ] |
| E15 | Suche | A: Apple nativ (Toolbar/Navigationsleiste)<br>B: Textfeld mit Lupe<br>C: Symaira-Textfeld mit Lupe | W1: Browser-nativ<br>W2: Search mit Tokens | **A** | **W1** | Must | [ ] |
| E16 | Mehrzeiliger Text | A: Apple nativ<br>B: TextField mit axis<br>C: In Symaira-Karte | W1: Browser-nativ<br>W2: Mit Tokens | **C** | **W1** | Must | [ ] |

## Formulare & Flächen

| ID | Element | Apple-Varianten | Web-Varianten | Apple | Web | Prio | Gebaut |
|---|---|---|---|---|---|---|---|
| E17 | Formular | A: Apple nativ, gruppiert<br>B: Spalten (macOS-Einstellungsstil)<br>C: Symaira heute | W1: Browser-nativ<br>W2: Tokens, Zeilen in Karte | **A** | **W1** | Must | [ ] |
| E18 | Gruppe / Karte | A: GroupBox<br>B: Liste inset<br>C: Symaira heute | W1: Browser-nativ<br>W2: Symaira-Karte | **C** | **W1** | Must | [ ] |

## Rückmeldung

| ID | Element | Apple-Varianten | Web-Varianten | Apple | Web | Prio | Gebaut |
|---|---|---|---|---|---|---|---|
| E19 | Fortschritt | A: Apple nativ, linear<br>B: Gauge<br>C: Kreis-Gauge<br>D: Symaira heute | W1: Browser-nativ<br>W2: Mit Tokens (Rinne + Tinte) | **A** | **W1** | Must | [ ] |
| E20 | Hinweis-Banner | A: GroupBox mit Label<br>B: Material-Fläche<br>C: Symaira heute | W1: Browser-nativ<br>W2: Symaira-Hinweis | **C** | **W2** | Must | [ ] |
| E21 | Badge | A: Nativer Listen-Badge<br>B: Kapsel mit Tint<br>C: Symaira heute | W1: Browser-nativ<br>W2: Symaira-Pill | **B** | **W1** | Must | [ ] |
| E22 | Statusanzeige | A: Label mit SF Symbol<br>B: Punkt + Text nativ<br>C: Symaira heute | W1: Browser-nativ (Text)<br>W2: Symaira-Status | **B** | **W1** | Must | [ ] |
| E23 | Leerzustand | A: Apple nativ<br>B: Symaira heute | W1: Browser-nativ<br>W2: Symaira-Leerzustand | **B** | **W2** | Must | [ ] |
| E24 | Laden | A: Apple nativ<br>B: Symaira heute | W1: Browser-nativ<br>W2: Spinner mit Tokens | **A** | **W1** | Must | [ ] |
| E25 | Bestätigungsdialog | A: Alert<br>B: Confirmation Dialog<br>C: Eigene Karte (heutiges Web-Muster) | W1: Browser-nativ<br>W2: <dialog> mit Tokens | **A** | **W1** | Must | [ ] |
| E26 | Sheet | A: Natives Sheet mit Toolbar<br>B: Symaira heute | W1: Browser-nativ<br>W2: Seitenpanel mit Tokens | **A** | **W2** | Must | [ ] |

## Navigation & Daten

| ID | Element | Apple-Varianten | Web-Varianten | Apple | Web | Prio | Gebaut |
|---|---|---|---|---|---|---|---|
| E27 | Seitenleiste | A: Apple nativ<br>B: Symaira heute | W1: Browser-nativ<br>W2: Symaira-Seitenleiste | **B** | **W1** | Must | [ ] |
| E28 | Tabs | A: Apple nativ<br>B: Segment statt Tabs<br>C: Symaira-Segment | W1: Browser-nativ<br>W2: Tabs mit Tokens | **A** | **W1** | Must | [ ] |
| E29 | Darstellung (System/Hell/Dunkel) | A: Apple nativ<br>B: Symaira heute | W1: Browser-nativ<br>W2: Segment mit Tokens | **A** | **W1** | Must | [ ] |
| E30 | Liste | A: Apple nativ, inset<br>B: Gruppiert (iOS) / Plain (macOS)<br>C: Symaira-Kartenzeilen | W1: Browser-nativ<br>W2: Symaira-Liste | **C** | **W1** | Must | [ ] |
| E31 | Tabelle | A: Apple nativ<br>B: Symaira-Raster | W1: Browser-nativ<br>W2: Tabelle mit Tokens | **A** | **W1** | Must | [ ] |
| E32 | Aufklapper | A: Apple nativ<br>B: In Symaira-Karte | W1: Browser-nativ<br>W2: Mit Tokens | **B** | **W2** | Must | [ ] |
| E33 | Kennzahl | A: LabeledContent<br>B: Gauge mit Wert<br>C: Symaira heute | W1: Browser-nativ<br>W2: Symaira-Kachel | **B** | **W1** | Must | [ ] |

## Folgen für SymairaTheme (CoreKit)

Bleiben Symaira-Komponente:
- `symairaButtonStyle(.primary)` (E01); `.secondary` (E02) behält die Symaira-Geometrie, ist seit 2026-11-26 aber natives Liquid Glass; `SymairaTextFieldStyle` (E13, E14), `.symairaCard()` (E16, E18, E30, E32), `SymairaNotice` (E20), `SymairaEmptyState` (E23), `SymairaWorkspace` + `SymairaNavigationButton` (E27), `SymairaFormRow`/`SymairaFormDivider` nur noch als Kartenzeile (E30).

Werden durch native Controls ersetzt (deprecaten, nicht sofort löschen):
- ~~`SymairaSegmentedControl` → `Picker(.segmented)`~~ (E07, am 2026-11-26 zurückgenommen: `SymairaSegmentedControl` bleibt als dünne Hülle um den nativen Picker mit Tint und 36 pt); Tabs → `TabView` (E28)
- `.symairaSwitch` → `Toggle(.switch)` + `.tint(SymairaTokens.selected)` (E08)
- `SymairaFilterMenu` → `Picker(.menu)` (E06, E09)
- `SymairaIconButton` → `Button` + `.glass` + `.buttonBorderShape(.circle)` (E04), Symbol als `Image(symairaIcon:)` im Label (`Label(_:symairaIcon:)` bleibt im Glass-Button leer, #510); Toolbar-Gruppen → `GlassEffectContainer` (E05)
- `SymairaProgressStyle` → `ProgressView(value:)` (E19); `SymairaLoadingState` → `ProgressView("…")` (E24)
- `SymairaFormSection` als Formular → `Form { Section }.formStyle(.grouped)` (E17)
- `SymairaSheetScaffold` → `.sheet` + `NavigationStack` + Toolbar-Rollen (E26); Bestätigung → `.alert` (E25)
- `SymairaAppearancePicker` → `Picker(.segmented)` (E29)
- `SymairaStatTile` → `Gauge` mit Wert (E33); `SymairaStatusLabel` → Punkt + Text (E22); `SymairaBadge` → Kapsel mit Tint (E21)
- Destruktiv: prominentes Rot als `.symairaButtonStyle(.destructive)` (E03, seit 2026-11-27, vorher `.borderedProminent` + `.tint(.red)`); Regler: `Slider` + `.tint(SymairaTokens.ink)` (E10)

Web: W1 = natives HTML-Element (Browser-Standard), W2 = natives Element mit Symaira-Tokens (`web/variants.css`).

## Entscheidungen zu Grundsatzfragen (2026-11-25)

- **Web W1** = natives HTML-Element mit Symaira-Grundlage: Figtree, Tokenfarben, `accent-color: var(--sym-selected)`, sonst Browser-Standard (Referenz: `.raw` in `web/variants.css`).
- **Felder in Formularen:** Innerhalb eines nativen `Form` native Felder; `.textFieldStyle(.symaira)` nur außerhalb von Formularen (Suchleiste, Feld auf Karte).
- **Darstellung E29** bekommt den Symaira-Tint wie E07 (`SymairaAppearancePicker` ist jetzt nativer Segment-Picker mit `.tint(SymairaTokens.selected)`).
- **Umsetzung:** CoreKit umgebaut, ersetzte Komponenten deprecated statt gelöscht; Doku, `gui-review.py` (NATIVE-1) und Katalog-App angepasst; lokal gebaut und getestet, kein Push.

## Revision 2026-11-26 (Soundworks-Pilot)

- **E07 bleibt B:** `SymairaSegmentedControl` ist der native `Picker(.segmented)` mit `.tint(SymairaTokens.selected)`: 36 pt bei Seitenaktionen, 28 pt in der Werkbank (CTRL-1), natürliche Breite, nichts wird abgeschnitten. Die eigene Glas-Variante C mit Linse wurde gebaut und verworfen: Die Linse aus „Wo ist?“ gibt es nur in Catalyst-/iOS-Controls, der macOS-Picker hat sie auch auf macOS 27.2 nicht (gemessen), und eine Nachbildung wäre eigener Code ohne natives Verhalten. `gui-review.py` meldet ein loses `.pickerStyle(.segmented)` als FORM-5, damit Tint und Höhe nicht fehlen.
- **Drei Control-Ebenen (GUIDELINES CTRL-1):** Navigation (Seitenleiste, Fenster-Toolbar, animierte Icons), Seitenaktionen (Seiten-Toolbar, Sheet-Footer, leere Zustände: eine Höhe, 36-pt-Kapseln, Glass) und Werkbank (Inhalt, Inspector, Panels, Formularzeilen: native solide Controls in `.large`, 28 pt, kein Glass). `SymairaPage` setzt Seite und Werkbank selbst.
- **E02 → B:** Sekundär-Buttons sind natives, interaktives Liquid Glass in Symaira-Geometrie (36-pt-Kapsel, Figtree); Reduce Transparency und ältere Systeme behalten die deckende `raised`-Fläche. Einziger deckender Symaira-Button pro Screen bleibt der Primär-Button.
- **Glass bleibt neutral:** `.toolbar` und `.secondary` ignorieren einen fensterweiten `.tint(SymairaTokens.selected)`; der Tint färbt nur Auswahlzustände (Segmente, Schalter).
- **Toolbar-Zeilen:** `.controlSize(.extraLarge)` macht Segmente, Menüs, Schalter und Icon-Buttons zu 36-pt-Kapseln, so hoch wie die Seitenaktionen (GUIDELINES FORM-9); Sheet-Footer: Abbrechen `.secondary`, bestätigendes Verb `.primary` (ACTION-5).

## Revision 2026-11-27 (Designcheck nach der UI-Literatur, #512 bis #516)

- **E03 bleibt B (prominentes Rot), aber aus Tokens:** `.symairaButtonStyle(.destructive)` zeichnet `critical` mit `on-critical`-Schrift in der Geometrie der Primäraktion (4,81:1 hell, 8,24:1 dunkel). `.tint(.red)` setzte weiße Schrift auf Systemrot (3,55:1 bzw. 3,41:1) und verstieß gegen COLOR-1; `gui-review.py` meldet es weiter.
- **Kontur von Bedienelementen:** neue Rolle `control-outline` (mindestens 3:1) für Symaira-Textfelder (E13, E14) und den deckenden Sekundär-Fallback (E02); Karten und Trenner bleiben bei `line`.
- **Text:** Rollen tragen die Zeilenhöhen der Token-Spec (Fließtext 1,5), Fließtext bleibt in `SymairaMetrics.proseMeasure` (440 pt, etwa 72 Zeichen), und iOS nutzt seit 0.28.2 wieder dieselbe Skala wie macOS, Fließtext 13,5 pt (#525; 0.28.0: 17/13,5, 0.28.1: 15/13,5).

## Umsetzungshinweise

- Badge (E21) und Status (E22) nutzen die kontrastgeprüften Symaira-Tonfarben statt der Systemfarben aus der Demo (Systemgrün erreicht auf `canvas` den Nicht-Text-Kontrast 3:1 nicht).
- Fortschritt (E19) nutzt den Systemakzent; native lineare Fortschrittsbalken übernehmen `tint` nicht zuverlässig.

## Offen

- Schrift in nativen Controls bleibt SF (Apple-Standard); Inhalt und Marke Figtree bzw. Google Sans Flex.
- `symairaButtonStyle` bricht Text in schmalen Containern um („Abbrec / hen“ in E25 C); danieljustus/symaira-corekit#507.
