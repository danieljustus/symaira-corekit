#!/usr/bin/env python3
"""Build the selection board: Apple screenshots (macOS + iPhone) next to live web variants.

Run with Pillow:  uv run --no-project --with pillow python -I board.py
Inputs : elements.json, selection.json, web/variants.{html,css}, liquid-topography tokens + Figtree,
         $UI_CATALOG_BUILD/shots/{mac,ios}/{light,dark}/*.png (from capture.py)
Output : $UI_CATALOG_BUILD/board.html (self-contained; images embedded as JPEG)
"""
import base64, html, io, json, os, re
from pathlib import Path
from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
BUILD = Path(os.environ.get("UI_CATALOG_BUILD", "/Volumes/1TB_NVMe_SN850X/Dev/Symaira_Dev/builds/symaira-corekit/ui-catalog"))
SHOTS = BUILD / "shots"
TOKENS = HERE.parent / "liquid-topography/dist/tokens.css"
FIGTREE = HERE.parents[1] / "Sources/SymairaTheme/Resources/Fonts/Figtree.ttf"


def trim(img):
    """Cut the uniform background below the content (keeps a small margin)."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    bg = Image.new("RGB", rgb.size, rgb.getpixel((w // 2, h - 3)))
    mask = ImageChops.difference(rgb, bg).convert("L").point(lambda v: 255 if v > 24 else 0)
    box = mask.crop((48, 0, w - 48, h)).getbbox()
    last = box[3] if box else h
    return rgb.crop((0, 0, w, min(h, last + 40)))


def jpeg(path, width, crop_top=0):
    img = Image.open(path)
    if crop_top:
        img = img.crop((0, crop_top, img.width, img.height))
    img = trim(img)
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=70, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def blank(path):
    lo, hi = Image.open(path).convert("RGB").convert("L").getextrema()
    return hi - lo < 8


def shot(platform, appearance, name, width, crop_top=0):
    p = SHOTS / platform / appearance / name
    if not p.exists() or blank(p):  # macOS alert windows stay blank while the app is in the background
        return None
    return jpeg(p, width, crop_top)


def main():
    data = json.loads((HERE / "elements.json").read_text())
    elements = data["elements"]
    sel_path = HERE / "selection.json"
    selection = json.loads(sel_path.read_text()) if sel_path.exists() else {}
    selection = {k: {"apple": v.get("apple"), "web": v.get("web")} for k, v in selection.get("elements", selection).items()}
    templates = dict(re.findall(r'<template data-v="([^"]+)">(.*?)</template>', (HERE / "web/variants.html").read_text(), re.S))
    css = (HERE / "web/variants.css").read_text()
    tokens = TOKENS.read_text()
    font = base64.b64encode(FIGTREE.read_bytes()).decode()

    stats = {"mac": 0, "ios": 0}
    sections = []
    for el in elements:
        eid = el["id"]
        imgs = {}
        for ap in ("light", "dark"):
            mac = []
            names = [f"{eid}.png"] if not el["modal"] else [f"{eid}_{v['id']}.png" for v in el["apple"]]
            for n in names:
                src = shot("mac", ap, n, 1100)
                if src:
                    stats["mac"] += ap == "light"
                    sheet = shot("mac", ap, n.replace(".png", "_sheet.png"), 560)
                    mac.append((n[:-4], src, sheet))
            ios = []
            for v in el["apple"]:
                src = shot("ios", ap, f"{eid}_{v['id']}.png", 420, crop_top=170)
                if src:
                    stats["ios"] += ap == "light"
                ios.append((v["id"], src))
            imgs[ap] = (mac, ios)

        def mac_html(ap):
            mac, _ = imgs[ap]
            if not mac:
                return '<p class="missing">Noch keine macOS-Aufnahme</p>'
            out = []
            if el["modal"]:
                out.append('<p class="note">macOS-Dialoge werden im Hintergrund aufgenommen; Alerts zeichnet AppKit dabei nicht. '
                           'Alert und Confirmation Dialog: siehe iPhone oder live in der Katalog-App.</p>')
            for name, src, sheet in mac:
                cap = f"Variante {name.split('_')[1]}" if "_" in name else ""
                out.append(f'<figure><img src="{src}" alt="macOS {html.escape(name)}">'
                           + (f'<img class="sheet" src="{sheet}" alt="Dialog {html.escape(name)}">' if sheet else "")
                           + (f"<figcaption>{cap}{' · Dialog separat aufgenommen' if sheet else ''}</figcaption>" if cap else "") + "</figure>")
            return "".join(out)

        def ios_html(ap):
            _, ios = imgs[ap]
            cells = []
            for vid, src in ios:
                body = f'<img src="{src}" alt="iPhone {eid} {vid}">' if src else '<p class="missing">fehlt</p>'
                cells.append(f'<figure class="phone"><figcaption>{vid}</figcaption>{body}</figure>')
            return "".join(cells)

        def chips(kind, variants):
            current = selection.get(eid, {}).get(kind)
            out = []
            for v in variants + [{"id": "Out", "title": "Element nicht nötig"}]:
                on = " on" if current == v["id"] else ""
                out.append(f'<button class="chip{on}" data-el="{eid}" data-kind="{kind}" data-v="{v["id"]}" title="{html.escape(v["title"])}">'
                           f'<b>{v["id"]}</b> {html.escape(v["title"])}</button>')
            return "".join(out)

        web_cards = []
        for v in el["web"]:
            tpl = templates.get(f"{eid}-{v['id']}", '<p class="missing">Vorlage fehlt</p>')
            web_cards.append(f'<div class="wcard"><div class="whead"><b>{v["id"]}</b> {html.escape(v["title"])}'
                             f'<code>{html.escape(v["code"])}</code></div><div class="wdemo">{tpl}</div></div>')

        apple_list = "".join(f'<li><b>{v["id"]}</b> {html.escape(v["title"])} <code>{html.escape(v["code"])}</code></li>' for v in el["apple"])
        sections.append(f'''
<section class="el" id="{eid}" data-group="{html.escape(el["group"])}">
  <header><span class="eid">{eid}</span><h2>{html.escape(el["title"])}</h2><span class="job">{html.escape(el["job"])}</span></header>
  <div class="cols">
    <div class="apple">
      <h3>Apple</h3>
      <ul class="vlist">{apple_list}</ul>
      <div class="tabs" role="tablist"><button class="tab on" data-p="mac">macOS</button><button class="tab" data-p="ios">iPhone</button></div>
      <div class="pane mac" data-ap="light">{mac_html("light")}</div>
      <div class="pane mac" data-ap="dark">{mac_html("dark")}</div>
      <div class="pane ios" data-ap="light" hidden><div class="phones">{ios_html("light")}</div></div>
      <div class="pane ios" data-ap="dark" hidden><div class="phones">{ios_html("dark")}</div></div>
      <div class="chips">{chips("apple", el["apple"])}</div>
    </div>
    <div class="web">
      <h3>Web</h3>
      <div class="wgrid">{"".join(web_cards)}</div>
      <div class="chips">{chips("web", el["web"])}</div>
    </div>
  </div>
</section>''')

    groups = []
    for el in elements:
        if el["group"] not in groups:
            groups.append(el["group"])
    nav = "".join(f'<a href="#{e["id"]}" data-nav="{e["id"]}"><span>{e["id"]}</span> {html.escape(e["title"])}</a>' for e in elements)
    page = f'''<!doctype html>
<html lang="de" data-theme="light"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Symaira UI-Katalog: Auswahl</title>
<style>@font-face{{font-family:"Figtree";src:url(data:font/ttf;base64,{font}) format("truetype");font-weight:300 900}}</style>
<style>{tokens}</style>
<style>
body{{margin:0;background:var(--sym-canvas);color:var(--sym-ink);font:450 14px/1.5 var(--sym-font-text)}}
.top{{position:sticky;top:0;z-index:5;background:var(--sym-canvas);border-bottom:1px solid var(--sym-line);padding:10px 20px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}}
.top h1{{font:700 17px/1.2 var(--sym-font-text);margin:0}}
.top .sp{{flex:1}}
.top button,.top select{{font:600 13px var(--sym-font-text);padding:6px 12px;border-radius:10px;border:1px solid var(--sym-line);background:var(--sym-surface);color:var(--sym-ink);cursor:pointer}}
.top .send{{background:var(--sym-ink);color:var(--sym-surface);border-color:transparent}}
.legend{{padding:12px 20px;color:var(--sym-ink-2);font-size:13px;max-width:1100px}}
.legend b{{color:var(--sym-ink)}}
main{{padding:0 20px 120px;display:grid;gap:22px}}
.el{{background:var(--sym-surface);border:1px solid var(--sym-line);border-radius:16px;padding:16px 18px;scroll-margin-top:70px}}
.el header{{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;margin-bottom:10px}}
.el h2{{margin:0;font:700 18px/1.2 var(--sym-font-text)}}
.eid{{font:600 12px var(--sym-font-mono);background:var(--sym-raised);border:1px solid var(--sym-line);border-radius:6px;padding:1px 6px}}
.job{{color:var(--sym-ink-2)}}
.cols{{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:18px}}
@media (max-width:900px){{.cols{{grid-template-columns:minmax(0,1fr)}}}}
h3{{margin:0 0 6px;font:700 12px var(--sym-font-text);text-transform:uppercase;letter-spacing:.06em;color:var(--sym-ink-3)}}
.vlist{{margin:0 0 8px;padding:0;list-style:none;font-size:12.5px;color:var(--sym-ink-2);display:grid;gap:2px}}
.vlist code,.whead code{{font:500 11px var(--sym-font-mono);color:var(--sym-ink-3);margin-left:6px}}
.tabs{{display:inline-flex;gap:4px;padding:3px;background:var(--sym-raised);border-radius:10px;margin-bottom:8px}}
.tab{{border:0;background:none;padding:4px 12px;border-radius:8px;font:600 12.5px var(--sym-font-text);color:var(--sym-ink-2);cursor:pointer}}
.tab.on{{background:var(--sym-selected);color:var(--sym-on-selected)}}
figure{{margin:0 0 8px}}
figure img{{max-width:100%;border-radius:10px;border:1px solid var(--sym-line);display:block}}
figure img.sheet{{max-width:60%;margin-top:6px}}
figcaption{{font-size:12px;color:var(--sym-ink-3);margin:2px 0}}
.phones{{display:flex;gap:10px;overflow-x:auto;padding-bottom:6px}}
.phone{{flex:0 0 210px}}
.phone figcaption{{font-weight:700;color:var(--sym-ink)}}
.missing{{color:var(--sym-ink-3);font-style:italic;font-size:12.5px}}
.note{{font-size:12px;color:var(--sym-warning);margin:0 0 6px}}
.wgrid{{display:grid;gap:10px}}
.wcard{{border:1px solid var(--sym-line);border-radius:12px;overflow:hidden;background:var(--sym-canvas)}}
.whead{{padding:6px 10px;font-size:12.5px;border-bottom:1px solid var(--sym-line);background:var(--sym-surface)}}
.wdemo{{padding:14px}}
.chips{{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}}
.chip{{font:500 12.5px var(--sym-font-text);padding:5px 10px;border-radius:999px;border:1px solid var(--sym-line);background:var(--sym-canvas);color:var(--sym-ink);cursor:pointer}}
.chip b{{font-weight:800}}
.chip.on{{background:var(--sym-selected);color:var(--sym-on-selected);border-color:transparent}}
.chip:focus-visible,.tab:focus-visible,.top button:focus-visible{{outline:2px solid var(--sym-focus);outline-offset:2px}}
.el.done{{border-color:var(--sym-ink-3)}}
nav.idx{{display:flex;flex-wrap:wrap;gap:4px 10px;padding:0 20px 12px;font-size:12.5px}}
nav.idx a{{color:var(--sym-ink-2);text-decoration:none}}
nav.idx a.done{{color:var(--sym-ink);font-weight:700}}
nav.idx a.done::after{{content:" ✓"}}
nav.idx span{{font-family:var(--sym-font-mono);font-size:11px}}
</style></head><body>
<div class="top">
  <h1>Symaira UI-Katalog</h1>
  <span id="count">0 / {len(elements)} entschieden</span>
  <select id="grp" aria-label="Gruppe"><option value="">Alle Gruppen</option>{"".join(f"<option>{html.escape(g)}</option>" for g in groups)}</select>
  <button id="theme">Dunkel zeigen</button>
  <span class="sp"></span>
  <button id="copy">Auswahl kopieren</button>
  <button id="send" class="send">Auswahl senden</button>
</div>
<p class="legend">Pro Element je eine <b>Apple</b>- und eine <b>Web</b>-Variante wählen, oder <b>Out</b>, wenn Symaira das Element nicht braucht.
Apple-Bilder sind echte Aufnahmen (macOS-Fenster, iPhone-17-Simulator, iOS/macOS 27). Web-Varianten sind live.
Buchstaben: A/B/C/D Apple, W1 Browser-nativ, W2 natives Element mit Symaira-Tokens, W3 Eigenbau. Die Auswahl bleibt im Browser gespeichert.</p>
<nav class="idx">{nav}</nav>
<main>{"".join(sections)}</main>
<script>
const KEY="symaira-ui-catalog-selection";
const initial={json.dumps(selection)};
let sel=Object.assign({{}},initial,JSON.parse(localStorage.getItem(KEY)||"{{}}"));
const total={len(elements)};
function paint(){{
  document.querySelectorAll(".chip").forEach(c=>c.classList.toggle("on",(sel[c.dataset.el]||{{}})[c.dataset.kind]===c.dataset.v));
  let n=0;
  document.querySelectorAll(".el").forEach(s=>{{const d=sel[s.id]&&sel[s.id].apple&&sel[s.id].web;if(d)n++;s.classList.toggle("done",!!d);
    const a=document.querySelector(`[data-nav="${{s.id}}"]`);if(a)a.classList.toggle("done",!!d);}});
  document.getElementById("count").textContent=`${{n}} / ${{total}} entschieden`;
  localStorage.setItem(KEY,JSON.stringify(sel));
}}
document.addEventListener("click",e=>{{
  const c=e.target.closest(".chip");
  if(c){{const s=sel[c.dataset.el]||(sel[c.dataset.el]={{}});s[c.dataset.kind]=s[c.dataset.kind]===c.dataset.v?undefined:c.dataset.v;paint();return;}}
  const t=e.target.closest(".tab");
  if(t){{const box=t.closest(".apple");box.querySelectorAll(".tab").forEach(x=>x.classList.toggle("on",x===t));applyPanes(box);}}
}});
function applyPanes(box){{
  const p=box.querySelector(".tab.on").dataset.p, ap=document.documentElement.dataset.theme;
  box.querySelectorAll(".pane").forEach(x=>x.hidden=!(x.classList.contains(p)&&x.dataset.ap===ap));
}}
function allPanes(){{document.querySelectorAll(".apple").forEach(applyPanes);}}
document.getElementById("theme").onclick=e=>{{
  const r=document.documentElement;r.dataset.theme=r.dataset.theme==="dark"?"light":"dark";
  e.target.textContent=r.dataset.theme==="dark"?"Hell zeigen":"Dunkel zeigen";allPanes();
}};
document.getElementById("grp").onchange=e=>document.querySelectorAll(".el").forEach(s=>s.hidden=!!e.target.value&&s.dataset.group!==e.target.value);
function summary(){{
  const rows=Object.keys(sel).sort().filter(k=>sel[k]&&(sel[k].apple||sel[k].web)).map(k=>`${{k}} Apple=${{sel[k].apple||"?"}} Web=${{sel[k].web||"?"}}`);
  return "UI-Katalog Auswahl ("+rows.length+"/"+total+"): "+rows.join("; ");
}}
document.getElementById("copy").onclick=()=>navigator.clipboard.writeText(summary());
document.getElementById("send").onclick=()=>{{
  if(window.hermes&&window.hermes.send)window.hermes.send(summary());else navigator.clipboard.writeText(summary()).then(()=>alert("Nicht in Hermes: Auswahl in die Zwischenablage kopiert."));
}};
allPanes();paint();
</script></body></html>'''
    out = BUILD / "board.html"
    out.write_text(page)
    print(f"{out} {out.stat().st_size // 1024} KB, macOS-Aufnahmen hell {stats['mac']}, iPhone hell {stats['ios']}")


if __name__ == "__main__":
    main()
