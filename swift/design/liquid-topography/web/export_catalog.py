#!/usr/bin/env python3
"""Export the component catalogue as a standalone, offline HTML file.

Run build.py first. The source remains web/catalog.html plus generated tokens;
this export is a disposable user-facing preview, never another token source.
"""
from pathlib import Path
import json
import sys

root = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    raise SystemExit('Usage: python3 web/export_catalog.py /absolute/output.html')
html = (root / 'catalog.html').read_text()
css = (root.parent / 'dist/tokens.css').read_text()
engine = (root / 'symaira-topo.js').read_text()
params = json.loads((root.parent / 'topo.json').read_text())
imports = "import { mountTopo } from './symaira-topo.js';\nconst topoParams = await (await fetch('../topo.json')).json();"
if html.count(imports) != 1 or '</script' in engine.lower():
    raise SystemExit('Expected one safe topography module import block')
html = html.replace(imports, engine + '\nconst topoParams = ' + json.dumps(params) + ';')
link = '<link rel="stylesheet" href="../dist/tokens.css">'
if html.count(link) != 1:
    raise SystemExit('Expected one generated stylesheet link; refusing ambiguous export')
output = Path(sys.argv[1]).expanduser().resolve()
if output == root / 'catalog.html':
    raise SystemExit('Export must not overwrite the source catalogue')
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(html.replace(link, '<!-- Generated offline preview; edit the kit source instead. -->\n<style>\n'+css+'\n</style>'))
print(output)
