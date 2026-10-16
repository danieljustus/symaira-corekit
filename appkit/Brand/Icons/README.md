# Symaira Icons

135 icons drawn in-house for every Symaira product. They are owned by Symaira, so
they can be used on any platform and commercially, including in Swift, web and
Android apps.

- **Source:** `icons.svg`. This is the only file to edit. It uses a 24 pt grid with
  the live area between 3 and 21, stroke 2 with round caps and joins, and corner
  radii of 3–3.5 on large shapes and 2 on small ones.
- **Parts:** each `<g>` inside a `<symbol>` is a separately animated part.
  - `data-o` sets the transform origin.
  - `data-hover` sets the pose the part moves to on hover, e.g. `r:-8 y:-1`.
  - `data-click` lists the motions played on click, e.g. `lift:3,-20 draw@.25`.
  - The available motions are defined in `scripts/build-icons.py`.
- **Build:** run `python3 scripts/build-icons.py`. It writes:
  - `dist/svg/*.svg` — static SVGs
  - `dist/symaira-icons.css` — the web motion. Wrap an icon in `.si` and add
    `.si-play` to play its click motion.
  - `dist/icons.json` — the motion spec for other clients
  - `Sources/SymairaTheme/SymairaIconData.swift`
  - `docs/icon-preview.html`
- **Swift:** use `SymairaIconView(.delete, trigger: count)`,
  `SymairaIconButton("Delete", icon: .delete) { … }` or
  `Label("Delete", symairaIcon: .delete)`.
