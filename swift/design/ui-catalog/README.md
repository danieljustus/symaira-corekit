# Symaira UI-Katalog

Alle UI-Elemente von Symaira mit ihren Varianten für Apple (macOS, iPhone) und Web, als Grundlage für die Auswahl „mehr Apple-eigene Controls“. Quelle der Wahrheit ist [`elements.json`](elements.json); die Entscheidungen stehen in [`ui-catalog.md`](ui-catalog.md) und [`selection.json`](selection.json).

| Datei | Zweck |
|---|---|
| `elements.json` | 33 Elemente, je Apple-Varianten (A–D) und Web-Varianten (W1–W3) mit Code-Hinweis |
| `apple/` | SwiftUI-Katalog-App (macOS + iOS), `project.yml` für xcodegen, Quellen in `Sources/` |
| `web/variants.html`, `web/variants.css` | Web-Varianten als `<template data-v="E01-W2">` auf Basis der Liquid-Topography-Tokens |
| `capture.py` | Echte Screenshots: macOS-Fenster im Hintergrund, iPhone-Simulator |
| `board.py` | Auswahlboard (eine HTML-Datei) mit Apple-Screenshots und Live-Web-Varianten |
| `ui-catalog.md`, `selection.json` | Entscheidungen je Element (Daniel, 2026-11-25); die Katalog-App markiert die gewählte Variante mit „Gewählt“, das Board übernimmt sie als Startauswahl |

Variantenarten: **A Apple nativ**, **Nativ + Symaira-Tint**, **Liquid Glass**, **Symaira-Eigenbau heute**; Web **W1 Browser-nativ**, **W2 natives Element mit Tokens**, **W3 Eigenbau**.

## Ablauf

```bash
cd swift/design/ui-catalog
B=/Volumes/1TB_NVMe_SN850X/Dev/Symaira_Dev/builds/symaira-corekit/ui-catalog
(cd apple && xcodegen generate)
/Users/daniel/.local/bin/dev-external xcodebuild -project apple/SymairaUICatalog.xcodeproj -scheme UICatalogMac \
  -destination 'platform=macOS' -derivedDataPath $B/DerivedData build
/Users/daniel/.local/bin/dev-external xcodebuild -project apple/SymairaUICatalog.xcodeproj -scheme UICatalogiOS \
  -destination 'generic/platform=iOS Simulator' -derivedDataPath $B/DerivedData build
python3 -I capture.py --platform mac --appearance light,dark
python3 -I capture.py --platform ios --appearance light,dark
uv run --no-project --with pillow python -I board.py      # -> $B/board.html
```

Interaktiv: `open $B/DerivedData/Build/Products/Debug/SymairaUICatalog.app` zeigt alle Elemente mit Suche; `-ui-catalog-item E07` öffnet ein Element, `-variant B -solo` nur eine Variante, `-appearance dark` erzwingt Dunkel.

## Grenzen der Aufnahmen

- macOS wird vollständig im Hintergrund aufgenommen (`open -g`, Fenster hinten, nie aktiviert, Aufnahme nur per Fenster-ID, daher nie fremde Fenster). Damit Controls trotzdem aktiv gezeichnet werden, meldet sich die App **nur im Tour-Modus** als aktiv (`TourApplication.isActive`, `BackgroundKeyWindow` mit privaten AppKit-Abfragen wie `_setForceActiveControls:`). Das ist reines Katalog-Werkzeug, kein Produktcode. Fällt eine private Abfrage in einer künftigen macOS-Version weg, erscheinen betroffene Controls grau: dann Screenshots prüfen.
- Dialoge (Alert, Sheet) auf macOS sind eigene Fenster und werden separat aufgenommen.
- Der Simulator darf wegen TCC nicht auf die externe NVMe schreiben; `capture.py` speichert über `$TMPDIR` und verschiebt.
- Screenshots belegen nur die Optik, nicht das Verhalten (Tastatur, VoiceOver, Fokus).
