// Symaira Liquid Topography – reaktive Topografie für das Web (WebGL2, keine Abhängigkeiten).
// Gleicher Algorithmus wie apple/SymairaTopo.metal. Parameter: ../topo.json
//
// Nutzung:
//   import { mountTopo } from "./symaira-topo.js";
//   const topo = mountTopo(document.querySelector(".app"), { params });   // params = topo.json
//   topo.setState("thinking");                 // idle | thinking | problem | input
//   topo.setState("input", askElement);        // Ringe laufen auf askElement zu
//   topo.ripple(element, 0.8);                 // GUI-Ereignis
// Markup: data-topo="protect" = Schutzzone (Text/Buttons), data-topo="hill" = Schutzzone + Hügel.
// Hintergrund hinter Seiteninhalt (position: fixed, pointer-events: none):
//   mountTopo(bg, { params, pointerTarget: window, root: document,
//                   protect: "h1, p, .button", hill: ".card" });

const VS = `#version 300 es
in vec2 p;void main(){gl_Position=vec4(p,0.,1.);}`;

const FS = `#version 300 es
precision highp float;
uniform vec2 res,mouse,askP;uniform float t,rt,dpr,k,mAmt,warp,think,prob,ask,tintA,scale,levels,lineA,idxA,bandA,maxA,basin,pR,pS,press,pD;
uniform vec3 col,tint;uniform vec4 R[20];uniform float K[20];uniform int NR;uniform vec4 RP[8];
out vec4 o;
float hash(vec3 p){p=fract(p*.3183099+.1);p*=17.;return fract(p.x*p.y*p.z*(p.x+p.y+p.z));}
float n3(vec3 x){vec3 i=floor(x),f=fract(x);f=f*f*(3.-2.*f);
 return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),f.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),
            mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),f.x),f.y),f.z);}
float fbm(vec3 p){return n3(p)*.62+n3(p*2.03+7.)*.26+n3(p*4.1+3.)*.12;}
float iso(float v,float w,float s){float f=fract(v),d=min(f,1.-f),a=fwidth(v);return 1.-smoothstep(a*max(w-s,0.),a*(w+s),d);}
float sdBox(vec2 p,vec4 r,float rad){vec2 c=r.xy+r.zw*.5;vec2 d=abs(p-c)-r.zw*.5+rad;return length(max(d,0.))+min(max(d.x,d.y),0.)-rad;}
void main(){
 vec2 px=gl_FragCoord.xy/dpr;px.y=res.y-px.y;
 vec2 dm=px-mouse;float md=length(dm);
 vec2 sp=px-dm*mAmt*pS*exp(-md*md/(pR*pR));
 vec2 q=sp/scale;
 vec2 w=vec2(fbm(vec3(q*.7,t*.6)),fbm(vec3(q*.7+5.2,t*.6)));
 float h=fbm(vec3(q+w*warp,t));
 h+=prob*.025*(n3(vec3(sp/26.,rt*.9))-.5);
 h-=press*pD*exp(-md*md/(pR*pR*1.6));
 float mask=1.,hill=0.;
 for(int i=0;i<20;i++){if(i>=NR)break;float sd=sdBox(px,R[i],12.);
  if(K[i]>.5)hill=max(hill,.025*exp(-max(sd,0.)/24.));
  mask=min(mask,smoothstep(2.,8.,sd));}
 h+=hill;
 for(int i=0;i<8;i++){vec4 r=RP[i];if(r.w<=0.)continue;float d=length(px-r.xy),front=r.z*180.;
  h+=r.w*.03*exp(-pow((d-front)/40.,2.))*exp(-r.z*1.2);}
 if(ask>0.){float d=length(px-askP);h+=ask*.025*sin(d/30.+rt*1.2)*exp(-d/380.);}
 float v=h*levels;
 float line=iso(v,.65*dpr,.5),idx=iso(v/5.,1.*dpr,1.6),band=floor(v)/levels;
 vec2 e=(px-vec2(res.x*.6,res.y*.55))/vec2(res.x*.36,res.y*.5);
 float vis=mix(1.,clamp((length(e)-.78)/.42,0.,1.),basin);
 float pulse=1.+think*.08*sin(rt*1.5);
 float a=min((max(line*lineA,idx*idxA)+band*bandA)*vis*pulse,maxA)*mask*k;
 vec3 c=mix(col,tint,tintA);
 o=vec4(c*a,a);
}`;

const KEYS = ["speed", "warp", "think", "problem", "ask", "tintAmount"];

export function mountTopo(host, {
  params,
  theme = () => host.closest("[data-theme]")?.dataset.theme,
  pointerTarget = host,          // window, wenn der Host hinter dem Inhalt liegt
  root = host,                   // Suchbereich für Schutzzonen
  protect = '[data-topo="protect"]',
  hill = '[data-topo="hill"]',
} = {}) {
  if (!params) throw new Error("mountTopo: params (topo.json) fehlen");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)");
  const cv = document.createElement("canvas");
  cv.setAttribute("aria-hidden", "true");
  Object.assign(cv.style, { position: "absolute", inset: "0", pointerEvents: "none", zIndex: "0" });
  if (getComputedStyle(host).position === "static") host.style.position = "relative";
  host.prepend(cv);
  const gl = cv.getContext("webgl2", { premultipliedAlpha: true, alpha: true, antialias: false });
  if (!gl) return { setState() {}, setMotionEnabled() {}, ripple() {}, destroy() { cv.remove(); }, supported: false };

  const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
  const prog = gl.createProgram();
  gl.attachShader(prog, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FS));
  gl.linkProgram(prog); gl.useProgram(prog);
  const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, "p"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const U = {};
  for (const n of ["res","mouse","askP","t","rt","dpr","k","mAmt","warp","think","prob","ask","tintA","scale","levels","lineA","idxA","bandA","maxA","basin","pR","pS","press","pD","col","tint","R","K","NR","RP"])
    U[n] = gl.getUniformLocation(prog, n);

  const css = (n) => getComputedStyle(host).getPropertyValue(n).trim();
  const hexRGB = (h) => { h = h.replace("#", ""); return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255); };
  const tintFor = (s) => s.tint === "none" ? hexRGB(css("--sym-topo")) : hexRGB(css(`--sym-${s.tint}`));

  let state = "idle", askEl = null, motionEnabled = true;
  const cur = Object.fromEntries(KEYS.map((k) => [k, params.states.idle[k]]));
  let tintCur = tintFor(params.states.idle);
  const rip = [], mouse = { x: -1e4, y: -1e4, tx: -1e4, ty: -1e4, amt: 0, tAmt: 0, vel: 0, down: false, press: 0, travel: 0 };
  const anchors = new WeakMap(), keyed = new Map(); let lastHost = null;
  let flowT = 0, rt = 0, last = 0, nextThink = 0, raf = null, alive = true;
  const RB = new Float32Array(80), KB = new Float32Array(20), PB = new Float32Array(32);

  const local = (x, y) => { const r = host.getBoundingClientRect(); return [x - r.left, y - r.top]; };
  const center = (el) => { const r = el.getBoundingClientRect(); return local(r.left + r.width / 2, r.top + r.height / 2); };
  function ripple(target, str = 1, key) {
    if (reduce.matches || !motionEnabled || !target) return;
    if (key) { const n = performance.now(); if (n - (keyed.get(key) || 0) < params.layout.rippleThrottleSeconds * 1000) return; keyed.set(key, n); }
    const [x, y] = target instanceof Element ? center(target) : target;
    rip.push({ x, y, age: 0, str }); if (rip.length > 8) rip.shift();
  }
  function setState(s, el) {
    if (!params.states[s]) throw new Error(`unbekannter Zustand ${s}`);
    state = s; askEl = el || null; host.dataset.topoState = s;
    const status = host.querySelector("[data-topo-status]"); if (status) ripple(status, 0.9);
    schedule();
  }
  const onMove = (e) => { const [x, y] = local(e.clientX, e.clientY);
    mouse.vel = Math.min(1, mouse.vel + Math.hypot(x - mouse.tx, y - mouse.ty) / 120);
    if (mouse.down) { mouse.travel += Math.hypot(x - mouse.tx, y - mouse.ty); if (mouse.travel > params.pointer.dragRippleEvery) { mouse.travel = 0; ripple([x, y], 0.35); } }
    mouse.tx = x; mouse.ty = y; if (mouse.x < -9e3) { mouse.x = x; mouse.y = y; } mouse.tAmt = 1; };
  const onLeave = () => { mouse.tAmt = 0; mouse.down = false; };
  const onDown = (e) => { mouse.down = true; mouse.travel = 0; ripple(local(e.clientX, e.clientY), params.pointer.clickRipple); };
  const onUp = () => { mouse.down = false; };
  addEventListener("pointerup", onUp); addEventListener("pointercancel", onUp);
  const leaveTarget = pointerTarget === window ? document.documentElement : pointerTarget;
  pointerTarget.addEventListener("pointermove", onMove); leaveTarget.addEventListener("pointerleave", onLeave); pointerTarget.addEventListener("pointerdown", onDown);

  function collect(hr) {
    let n = 0;
    let left = Infinity, topmost = Infinity, right = -Infinity, bottom = -Infinity;
    const limit = Math.min(20, params.maxProtectedRects);
    for (const el of root.querySelectorAll(`${protect}, ${hill}`)) {
      const isHill = el.matches(hill);
      let r = el.getBoundingClientRect();
      if (!isHill && el.matches('p,h1,h2,h3,h4,h5,h6,[data-topo="text"]')) {
        // Protect rendered text, not the block's full layout width or margins.
        // Multi-line text keeps one conservative bounding rectangle to avoid
        // exhausting the bounded shader budget with individual glyph fragments.
        const range = document.createRange();
        range.selectNodeContents(el);
        const text = range.getBoundingClientRect();
        if (!text.width || !text.height) continue;
        r = new DOMRect(text.x - 4, text.y - 4, text.width + 8, text.height + 8);
      }
      const an = anchors.get(el);
      if (!an) anchors.set(el, r);
      else if (Math.abs(an.x - r.x) + Math.abs(an.y - r.y) + Math.abs(an.width - r.width) + Math.abs(an.height - r.height) > params.layout.moveThreshold) {
        anchors.set(el, r); ripple(center(el), 0.6, el); }
      if (r.width < 1 || r.height < 1 || r.bottom < hr.top - 22 || r.top > hr.bottom + 22 ||
          r.right < hr.left - 22 || r.left > hr.right + 22) continue;
      left = Math.min(left, r.left); topmost = Math.min(topmost, r.top);
      right = Math.max(right, r.right); bottom = Math.max(bottom, r.bottom);
      if (n < limit) {
        RB.set([r.left - hr.left, r.top - hr.top, r.width, r.height], n * 4);
        KB[n] = isHill ? 1 : 0;
      }
      n++;
    }
    if (n > limit) {
      // Never leave the 21st element exposed: conservatively mask their union.
      RB.set([left - hr.left, topmost - hr.top, right - left, bottom - topmost]);
      KB[0] = 0;
      return 1;
    }
    return n;
  }

  function schedule() {
    if (alive && !document.hidden && raf === null) raf = requestAnimationFrame(frame);
  }
  function frame(ts) {
    raf = null;
    if (!alive || document.hidden) return;
    const still = reduce.matches || !motionEnabled, cap = 1000 / params.fps.web;
    if (!still && last && ts - last < cap - 1) { schedule(); return; }
    const dt = last ? Math.min(0.06, (ts - last) / 1000) : 0; last = ts;
    const tg = params.states[state], f = 1 - Math.exp(-dt / params.transitionSeconds);
    for (const key of KEYS) cur[key] += (tg[key] - cur[key]) * f;
    const tc = tintFor(tg); tintCur = tintCur.map((v, i) => v + (tc[i] - v) * f);
    if (!still) { flowT += cur.speed * dt; rt += dt; }
    const fm = 1 - Math.exp(-dt / 0.12);
    mouse.x += (mouse.tx - mouse.x) * fm; mouse.y += (mouse.ty - mouse.y) * fm;
    mouse.vel *= Math.exp(-dt / 0.5);
    mouse.press += ((still || !mouse.down ? 0 : 1) - mouse.press) * (1 - Math.exp(-dt / params.pointer.pressSeconds));
    mouse.amt += ((still ? 0 : mouse.tAmt * (0.45 + 0.55 * mouse.vel)) - mouse.amt) * (1 - Math.exp(-dt / 0.25));
    for (const r of rip) r.age += dt; while (rip.length && rip[0].age > 2.4) rip.shift();
    if (state === "thinking" && rt > nextThink) { ripple(host.querySelector("[data-topo-status]") || [0, 0], 0.8); nextThink = rt + tg.rippleEverySeconds; }

    const hr = host.getBoundingClientRect(), dpr = devicePixelRatio || 1;
    if (lastHost && Math.abs(lastHost.x - hr.x) + Math.abs(lastHost.width - hr.width) > 1) ripple([0, hr.height / 2], params.layout.edgeRipple, "layout.edge");
    lastHost = hr;
    const w = Math.round(hr.width * dpr), h = Math.round(hr.height * dpr);
    if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; cv.style.width = hr.width + "px"; cv.style.height = hr.height + "px"; }
    gl.viewport(0, 0, w, h); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
    const n = collect(hr); PB.fill(0); rip.forEach((r, i) => PB.set([r.x, r.y, r.age, r.str], i * 4));
    const ap = askEl ? center(askEl) : [hr.width / 2, hr.height - 60];
    const dark = (theme() || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")) === "dark";
    gl.uniform2f(U.res, hr.width, hr.height); gl.uniform2f(U.mouse, mouse.x, mouse.y); gl.uniform2f(U.askP, ...ap);
    gl.uniform1f(U.t, flowT); gl.uniform1f(U.rt, rt); gl.uniform1f(U.dpr, dpr); gl.uniform1f(U.k, dark ? 1 : params.lightModeFactor);
    gl.uniform1f(U.mAmt, mouse.amt); gl.uniform1f(U.warp, cur.warp); gl.uniform1f(U.think, cur.think);
    gl.uniform1f(U.prob, cur.problem); gl.uniform1f(U.ask, cur.ask); gl.uniform1f(U.tintA, cur.tintAmount);
    gl.uniform1f(U.scale, params.scale); gl.uniform1f(U.levels, params.levels); gl.uniform1f(U.lineA, params.lineAlpha);
    gl.uniform1f(U.idxA, params.indexAlpha); gl.uniform1f(U.bandA, params.bandAlpha); gl.uniform1f(U.maxA, params.maxAlpha);
    gl.uniform1f(U.basin, params.basinOpen); gl.uniform1f(U.pR, params.pointer.radius); gl.uniform1f(U.pS, params.pointer.strength); gl.uniform1f(U.press, mouse.press); gl.uniform1f(U.pD, params.pointer.pressDepth);
    gl.uniform3f(U.col, ...hexRGB(css("--sym-topo"))); gl.uniform3f(U.tint, ...tintCur);
    gl.uniform4fv(U.R, RB); gl.uniform1fv(U.K, KB); gl.uniform1i(U.NR, n); gl.uniform4fv(U.RP, PB);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    if (!still) schedule();
  }
  const onVis = () => {
    if (raf !== null) cancelAnimationFrame(raf);
    raf = null; last = 0;
    mouse.down = false;
    schedule();
  };
  const onReduce = () => {
    rip.length = 0; mouse.amt = 0; mouse.press = 0; mouse.down = false;
    schedule();
  };
  const resize = new ResizeObserver(schedule);
  resize.observe(host);
  const mutations = new MutationObserver(records => {
    if (records.some(r => r.target !== cv)) schedule();
  });
  mutations.observe(root === document ? document.documentElement : root, {
    subtree: true, childList: true, attributes: true,
    attributeFilter: ['class', 'style', 'data-theme', 'hidden', 'aria-expanded'],
  });
  // Themes are commonly applied outside the component root, on <html>/<body>.
  for (let ancestor = host.parentElement; ancestor; ancestor = ancestor.parentElement) {
    if (ancestor === root || root === document) break;
    mutations.observe(ancestor, { attributes: true, attributeFilter: ['class', 'style', 'data-theme'] });
  }
  const colorScheme = matchMedia('(prefers-color-scheme: dark)');
  colorScheme.addEventListener('change', schedule);
  reduce.addEventListener('change', onReduce);
  addEventListener('resize', schedule);
  addEventListener('scroll', schedule, true);
  document.addEventListener("visibilitychange", onVis);
  schedule();

  return {
    supported: true, setState, ripple,
    setMotionEnabled(enabled) { motionEnabled = Boolean(enabled); onReduce(); },
    destroy() { alive = false; if (raf !== null) cancelAnimationFrame(raf); document.removeEventListener("visibilitychange", onVis);
      resize.disconnect(); mutations.disconnect(); reduce.removeEventListener('change', onReduce);
      colorScheme.removeEventListener('change', schedule);
      removeEventListener('resize', schedule); removeEventListener('scroll', schedule, true);
      gl.deleteBuffer(buf); gl.deleteProgram(prog);
      pointerTarget.removeEventListener("pointermove", onMove); leaveTarget.removeEventListener("pointerleave", onLeave); pointerTarget.removeEventListener("pointerdown", onDown); removeEventListener("pointerup", onUp); removeEventListener("pointercancel", onUp); cv.remove(); },
  };
}
