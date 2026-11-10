// Deterministic scheduler/mask contract checks. Stub GL records uniforms;
// these tests do NOT claim GPU rendering or real browser layout coverage.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { mountTopo } from './symaira-topo.js';

const params = JSON.parse(readFileSync(new URL('../topo.json', import.meta.url)));
const pending = new Map();
let nextID = 0, renders = 0;
const uniforms = {};
const media = new EventTarget(); media.matches = true;
const rect = (x, y, w, h) => ({ x, y, left:x, top:y, right:x+w, bottom:y+h, width:w, height:h });
const gl = new Proxy({}, { get(_, key) {
  if (key === 'getShaderParameter') return () => true;
  if (key === 'getUniformLocation') return (_, name) => name;
  if (key === 'drawArrays') return () => { renders++; };
  if (key.startsWith('uniform')) return (name, ...args) => { uniforms[name] = args.map(x => ArrayBuffer.isView(x) ? [...x] : x); };
  return () => ({});
}});
class ElementStub extends EventTarget {
  constructor(r, hill = false) { super(); this.r = r; this.hill = hill; this.style = {}; this.dataset = {}; }
  getBoundingClientRect() { return this.r; }
  matches() { return this.hill; }
  setAttribute() {}
  prepend() {}
  remove() {}
  closest() { return { dataset: {theme:'dark'} }; }
  querySelector() { return null; }
}
globalThis.Element = ElementStub;
globalThis.window = new EventTarget();
globalThis.addEventListener = window.addEventListener.bind(window);
globalThis.removeEventListener = window.removeEventListener.bind(window);
globalThis.document = new EventTarget();
document.documentElement = new ElementStub(rect(0,0,1000,800));
document.hidden = false;
document.createElement = () => Object.assign(new ElementStub(rect(0,0,1000,800)), {getContext:()=>gl});
globalThis.getComputedStyle = () => ({position:'relative', getPropertyValue:()=> '#E1E0DA'});
globalThis.matchMedia = () => media;
globalThis.devicePixelRatio = 1;
globalThis.requestAnimationFrame = fn => { pending.set(++nextID,fn); return nextID; };
globalThis.cancelAnimationFrame = id => pending.delete(id);
globalThis.ResizeObserver = class { observe() {} disconnect() {} };
globalThis.MutationObserver = class { observe() {} disconnect() {} };
const host = new ElementStub(rect(272,40,1000,800));
const elements = Array.from({length:25}, (_,i)=>new ElementStub(rect(300+i*20,80,30,30),true));
host.querySelectorAll = () => elements;
function tick(ts) { const work = [...pending.values()]; pending.clear(); work.forEach(fn => fn(ts)); }

const topo = mountTopo(host,{params});
assert.equal(pending.size,1);
tick(100);
assert.equal(uniforms.NR[0],1);
assert.deepEqual(uniforms.R[0].slice(0,4),[28,40,510,30]);
assert.equal(uniforms.K[0][0],0);
assert.equal(pending.size,0, 'reduced motion must have no recurring timer');
media.matches = false; media.dispatchEvent(new Event('change')); tick(150);
assert.equal(pending.size,1);
document.hidden = true; document.dispatchEvent(new Event('visibilitychange'));
assert.equal(pending.size,0,'hidden document must cancel pending work');
const before = renders; tick(200); assert.equal(renders,before);
document.hidden = false;
for(let i=0;i<5;i++) document.dispatchEvent(new Event('visibilitychange'));
assert.equal(pending.size,1,'resume must not create duplicate animation loops');
tick(250);
media.matches = true; media.dispatchEvent(new Event('change')); tick(300);
assert.equal(pending.size,0);
topo.destroy();
window.dispatchEvent(new Event('resize'));
assert.equal(pending.size,0,'destroy must remove redraw subscriptions');
console.log('PASS: overflow union, reduced-motion quiescence, hidden cancellation, single resume loop, teardown');
