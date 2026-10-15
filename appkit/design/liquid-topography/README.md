# Symaira Design Kit · „Liquid Topography“

Gemeinsame Designquelle für alle Symaira-Apps (macOS, iOS) und symaira.com.

## Inhalt

| Pfad | Zweck | Bearbeiten? |
|---|---|---|
| `DESIGN.md` | Farben, Schrift, Radien, Abstände, Komponenten und Regeln (Google-DESIGN.md-Format) | ✅ Quelle |
| `topo.json` | Parameter der Topografie: Linien, Deckkraft, Zustände, fps | ✅ Quelle |
| `build.py` | erzeugt `dist/` und prüft 52 Kontrastpaare (hell und dunkel) | – |
| `dist/tokens.css` | CSS-Variablen `--sym-*`, hell/dunkel über `prefers-color-scheme` oder `data-theme` | ❌ generiert |
| `../../Sources/SymairaTheme/SymairaTokens.swift` | adaptive SwiftUI-Farben, Radien, Abstände, Topo-Parameter (auch in `dist/`) | ❌ generiert |
| `dist/tokens.json` | flache Token-Liste für andere Tools | ❌ generiert |
| `web/symaira-topo.js` | reaktive Topografie für das Web (WebGL2, ohne Abhängigkeiten) | ✅ |
| `web/demo.html` | Demo, die nur Kit-Dateien nutzt | – |
| `web/catalog.html` | interaktiver Komponenten-Katalog mit klar markierten Demo-Daten | ✅ |
| `web/test_catalog.py` | Browser-Checks für Desktop, Touch, Tastatur, Kontraste und reduzierte Bewegung | ✅ |
| `../../Sources/SymairaTheme/Resources/SymairaTopo.metal` | dieselbe Topografie als Metal-Shader | ✅ |
| `../../Sources/SymairaTheme/SymairaTopoView.swift` | SwiftUI-View und `.topoProtected()`-Modifier | ✅ |
| `../../Sources/SymairaTheme/Resources/Fonts/` | Google Sans Flex (unveränderte Originaldatei, OFL, Markenhinweis) | ❌ nur durch neuere Originalversion ersetzen |

## Ablauf nach Änderungen

```bash
python3 build.py                              # dist/ neu erzeugen + Kontraste prüfen (Exit 1 bei Verstoß)
npx -y @google/design.md lint DESIGN.md       # Struktur + Referenzen + WCAG
```

## Web

### Komponenten-Katalog

Nach `python3 build.py` den Kit-Ordner lokal per HTTP bereitstellen und
`web/catalog.html` öffnen. Der Katalog enthält Formulare, Tabellen mit Suche
und Sortierung, Menüs, Dialoge, Einstellungen sowie Leer- und Fehlerzustände.
Alle Aktionen sind ausschließlich Vorschau, ohne Backend oder Speicherung.
Die Topografie animiert in freien Zwischenräumen und Randflächen. Karten,
Tabellen, Texte und Navigation bleiben geschützt und deckend. Der Schalter
„Bewegung reduzieren“ pausiert auch den Hintergrund.

```sh
# From this kit directory; requires an already installed Playwright/Chromium.
CATALOG_URL=http://127.0.0.1:8765/web/catalog.html python3 web/test_catalog.py
# Optional existing Chromium binary: CHROMIUM_EXECUTABLE=/path/to/chrome
python3 web/export_catalog.py /path/to/Liquid-Topography-Katalog.html
```

Der Offline-Export bettet Tokens, Shader-Engine und Parameter ein und braucht keinen Server.
Er ist keine zweite Designquelle. Native SwiftUI-Komponenten und VoiceOver
müssen im jeweiligen App-Piloten separat geprüft werden.

```html
<link rel="stylesheet" href="dist/tokens.css">
<main id="app"> <section data-topo="hill">…</section> <span data-topo-status role="status">…</span> </main>
<script type="module">
  import { mountTopo } from "./web/symaira-topo.js";
  const topo = mountTopo(document.getElementById("app"), { params: await (await fetch("topo.json")).json() });
  topo.setState("thinking");
</script>
```

## SwiftUI

```swift
@State var topo = SymairaTopoModel()
ZStack {
    SymairaTopoView(model: topo)
    ContentView().topoProtected(in: topo, hill: true)
}
.coordinateSpace(name: SymairaTopo.space)
// topo.state = .thinking
```

Die `.metal`-Datei muss im App- bzw. Package-Target liegen, damit `ShaderLibrary` sie findet.

## Status

Siehe `DESIGN.md` → *Known Gaps*. SwiftUI-Clients nutzen `import SymairaTheme`; die Web-Komponente wird nach `symaira.com` vendored.

## Native Demos

```bash
zsh design/liquid-topography/apple/Demo/build-ios.sh <ausgabeordner>   # iOS-Simulator
```

### macOS

```bash
zsh design/liquid-topography/apple/Demo/build.sh <ausgabeordner>   # baut .app mit swiftc + metallib, ohne Xcode-Projekt
```
