// Symaira Liquid Topography – Metal-Port von web/symaira-topo.js (gleicher Algorithmus).
// SwiftUI: .colorEffect(ShaderLibrary.symairaTopo(...)) – siehe SymairaTopoView.swift.
#include <metal_stdlib>
#include <SwiftUI/SwiftUI_Metal.h>
using namespace metal;

static float hash3(float3 p){ p = fract(p * .3183099 + .1); p *= 17.; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
static float n3(float3 x){
    float3 i = floor(x), f = fract(x); f = f * f * (3. - 2. * f);
    return mix(mix(mix(hash3(i), hash3(i + float3(1,0,0)), f.x), mix(hash3(i + float3(0,1,0)), hash3(i + float3(1,1,0)), f.x), f.y),
               mix(mix(hash3(i + float3(0,0,1)), hash3(i + float3(1,0,1)), f.x), mix(hash3(i + float3(0,1,1)), hash3(i + float3(1,1,1)), f.x), f.y), f.z);
}
static float fbm(float3 p){ return n3(p) * .62 + n3(p * 2.03 + 7.) * .26 + n3(p * 4.1 + 3.) * .12; }
// `a` is the per-pixel change of `v`. SwiftUI's stitchable colorEffect has no
// reliable fragment derivatives (fwidth returned 0, so every pixel counted as
// "on a line" and the whole surface went flat grey). Callers pass an explicit
// finite-difference estimate instead.
static float iso(float v, float a, float w, float s){
    float f = fract(v), d = min(f, 1. - f);
    a = max(a, 1e-4);
    return 1. - smoothstep(a * max(w - s, 0.), a * (w + s), d);
}
static float sdBox(float2 p, float4 r, float rad){
    float2 c = r.xy + r.zw * .5; float2 d = abs(p - c) - r.zw * .5 + rad;
    return length(max(d, 0.)) + min(max(d.x, d.y), 0.) - rad;
}

// rects: je 5 floats (x, y, w, h, hill) ; ripples: je 4 floats (x, y, age, strength)
// p0: size.x, size.y, t, rt     p1: mouse.x, mouse.y, mouseAmt, k
// p2: warp, think, problem, ask p3: tintAmount, askX, askY, displayScale
// p4: scale, levels, lineA, idxA p5: bandA, maxA, basinOpen, press
// p6: pointerRadius, pointerStrength, pressDepth, unused
struct TopoIn {
    float2 mouse; float mAmt; float t, rt, warp, prob, ask, press;
    float2 askP; float4 p4, p6;
    device const float *rects; int rectCount; device const float *ripples; int rippleCount;
};

// Height field at one position (everything that shapes the contour lines).
static float topoHeight(float2 pos, thread const TopoIn &in){
    float2 dm = pos - in.mouse; float md = length(dm);
    float2 sp = pos - dm * in.mAmt * in.p6.y * exp(-md * md / (in.p6.x * in.p6.x));
    float2 q = sp / in.p4.x;
    float2 w = float2(fbm(float3(q * .7, in.t * .6)), fbm(float3(q * .7 + 5.2, in.t * .6)));
    float h = fbm(float3(q + w * in.warp, in.t));
    h += in.prob * .025 * (n3(float3(sp / 26., in.rt * .9)) - .5);
    h -= in.press * in.p6.z * exp(-md * md / (in.p6.x * in.p6.x * 1.6));   // gedrückt halten: Mulde
    float hill = 0.;
    for (int i = 0; i < in.rectCount / 5; i++) {
        if (in.rects[i*5+4] < .5) continue;
        float4 r = float4(in.rects[i*5], in.rects[i*5+1], in.rects[i*5+2], in.rects[i*5+3]);
        hill = max(hill, .025 * exp(-max(sdBox(pos, r, 12.), 0.) / 24.));
    }
    h += hill;
    for (int i = 0; i < in.rippleCount / 4; i++) {
        float2 rp = float2(in.ripples[i*4], in.ripples[i*4+1]); float age = in.ripples[i*4+2], str = in.ripples[i*4+3];
        // pow(x, 2.) is undefined for x < 0 under Metal fast-math (NaN behind
        // the wave front, which saturated the whole surface). Square explicitly.
        float d = length(pos - rp), x = (d - age * 180.) / 40.;
        h += str * .03 * exp(-x * x) * exp(-age * 1.2);
    }
    if (in.ask > 0.) { float d = length(pos - in.askP); h += in.ask * .025 * sin(d / 30. + in.rt * 1.2) * exp(-d / 380.); }
    return h;
}

// rects: je 5 floats (x, y, w, h, hill) ; ripples: je 4 floats (x, y, age, strength)
// p0: size.x, size.y, t, rt     p1: mouse.x, mouse.y, mouseAmt, k
// p2: warp, think, problem, ask p3: tintAmount, askX, askY, displayScale
// p4: scale, levels, lineA, idxA p5: bandA, maxA, basinOpen, press
// p6: pointerRadius, pointerStrength, pressDepth, unused
[[ stitchable ]] half4 symairaTopo(float2 pos, half4 color,
    float4 p0, float4 p1, float4 p2, float4 p3, float4 p4, float4 p5, float4 p6,
    half4 col4, half4 tint4, device const float *rects, int rectCount, device const float *ripples, int rippleCount)
{
    float2 res = p0.xy; float rt = p0.w; float k = p1.w;
    float think = p2.y; float tintA = p3.x; float ds = max(p3.w, 1.);
    TopoIn in = { p1.xy, p1.z, p0.z, rt, p2.x, p2.z, p2.w, p5.w, p3.yz, p4, p6,
                  rects, rectCount, ripples, rippleCount };

    // Schutzzonen: keine Linien unter Text/Karten, weicher Rand von 2–8 pt.
    float mask = 1.;
    for (int i = 0; i < rectCount / 5; i++) {
        float4 r = float4(rects[i*5], rects[i*5+1], rects[i*5+2], rects[i*5+3]);
        mask = min(mask, smoothstep(2., 8., sdBox(pos, r, 12.)));
    }
    if (mask <= 0.) { return color; }

    // Finite differences over one device pixel replace fwidth().
    float px = 1. / ds;
    float v = topoHeight(pos, in) * p4.y;
    float vx = topoHeight(pos + float2(px, 0.), in) * p4.y;
    float vy = topoHeight(pos + float2(0., px), in) * p4.y;
    float a1 = abs(vx - v) + abs(vy - v);

    float line = iso(v, a1, .65 * ds, .5), idx = iso(v / 5., a1 / 5., 1. * ds, 1.6), band = floor(v) / p4.y;
    float2 e = (pos - float2(res.x * .6, res.y * .55)) / float2(res.x * .36, res.y * .5);
    float vis = mix(1., clamp((length(e) - .78) / .42, 0., 1.), p5.z);
    float pulse = 1. + think * .08 * sin(rt * 1.5);
    float a = min((max(line * p4.z, idx * p4.w) + band * p5.x) * vis * pulse, p5.y) * mask * k;
    half3 c = mix(col4.rgb, tint4.rgb, half(tintA));
    // über die Eingangsfarbe (Canvas) komponieren: SwiftUI überspringt vollständig transparente Layer
    return half4(mix(color.rgb, c, half(a)), color.a);
}
