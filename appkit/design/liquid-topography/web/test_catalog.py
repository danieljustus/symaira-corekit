"""Catalogue browser checks; requires installed Playwright/Chromium.

Run against a local kit server; no backend or production site is contacted.
"""
import json
import os
import sys
from playwright.sync_api import sync_playwright

URL = os.environ.get("CATALOG_URL", "http://127.0.0.1:8765/web/catalog.html")
results = []

def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f" :: {detail}" if detail else ""), flush=True)

def run(p):
    browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_EXECUTABLE"),
                                args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    errors = []

    # ---------- Desktop ----------
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, color_scheme="light")
    page = ctx.new_page()
    page.add_init_script("""window.topoDraws=0;
        const locations=new WeakMap();
        const locate=WebGL2RenderingContext.prototype.getUniformLocation;
        WebGL2RenderingContext.prototype.getUniformLocation=function(program,name){
            const location=locate.call(this,program,name);
            if(location) locations.set(location,name);
            return location;
        };
        const setRects=WebGL2RenderingContext.prototype.uniform4fv;
        WebGL2RenderingContext.prototype.uniform4fv=function(location,values,...rest){
            if(locations.get(location)==='R') window.topoRects=Array.from(values);
            return setRects.call(this,location,values,...rest);
        };
        const draw=WebGL2RenderingContext.prototype.drawArrays;
        WebGL2RenderingContext.prototype.drawArrays=function(...args){
            window.topoDraws++; return draw.apply(this,args);
        };""")
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    page.goto(URL, wait_until="load")
    page.wait_for_timeout(300)

    check("desktop: page title DEMO", "DEMO" in page.title())
    check("topography: real WebGL renderer ready", page.get_attribute('html', 'data-topography') == 'ready')
    check("topography: canvas has rendered", page.evaluate('topoDraws > 0'))
    text_mask = page.evaluate("""(() => {
        const element=document.getElementById('topo-status');
        const range=document.createRange(); range.selectNodeContents(element);
        const text=range.getBoundingClientRect(), block=element.getBoundingClientRect();
        const host=document.getElementById('topo-background').getBoundingClientRect();
        const expected=[text.x-host.x-4,text.y-host.y-4,text.width+8,text.height+8];
        const values=window.topoRects || [];
        let found=false;
        for(let i=0;i<values.length;i+=4)
            if(expected.every((value,j)=>Math.abs(value-values[i+j])<0.1)) found=true;
        return {found,maskWidth:expected[2],blockWidth:block.width};
    })()""")
    check("topography: status mask follows text, not full paragraph width",
          text_mask['found'] and text_mask['maskWidth'] < text_mask['blockWidth'], json.dumps(text_mask))
    check("desktop: tokens.css loaded (canvas var set)",
          page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--sym-canvas').trim()") == "#EEEDEA")
    check("desktop: body type from .sym-type-* not required; body font resolves",
          page.evaluate("getComputedStyle(document.body).fontFamily").strip() != "")
    page.evaluate("document.fonts.ready")
    check("type: Google Sans Flex loaded from the bundled original file",
          page.evaluate("document.fonts.check('600 13px \\\"Google Sans Flex\\\"') && [...document.fonts].some(f=>f.family.includes('Google Sans Flex') && f.status==='loaded')"))
    check("type: fixed optical size opsz 18 on body text",
          page.evaluate("(()=>{const s=getComputedStyle(document.querySelector('.hint')||document.body);return s.fontOpticalSizing==='none'&&s.fontVariationSettings.replace(/\\s/g,'')===\"\\\"opsz\\\"18\"})()"))
    check("desktop: no horizontal overflow", page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))

    # Theme toggle
    bg_light = page.evaluate("getComputedStyle(document.body).backgroundColor")
    check("theme: starts light (aria-pressed=false)", page.get_attribute("#theme-toggle", "aria-pressed") == "false")
    page.click("#theme-toggle")
    bg_dark = page.evaluate("getComputedStyle(document.body).backgroundColor")
    check("theme: toggle -> dark data-theme", page.evaluate("document.documentElement.dataset.theme") == "dark")
    check("theme: toggle -> aria-pressed=true", page.get_attribute("#theme-toggle", "aria-pressed") == "true")
    check("theme: background actually changes", bg_light != bg_dark, f"{bg_light} -> {bg_dark}")
    page.click("#theme-toggle")
    check("theme: toggle back -> light", page.evaluate("document.documentElement.dataset.theme") == "light")

    # Buttons: loading state
    page.click("#load-demo")
    check("btn loading: aria-disabled + aria-busy set", page.get_attribute("#load-demo", "aria-disabled") == "true"
          and page.get_attribute("#load-demo", "aria-busy") == "true")
    page.click("#load-demo", force=True)  # deliver the click while aria-disabled, rather than waiting for it to end
    page.wait_for_timeout(1800)
    check("btn loading: restores label", page.inner_text("#load-demo").strip() == "Speichern (Demo, 1,5 s)",
          page.inner_text("#load-demo"))
    check("btn loading: aria-disabled removed", page.get_attribute("#load-demo", "aria-disabled") is None)
    check("btn loading: demo status text", "nichts gespeichert" in page.inner_text("#load-status"))

    # Disabled button really disabled
    check("btn disabled: native disabled", page.is_disabled("button:has-text('Deaktiviert')"))

    # Form validation: submit empty
    page.click("#f-submit")
    page.wait_for_timeout(100)
    check("form: alert summary visible on empty submit", page.is_visible("#form-summary"))
    check("form: summary lists 3 errors", page.locator("#form-summary-list li").count() == 3,
          str(page.locator("#form-summary-list li").count()))
    check("form: focus moved to first invalid field",
          page.evaluate("document.activeElement.id") == "f-projekt")
    check("form: aria-invalid set on projekt", page.get_attribute("#f-projekt", "aria-invalid") == "true")
    check("form: error text visible", page.is_visible("#f-projekt-err"))
    check("form: describedby includes error id",
          "f-projekt-err" in (page.get_attribute("#f-projekt", "aria-describedby") or ""))

    # Blur validation: bad email
    page.fill("#f-projekt", "Ok Projekt")
    page.evaluate("document.getElementById('f-projekt').blur()")
    check("form: projekt valid -> aria-invalid=false", page.get_attribute("#f-projekt", "aria-invalid") == "false")
    page.fill("#f-email", "kein-mail")
    page.evaluate("document.getElementById('f-email').blur()")
    check("form: bad email -> error text", "name@beispiel.de" in page.inner_text("#f-email-err"),
          page.inner_text("#f-email-err"))
    page.fill("#f-kontingent", "150")
    page.evaluate("document.getElementById('f-kontingent').blur()")
    check("form: kontingent 150 rejected", "1 bis 100" in page.inner_text("#f-kontingent-err"))
    page.fill("#f-kontingent", "7")
    page.fill("#f-email", "a@b.de")
    page.evaluate("document.getElementById('f-kontingent').blur()")
    page.evaluate("document.getElementById('f-email').blur()")
    page.click("#f-submit")
    page.wait_for_timeout(100)
    check("form: valid submit shows busy", page.get_attribute("#f-submit", "aria-busy") == "true")
    page.wait_for_timeout(1200)
    check("form: valid submit -> demo status", "nichts gesendet" in page.inner_text("#form-status"))
    check("form: summary hidden after valid submit", not page.is_visible("#form-summary"))

    # Table: sort + filter + empty + error
    def first_names():
        return page.locator("#t-body tr td.name").all_inner_texts()
    base = first_names()
    check("table: default rows 8", len(base) == 8, str(len(base)))
    check("table: default sort aktualisiert desc (first is Brain Wissensbasis 14.10.)",
          base[0] == "Brain · Wissensbasis", base[0])
    page.click("button.sort[data-key='name']")
    check("table: name click -> aria-sort ascending",
          page.get_attribute("th:has(button[data-key='name'])", "aria-sort") == "ascending")
    asc = first_names()
    check("table: name asc order", asc == sorted(asc, key=lambda s: s.lower()), str(asc[:2]))
    page.click("button.sort[data-key='name']")
    check("table: second click -> descending", page.get_attribute("th:has(button[data-key='name'])", "aria-sort") == "descending")
    page.click("button.sort[data-key='eintraege']")
    nums = [int(x.replace('.', '')) for x in page.locator("#t-body tr td.num").all_inner_texts()]
    check("table: numeric sort first click desc", nums == sorted(nums, reverse=True), str(nums))
    # filter by text
    page.fill("#t-q", "brain")
    check("table: search brain -> 2 rows", page.locator("#t-body tr").count() == 2)
    check("table: live count text", "2 von 8" in page.inner_text("#t-count"), page.inner_text("#t-count"))
    page.fill("#t-q", "")
    page.select_option("#t-status", "fehlgeschlagen")
    check("table: status filter fehlgeschlagen -> 2", page.locator("#t-body tr").count() == 2)
    page.fill("#t-q", "zzz-nichts")
    check("table: no hits -> empty state visible", page.is_visible("#t-empty") and not page.is_visible("#t-wrap"))
    check("table: empty title Keine Treffer", page.inner_text("#t-empty-title") == "Keine Treffer")
    page.click("#t-reset")
    check("table: reset restores 8 rows", page.locator("#t-body tr").count() == 8)
    check("table: reset moves focus to search", page.evaluate("document.activeElement.id") == "t-q")
    page.select_option("#t-data", "empty")
    check("table: data=empty -> empty state 'Noch keine Einträge'",
          page.inner_text("#t-empty-title") == "Noch keine Einträge" and page.is_visible("#t-empty"))
    page.select_option("#t-data", "error")
    check("table: data=error -> alert + table hidden", page.is_visible("#t-error") and not page.is_visible("#t-wrap"))
    page.click("#t-retry")
    page.wait_for_timeout(1200)
    check("table: retry restores normal", page.locator("#t-body tr").count() == 8 and page.is_visible("#t-wrap"))
    check("table: data select back to normal", page.input_value("#t-data") == "normal")

    # Keyboard: sort via keyboard focus Enter
    page.focus("button.sort[data-key='typ']")
    page.keyboard.press("Enter")
    check("table: keyboard Enter sorts typ",
          page.get_attribute("th:has(button[data-key='typ'])", "aria-sort") == "ascending")

    # Menu
    page.focus("#menu-btn")
    page.keyboard.press("Enter")
    check("menu: Enter opens, focus on first item", page.is_visible("#menu") and
          page.evaluate("document.activeElement.textContent.trim()") == "Umbenennen")
    check("menu: aria-expanded true", page.get_attribute("#menu-btn", "aria-expanded") == "true")
    page.keyboard.press("ArrowDown")
    check("menu: ArrowDown -> Duplizieren", page.evaluate("document.activeElement.textContent.trim()") == "Duplizieren")
    page.keyboard.press("ArrowDown")
    check("menu: ArrowDown skips disabled -> Löschen", page.evaluate("document.activeElement.textContent.trim()") == "Löschen…")
    page.keyboard.press("ArrowDown")
    check("menu: wrap to first", page.evaluate("document.activeElement.textContent.trim()") == "Umbenennen")
    page.keyboard.press("End")
    check("menu: End -> last", page.evaluate("document.activeElement.textContent.trim()") == "Löschen…")
    page.keyboard.press("Escape")
    check("menu: Escape closes + restores focus", not page.is_visible("#menu") and
          page.evaluate("document.activeElement.id") == "menu-btn")
    page.keyboard.press("ArrowDown")  # on focused button opens menu first
    check("menu: ArrowDown on button opens", page.is_visible("#menu"))
    page.keyboard.press("Tab")
    check("menu: Tab closes menu", not page.is_visible("#menu"))
    page.focus("#menu-btn")
    page.keyboard.press("Enter")
    page.click("[data-action='duplicate']")
    check("menu: item click -> demo status", "nichts kopiert" in page.inner_text("#menu-status"))
    check("menu: closed after click", not page.is_visible("#menu"))

    # Dialog: open -> cancel focus, Escape closes, focus returns
    page.focus("#open-dialog")
    page.keyboard.press("Enter")
    check("dialog: opens modal", page.evaluate("document.getElementById('confirm').open") is True)
    check("dialog: initial focus on Abbrechen (safe)", page.evaluate("document.activeElement.textContent.trim()") == "Abbrechen",
          page.evaluate("document.activeElement.textContent.trim()"))
    page.keyboard.press("Tab")
    check("dialog: Tab stays in dialog (focus on Löschen)",
          page.evaluate("document.activeElement.textContent.trim()") == "Löschen (Demo)")
    page.keyboard.press("Tab")
    check("dialog: focus trap wraps to Abbrechen",
          page.evaluate("document.activeElement.textContent.trim()") == "Abbrechen")
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    check("dialog: Escape closes", page.evaluate("document.getElementById('confirm').open") is False)
    check("dialog: Escape -> cancelled status", "Abgebrochen" in page.inner_text("#dialog-status"))
    check("dialog: focus returned to opener", page.evaluate("document.activeElement.id") == "open-dialog")
    page.keyboard.press("Enter")
    page.click("#confirm button[value='confirm']")
    page.wait_for_timeout(200)
    check("dialog: confirm -> demo status, nothing deleted",
          "Bestätigt" in page.inner_text("#dialog-status") and "nichts gelöscht" in page.inner_text("#dialog-status"))

    # Settings
    page.click("label.setting:has-text('Bewegung reduzieren')")
    check("settings: motion switch -> force-reduce class",
          page.evaluate("document.documentElement.classList.contains('force-reduce')"))
    check("settings: switch state text Ein", page.inner_text("#s-motion-state") == "Ein")
    page.wait_for_timeout(250)
    draws = page.evaluate('topoDraws')
    page.wait_for_timeout(400)
    check("settings: reduced motion also pauses topography", page.evaluate('topoDraws') == draws)
    page.click("label.setting:has-text('Bewegung reduzieren')")
    check("settings: motion off -> class removed", not page.evaluate("document.documentElement.classList.contains('force-reduce')"))
    page.wait_for_timeout(250)
    check("settings: topography resumes", page.evaluate('topoDraws') > draws)
    page.click("label.choice:has-text('Kompakt')")
    check("settings: density kompakt -> table class", page.evaluate("document.getElementById('t-wrap').classList.contains('is-compact')"))

    page.click("#settings button[type='submit']")
    check("settings: submit -> nicht gespeichert status", "nicht gespeichert" in page.inner_text("#settings-status"))

    # States
    page.click("#retry-demo")
    page.wait_for_timeout(1200)
    check("states: retry -> demo status", "Erneut versucht" in page.inner_text("#states-status"))
    page.click("#empty-demo")
    check("states: empty action -> demo status", "nichts angelegt" in page.inner_text("#states-status"))

    # Keyboard focus ring on a button
    page.keyboard.press("Tab")
    page.focus("#theme-toggle")
    page.keyboard.press("Tab")
    focus_style = page.evaluate("""(() => { const e = document.activeElement; const s = getComputedStyle(e);
        return {tag: e.tagName, outline: s.outlineStyle + ' ' + s.outlineWidth + ' ' + s.outlineColor}; })()""")
    check("focus: visible focus ring present on Tab", focus_style["outline"].startswith("solid"), json.dumps(focus_style))

    # Contrast check of key pairs in computed colors (light + dark)
    def contrast_pairs(theme):
        page.evaluate(f"document.documentElement.dataset.theme = '{theme}'")
        return page.evaluate("""(() => {
          const v = n => getComputedStyle(document.documentElement).getPropertyValue('--sym-' + n).trim();
          const parse = h => [1,3,5].map(i => parseInt(h.substr(i,2),16)/255).map(c => c<=0.03928? c/12.92 : Math.pow((c+0.055)/1.055,2.4));
          const L = h => { const c = parse(h); return 0.2126*c[0]+0.7152*c[1]+0.0722*c[2]; };
          const R = (a,b) => { const x=L(a), y=L(b); return (Math.max(x,y)+0.05)/(Math.min(x,y)+0.05); };
          return {ink_canvas: R(v('ink'), v('canvas')), ink2_surface: R(v('ink-2'), v('surface')),
                  ink3_surface: R(v('ink-3'), v('surface')), critical_surface: R(v('critical'), v('surface')),
                  positive_surface: R(v('positive'), v('surface')),
                  oncritical_critical: R(v('on-critical'), v('critical')),
                  onprimary_primary: R(v('on-primary'), v('primary')),
                  onselected_selected: R(v('on-selected'), v('selected'))};
        })()""")
    light = contrast_pairs("light")
    dark = contrast_pairs("dark")
    page.evaluate("delete document.documentElement.dataset.theme")
    for k, val in light.items():
        check(f"contrast light {k} >= 4.5", val >= 4.5, f"{val:.2f}")
    for k, val in dark.items():
        check(f"contrast dark {k} >= 4.5", val >= 4.5, f"{val:.2f}")

    # Visible tap-target minimum at desktop (32px rule for mouse, we use 40)
    small = page.evaluate("""[...document.querySelectorAll('button, a, input, select, textarea')]
        .filter(e => e.offsetParent !== null && !e.closest('[hidden]') && !e.classList.contains('sr-only'))
        .map(e => { const t = (e.tagName === 'INPUT' && e.closest('label')) ? e.closest('label') : e;
                    return [t.tagName + '#' + (t.id || t.className), t.getBoundingClientRect().height]; })
        .filter(([, h]) => h < 32 && h > 0)""")
    check("desktop: interactive hit areas >= 32px high (inputs measured via wrapping label)", len(small) == 0, json.dumps(small[:6]))

    check("desktop: no page errors", not [e for e in errors if "pageerror" in e or "console.error" in e],
          json.dumps(errors[:5]))
    ctx.close()

    # ---------- Mobile 390 ----------
    mctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, color_scheme="light")
    m = mctx.new_page()
    merrors = []
    m.on("pageerror", lambda e: merrors.append(str(e)))
    m.on("console", lambda msg: merrors.append(msg.text) if msg.type == "error" else None)
    m.goto(URL, wait_until="load")
    m.wait_for_timeout(300)
    sw = m.evaluate("document.documentElement.scrollWidth")
    check("mobile 390: no page-level horizontal overflow", sw <= 390, f"scrollWidth={sw}")
    check("mobile 390: sidebar stacks above content", m.evaluate("getComputedStyle(document.querySelector('.layout')).gridTemplateColumns.split(' ').length") == 1)
    check("mobile 390: nav is horizontal scroller", m.evaluate("getComputedStyle(document.querySelector('.navlist')).display") == "flex")
    tbl = m.evaluate("""(() => { const w = document.getElementById('t-wrap'); return {sw: w.scrollWidth, cw: w.clientWidth}; })()""")
    check("mobile 390: table scrolls inside own wrapper", tbl["sw"] > tbl["cw"], json.dumps(tbl))
    small_m = m.evaluate("""[...document.querySelectorAll('button, a, input, select, textarea')]
        .filter(e => e.offsetParent !== null && !e.closest('[hidden]') && !e.classList.contains('sr-only') && !e.classList.contains('skip'))
        .map(e => { const t = (e.tagName === 'INPUT' && e.closest('label')) ? e.closest('label') : e;
                    return [t.tagName + '#' + (t.id || t.className) + ' ' + (t.textContent||'').trim().slice(0,20), t.getBoundingClientRect().height]; })
        .filter(([, h]) => h < 44 && h > 0)""")
    check("mobile 390: interactive targets >= 44px", len(small_m) == 0, json.dumps(small_m[:8]))
    m.click("#theme-toggle")
    check("mobile 390: theme toggle works", m.get_attribute("#theme-toggle", "aria-pressed") == "true")
    m.evaluate("document.getElementById('demo-form').scrollIntoView()")
    m.click("#f-submit")
    m.wait_for_timeout(100)
    check("mobile 390: form error summary visible", m.is_visible("#form-summary"))
    m.evaluate("document.getElementById('menu-btn').scrollIntoView()")
    m.click("#menu-btn")
    check("mobile 390: menu opens and fits", m.is_visible("#menu") and
          m.evaluate("(() => { const r = document.getElementById('menu').getBoundingClientRect(); return r.right <= window.innerWidth + 1 && r.left >= -1; })()"))
    m.keyboard.press("Escape")
    m.evaluate("document.getElementById('open-dialog').scrollIntoView()")
    m.click("#open-dialog")
    dialog_w = m.evaluate("document.getElementById('confirm').getBoundingClientRect().width")
    check("mobile 390: dialog fits viewport", dialog_w <= 390, f"width={dialog_w}")
    m.keyboard.press("Escape")
    check("mobile 390: no page errors", not merrors, json.dumps(merrors[:5]))
    mctx.close()

    # ---------- Reduced motion preference via OS ----------
    rctx = browser.new_context(viewport={"width": 1280, "height": 900}, reduced_motion="reduce")
    r = rctx.new_page()
    r.goto(URL, wait_until="load")
    r.wait_for_timeout(200)
    dur = r.evaluate("getComputedStyle(document.querySelector('.spinner')).animationDuration")
    check("reduced-motion OS: spinner animation effectively disabled", float(dur.rstrip('s')) <= 0.01, dur)
    check("reduced-motion OS: media query matches", r.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches"))
    rctx.close()

    # ---------- Dark system color scheme ----------
    dctx = browser.new_context(viewport={"width": 1280, "height": 900}, color_scheme="dark")
    d = dctx.new_page()
    d.goto(URL, wait_until="load")
    check("system dark: aria-pressed true", d.get_attribute("#theme-toggle", "aria-pressed") == "true")
    check("system dark: canvas token dark",
          d.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(28, 28, 27)")
    dctx.close()

    browser.close()

if __name__ == "__main__":
    with sync_playwright() as p:
        run(p)
    failed = [r for r in results if not r[1]]
    print(f"\nTOTAL {len(results)}  PASS {len(results)-len(failed)}  FAIL {len(failed)}")
    for n, _, d in failed:
        print("  FAILED:", n, d)
    sys.exit(1 if failed else 0)
