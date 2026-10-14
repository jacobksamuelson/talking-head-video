/* talking-head-video runtime — builds ONE paused GSAP timeline from window.__STORY.
   Deterministic: no clocks, no Math.random, built once after fonts load, then
   registered as window.__timelines.main (HyperFrames seeks it frame by frame). */
(function () {
  "use strict";
  var S = window.__STORY;
  var W = S.width, H = S.height;
  var $ = function (id) { return document.getElementById(id); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  var q = function (t) { return Math.round(t * S.fps) / S.fps; };
  // tiny seeded PRNG (mulberry32) for natural-looking typing rhythm
  function rng(seed) { return function () { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; var t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

  var EASE_IN = "power3.out", EASE_OUT = "power2.in";
  function show(tl, el, t) { tl.set(el, { visibility: "visible" }, q(t)); }
  function hide(tl, el, t) { tl.set(el, { visibility: "hidden" }, q(t)); }
  function enter(tl, el, t, o) {
    o = o || {};
    tl.fromTo(el,
      { opacity: 0, y: (o.y0 || 0) + (o.rise === undefined ? 44 : o.rise), scale: o.s0 || 0.965, filter: "blur(14px)" },
      { opacity: 1, y: o.y0 || 0, scale: 1, filter: "blur(0px)", duration: o.d || 0.62, ease: EASE_IN }, q(t));
  }
  function exit(tl, el, t) {
    tl.to(el, { opacity: 0, y: "-=18", scale: 0.985, filter: "blur(10px)", duration: 0.36, ease: EASE_OUT }, q(t - 0.36));
  }
  function segAt(t) {
    for (var i = 0; i < S.segments.length; i++) if (t < S.segments[i].out[1]) return S.segments[i];
    return S.segments[S.segments.length - 1];
  }

  // ── face: slow push-in per segment ───────────────────────────
  function faceMotion(tl) {
    if (S.faceMotion === "none") return;
    var amt = typeof S.faceMotion === "number" ? S.faceMotion : 0.028;
    var first = true;
    S.segments.forEach(function (s) {
      if (s.kind === "screen") return;
      var d = s.out[1] - s.out[0];
      tl.set("#face-drift", { transformOrigin: (s.face.x * 100).toFixed(2) + "% " + (s.face.y * 100).toFixed(2) + "%" }, q(s.out[0]));
      tl.fromTo("#face-drift", { scale: 1 }, { scale: 1 + amt * Math.min(1, d / 6), duration: d, ease: "none", immediateRender: first }, q(s.out[0]));
      first = false;
    });
  }

  // ── narrated screen recordings: framed card on the theme background ──
  var FULL_CLIP = "inset(0.0px 0.0px 0.0px 0.0px round 0.0px)";
  function screenGeom(seg) {
    var r = seg.screen, cx = r.x * W, cy = r.y * H, cw = r.w * W, ch = r.h * H;
    var fill = S.screenStyle === "fill", full = fill || S.screenStyle === "full";
    var dy = full ? 0 : (S.captionsOn ? -34 : 0);
    var s = fill ? Math.max(W / cw, H / ch) : full ? 1 : Math.min((W - 240) / cw, (H - 150 - (S.captionsOn ? 80 : 0)) / ch, 1);
    var rad = full ? 0 : 22 / s;
    return {
      s: s, dy: dy,
      clip: "inset(" + [cy, W - cx - cw, H - cy - ch, cx].map(function (v) { return v.toFixed(1) + "px"; }).join(" ") + " round " + rad.toFixed(1) + "px)",
      box: { left: W / 2 + (cx - W / 2) * s, top: H / 2 + (cy - H / 2) * s + dy, width: cw * s, height: ch * s },
      full: full,
    };
  }
  function screenMode(tl) {
    var prevScreen = false;
    S.segments.forEach(function (seg) {
      var t = q(seg.out[0]);
      if (seg.kind === "screen") {
        var g = screenGeom(seg);
        tl.set("#face", { transformOrigin: W / 2 + "px " + H / 2 + "px", x: 0, y: g.dy, scale: g.s, clipPath: g.clip }, t);
        tl.set("#screen-bg", { opacity: 1 }, t);
        tl.set("#screen-shadow", { left: g.box.left, top: g.box.top, width: g.box.width, height: g.box.height, opacity: g.full ? 0 : 1, borderRadius: g.full ? 0 : 22 }, t);
        if (!prevScreen && !g.full) {   // a small settle as the screen arrives
          tl.fromTo("#face", { scale: g.s * 1.035 }, { scale: g.s, duration: 0.6, ease: "power3.out", immediateRender: false }, t);
          tl.fromTo("#screen-shadow", { scale: 1.035 }, { scale: 1, duration: 0.6, ease: "power3.out", immediateRender: false }, t);
        }
        prevScreen = true;
      } else if (prevScreen) {
        tl.set("#face", { x: 0, y: 0, scale: 1, clipPath: FULL_CLIP }, t);
        tl.set("#screen-bg", { opacity: 0 }, t);
        tl.set("#screen-shadow", { opacity: 0 }, t);
        prevScreen = false;
      }
    });
  }

  // ── screen (focus/zoom + highlight rings) ────────────────────
  function panTo(tl, o, f, t) {
    var vw = o._vp.w, vh = o._vp.h, pan = "#" + o.id + "-pan";
    if (f.reset) { tl.to(pan, { x: 0, y: 0, scale: 1, duration: f.dur || 0.9, ease: "power3.inOut" }, q(t)); return; }
    var r = f.rect;
    var s = Math.max(1, Math.min(f.scale || Math.min(0.85 / r[2], 0.85 / r[3]), 4)); // fit rect with margin
    var cx = (r[0] + r[2] / 2) * vw, cy = (r[1] + r[3] / 2) * vh;
    var x = Math.min(0, Math.max(vw - vw * s, vw / 2 - cx * s));
    var y = Math.min(0, Math.max(vh - vh * s, vh / 2 - cy * s));
    tl.to(pan, { x: x, y: y, scale: s, duration: f.dur || 1.0, ease: "power3.inOut" }, q(t));
  }
  function shotMotion(tl, o) {
    (o.focus || []).forEach(function (f) { panTo(tl, o, f, o.start + (f.at || 0)); });
    (o.highlight || []).forEach(function (h, k) {
      var el = "#" + o.id + "-hl" + k, t = o.start + (h.at || 0.8);
      tl.fromTo(el, { opacity: 0, scale: 1.12 }, { opacity: 1, scale: 1, duration: 0.45, ease: "back.out(2)" }, q(t));
      if (h.dur) tl.to(el, { opacity: 0, duration: 0.3 }, q(t + h.dur));
    });
  }
  var A = {};
  A.screen = function (tl, o) {
    var ov = $(o.id);
    show(tl, ov, o.start);
    enter(tl, "#" + o.id + "-wrap", o.start);
    if ($(o.id + "-badge")) tl.fromTo("#" + o.id + "-badge", { opacity: 0, scale: 0.8, y: 10 }, { opacity: 1, scale: 1, y: 0, duration: 0.5, ease: "back.out(1.8)" }, q(o.start + 0.45));
    shotMotion(tl, o);
    exit(tl, "#" + o.id + "-wrap", o.end);
    hide(tl, ov, o.end);
  };

  // ── chat: type prompt → send → think → answer reveal ─────────
  A.chat = function (tl, o) {
    var ov = $(o.id), ask = $(o.id + "-ask"), reply = $(o.id + "-reply");
    var chars = $$(".c", $(o.id + "-typed")), caret = $(o.id + "-caret");
    var gap = 22, off = reply ? (reply.offsetHeight + gap) / 2 : 0;
    var span = o.end - o.start;
    var natural = 0.45 + chars.length / Math.max(o.cps || 22, chars.length / 2.6) + 0.6 + (reply ? (o.think === undefined ? 0.9 : o.think) + $$(".w", reply).length / (o.wps || 9) + 2.2 : 1.6);
    var k = Math.min(1, span / natural);  // compress if the window is short
    var t = o.start;
    show(tl, ov, t);
    if (reply) tl.set(reply, { opacity: 0, y: off }, q(t));
    enter(tl, ask, t, { y0: off });
    // typing
    var cps = Math.max(o.cps || 22, chars.length / 2.6) / k, r = rng(chars.length * 7919 + 17), tt = t + 0.45 * k;
    tl.set(caret, { opacity: 1 }, q(t));
    chars.forEach(function (c, i) {
      tl.set(c, { display: "inline" }, q(tt));
      var ch = c.textContent;
      tt += (1 / cps) * (0.6 + r() * 0.8) * (ch === " " ? 1.6 : 1) * (/[,.?!]/.test(ch) ? 2.2 : 1);
    });
    // send
    var tSend = tt + 0.22 * k;
    tl.to(caret, { opacity: 0, duration: 0.1 }, q(tSend));
    tl.to("#" + o.id + "-send", { backgroundColor: S.vars.accent, duration: 0.18 }, q(tSend - 0.12));
    tl.fromTo("#" + o.id + "-send", { scale: 1 }, { scale: 1.18, duration: 0.14, yoyo: true, repeat: 1, ease: "power2.out" }, q(tSend));
    if (!reply) { exit(tl, ask, o.end); hide(tl, ov, o.end); return; }
    // reply card slides in under the prompt; the prompt rises to make room
    var tR = tSend + 0.35 * k;
    tl.to(ask, { y: 0, duration: 0.6, ease: "power3.inOut" }, q(tR));
    tl.fromTo(reply, { opacity: 0, y: off + 30, filter: "blur(12px)" }, { opacity: 1, y: 0, filter: "blur(0px)", duration: 0.6, ease: "power3.out", immediateRender: false }, q(tR));
    var think = (o.think === undefined ? 0.9 : o.think) * k;
    var thinkEl = "#" + o.id + "-think";
    tl.set(thinkEl, { opacity: 1 }, q(tR));
    tl.fromTo(thinkEl + " svg", { rotation: 0 }, { rotation: 360 * Math.max(1, Math.round(think / 0.7)), duration: think + 0.25, ease: "none", transformOrigin: "50% 50%" }, q(tR));
    tl.to(thinkEl, { opacity: 0, scale: 0.6, duration: 0.2 }, q(tR + think + 0.1));
    // words: fade/blur in, warm sweep color, settle to ink (or accent for ==hi==)
    var ws = $$(".w", reply), t0 = tR + think + 0.25;
    var avail = Math.max(0.6, o.end - 1.6 - t0);
    var per = Math.min(1 / (o.wps || 9), avail / Math.max(1, ws.length));
    ws.forEach(function (w, i) {
      var fin = w.classList.contains("hi") ? S.vars.accent : S.vars.ink;
      var ti = q(t0 + i * per);
      tl.fromTo(w, { opacity: 0, filter: "blur(6px)", color: S.vars.sweep }, { opacity: 1, filter: "blur(0px)", duration: 0.32, ease: "power2.out" }, ti);
      tl.to(w, { color: fin, duration: 0.55, ease: "power1.inOut" }, q(ti + 0.28));
    });
    exit(tl, "#" + o.id + "-stack", o.end);
    hide(tl, ov, o.end);
  };

  // ── full-frame title ─────────────────────────────────────────
  A.title = function (tl, o) {
    var ov = $(o.id);
    show(tl, ov, o.start);
    tl.fromTo("#" + o.id + "-bg", { opacity: 0 }, { opacity: 1, duration: 0.22, ease: "power1.out" }, q(o.start));
    tl.fromTo($$(".tw", ov), { yPercent: 115 }, { yPercent: 0, duration: 0.7, ease: "expo.out", stagger: 0.07 }, q(o.start + 0.08));
    tl.to("#" + o.id + "-inner", { opacity: 0, y: -20, duration: 0.2, ease: EASE_OUT }, q(o.end - 0.2));
    tl.to("#" + o.id + "-bg", { opacity: 0, duration: 0.14 }, q(o.end - 0.14));
    hide(tl, ov, o.end);
  };

  // ── lower third ──────────────────────────────────────────────
  A.lowerThird = function (tl, o) {
    var ov = $(o.id);
    show(tl, ov, o.start);
    tl.fromTo("#" + o.id + "-bar", { scaleY: 0 }, { scaleY: 1, duration: 0.5, ease: "expo.out" }, q(o.start));
    tl.fromTo($$(".ltw", ov), { yPercent: 110 }, { yPercent: 0, duration: 0.65, ease: "expo.out", stagger: 0.09 }, q(o.start + 0.12));
    tl.to($$(".ltw", ov), { yPercent: -110, duration: 0.35, ease: "power2.in", stagger: 0.05 }, q(o.end - 0.45));
    tl.to("#" + o.id + "-bar", { scaleY: 0, duration: 0.3, ease: "power2.in" }, q(o.end - 0.3));
    hide(tl, ov, o.end);
  };

  // ── stacked prompt bubbles ───────────────────────────────────
  A.bubbles = function (tl, o) {
    var ov = $(o.id), bs = $$(".bubble", ov);
    show(tl, ov, o.start);
    bs.forEach(function (b, k) {
      var t = (o.itemTimes && o.itemTimes[k] !== null && o.itemTimes[k] !== undefined) ? o.itemTimes[k] : o.start + 0.25 + k * 0.42;
      tl.fromTo(b, { opacity: 0, y: 26, scale: 0.86, filter: "blur(8px)" }, { opacity: 1, y: 0, scale: 1, filter: "blur(0px)", duration: 0.55, ease: "back.out(1.7)" }, q(t));
      tl.to(b, { y: -10, duration: Math.max(0.5, o.end - t - 0.4), ease: "sine.inOut" }, q(t + 0.55));
    });
    tl.to(bs, { opacity: 0, y: "-=16", filter: "blur(8px)", duration: 0.35, ease: EASE_OUT, stagger: 0.05 }, q(o.end - 0.35 - 0.05 * (bs.length - 1)));
    hide(tl, ov, o.end);
  };

  // ── callout (big number / key point) ─────────────────────────
  A.callout = function (tl, o) {
    var ov = $(o.id), card = $(o.id + "-card"), val = $(o.id + "-val");
    show(tl, ov, o.start);
    enter(tl, card, o.start);
    if (val && o.countUp !== false) {
      var m = String(o.value).match(/^([^\d-]*)(-?[\d,]*\.?\d+)(.*)$/);
      if (m) {
        var target = parseFloat(m[2].replace(/,/g, "")), dec = (m[2].split(".")[1] || "").length, commas = m[2].indexOf(",") >= 0;
        var box = { v: 0 };
        tl.fromTo(box, { v: 0 }, { v: target, duration: 1.1, ease: "power3.out", onUpdate: function () {
          var n = box.v.toFixed(dec);
          if (commas) n = Number(n).toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
          val.textContent = m[1] + n + m[3];
        } }, q(o.start + 0.2));
      }
    }
    exit(tl, card, o.end);
    hide(tl, ov, o.end);
  };

  // ── demo: product full-frame, face shrinks into a PiP circle ─
  A.demo = function (tl, o) {
    var ov = $(o.id), R = o.pipSize ? o.pipSize / 2 : 150, M = 70;
    var cx = o.pip === "bottom-left" ? M + R : W - M - R, cy = H - M - R;
    if (o.pip === "top-right") cy = M + R;
    var ring = $("pip-ring");
    function pipState(seg) {
      if (!seg.face) seg = S.segments.filter(function (x) { return x.face; })[0] || { face: { x: 0.5, y: 0.42, size: 0.16 } };
      var fx = seg.face.x * W, fy = seg.face.y * H;
      // circle ≈ 1.6 face-widths, kept inside the frame so no empty edge shows
      var r0 = Math.max(110, Math.min(seg.face.size * W * 0.8, fy, H - fy, fx, W - fx));
      // inset(top right bottom left round r): full frame morphs into the circle around the face
      var ins = [fy - r0, W - fx - r0, H - fy - r0, fx - r0].map(function (v) { return v.toFixed(1) + "px"; }).join(" ");
      return { clipPath: "inset(" + ins + " round " + r0.toFixed(1) + "px)", transformOrigin: fx.toFixed(1) + "px " + fy.toFixed(1) + "px", x: cx - fx, y: cy - fy, scale: R / r0 };
    }
    var FULL_CLIP = "inset(0.0px 0.0px 0.0px 0.0px round 0.0px)";
    var s0 = pipState(segAt(o.start));
    var full = { clipPath: FULL_CLIP, x: 0, y: 0, scale: 1 };
    show(tl, ov, o.start);
    tl.fromTo("#" + o.id + "-bg", { opacity: 0 }, { opacity: 1, duration: 0.5, ease: "power1.out" }, q(o.start));
    tl.set("#face", { transformOrigin: s0.transformOrigin }, q(o.start));
    tl.fromTo("#face", full, { clipPath: s0.clipPath, x: s0.x, y: s0.y, scale: s0.scale, duration: 0.8, ease: "power3.inOut", immediateRender: false }, q(o.start));
    tl.set(ring, { left: cx - R, top: cy - R, width: 2 * R, height: 2 * R }, q(o.start));
    tl.fromTo(ring, { opacity: 0 }, { opacity: 1, duration: 0.3 }, q(o.start + 0.65));
    enter(tl, "#" + o.id + "-wrap", o.start + 0.25, { rise: 60, s0: 0.94, d: 0.8 });
    // re-aim the PiP at segment cuts inside the demo window (zoom may change)
    S.segments.forEach(function (s) {
      if (s.out[0] > o.start + 0.85 && s.out[0] < o.end - 0.9) {
        var st = pipState(s);
        tl.set("#face", st, q(s.out[0]));
      }
    });
    shotMotion(tl, o);
    if (o.end >= S.arollEnd - 0.05) return;  // demo runs to the end: hold the PiP, no exit
    var sEnd = pipState(segAt(o.end - 0.9));
    tl.to(ring, { opacity: 0, duration: 0.2 }, q(o.end - 0.85));
    tl.fromTo("#face", sEnd, { clipPath: FULL_CLIP, x: 0, y: 0, scale: 1, duration: 0.8, ease: "power3.inOut", immediateRender: false }, q(o.end - 0.8));
    tl.to("#" + o.id + "-wrap", { opacity: 0, y: 30, scale: 0.97, duration: 0.4, ease: EASE_OUT }, q(o.end - 0.8));
    tl.to("#" + o.id + "-bg", { opacity: 0, duration: 0.3 }, q(o.end - 0.3));
    tl.set("#face", { clipPath: "none" }, q(o.end));
    hide(tl, ov, o.end);
  };

  // smooth zoom into a region of a narrated screen recording; rect is a fraction of the screen
  function zoomXf(seg, R, k) {
    var r = seg.screen, cx = r.x * W, cy = r.y * H, cw = r.w * W, ch = r.h * H;
    var rx = cx + R[0] * cw, ry = cy + R[1] * ch, rw = R[2] * cw, rh = R[3] * ch;
    k = Math.max(1, Math.min(k || Math.min(cw / rw, ch / rh) * 0.88, 4));
    var X = cx + cw / 2 - k * (rx + rw / 2), Y = cy + ch / 2 - k * (ry + rh / 2);
    X = Math.min(cx * (1 - k), Math.max((cx + cw) * (1 - k), X));
    Y = Math.min(cy * (1 - k), Math.max((cy + ch) * (1 - k), Y));
    return { x: X, y: Y, scale: k };
  }
  A.zoom = function (tl, o) {
    var seg = segAt(o.start + 0.05);
    if (seg.kind !== "screen") return;
    var a = zoomXf(seg, o.rect, o.scale);
    var dIn = o.in || 1.0, dOut = Math.min(0.9, (o.end - o.start) / 3);
    tl.set("#face-drift", { transformOrigin: "0px 0px" }, q(o.start));
    tl.fromTo("#face-drift", { x: 0, y: 0, scale: 1 }, { x: a.x, y: a.y, scale: a.scale, duration: dIn, ease: "power3.inOut", immediateRender: false }, q(o.start));
    // during the hold: follow the content to the "to" rect(s), or creep in slowly so the frame never sits still
    var h0 = o.start + dIn, h1 = o.end - dOut;
    if (h1 - h0 > 0.4) {
      var path = o.to ? (Array.isArray(o.to[0]) ? o.to : [o.to]) : null;
      if (path) {
        var step = (h1 - h0) / path.length;
        path.forEach(function (R, i) {
          var b = zoomXf(seg, R, o.toScale || o.scale);
          tl.to("#face-drift", { x: b.x, y: b.y, scale: b.scale, duration: step, ease: "sine.inOut" }, q(h0 + i * step));
        });
      } else if (o.drift !== 0) {
        var b = zoomXf(seg, o.rect, a.scale * (1 + (o.drift === undefined ? 0.04 : o.drift)));
        tl.to("#face-drift", { x: b.x, y: b.y, scale: b.scale, duration: h1 - h0, ease: "sine.inOut" }, q(h0));
      }
    }
    tl.to("#face-drift", { x: 0, y: 0, scale: 1, duration: dOut, ease: "power3.inOut" }, q(o.end - dOut));
  };

  // highlighter stroke or ring on a line of a screen recording; it sits inside the recording,
  // so it moves with any zoom
  A.mark = function (tl, o) {
    var el = "#" + o.id + "-mark", t = q(o.start);
    tl.set(el, { opacity: 1 }, t);
    if (o.style === "ring") tl.fromTo(el, { scale: 1.08, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.4, ease: "power3.out", immediateRender: false }, t);
    else tl.fromTo(el, { scaleX: 0 }, { scaleX: 1, duration: 0.5, ease: "power2.out", immediateRender: false }, t);
    tl.to(el, { opacity: 0, duration: 0.3 }, q(o.end - 0.3));
  };

  A.endcard = function (tl, o) {
    var ov = $(o.id), card = $(o.id + "-card");
    show(tl, ov, o.start);
    enter(tl, card, o.start, { d: 0.8 });
    tl.fromTo($$(".ec-kicker, .ec-title, .ec-text", card), { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.6, ease: EASE_IN, stagger: 0.12 }, q(o.start + 0.25));
    if (o.end < S.arollEnd - 0.05) { exit(tl, card, o.end); hide(tl, ov, o.end); }
  };

  A.html = function (tl, o) {
    var ov = $(o.id);
    show(tl, ov, o.start);
    enter(tl, "#" + o.id + "-card", o.start);
    exit(tl, "#" + o.id + "-card", o.end);
    hide(tl, ov, o.end);
  };

  // ── captions ─────────────────────────────────────────────────
  function captions(tl) {
    if (!S.captions.length) return;
    function modeAt(t) {
      var m = "normal";
      S.segments.forEach(function (sg) { if (sg.kind === "screen" && t >= sg.out[0] - 0.001 && t < sg.out[1]) m = "boxed"; });
      S.overlays.forEach(function (o) { if (o.type === "demo" && t >= o.start && t < o.end) m = "boxed"; });
      S.overlays.forEach(function (o) { if (o.type === "title" && t >= o.start && t < o.end) m = "hidden"; });
      return m;
    }
    var marks = [0];
    S.segments.forEach(function (sg) { marks.push(sg.out[0], sg.out[1]); });
    S.overlays.forEach(function (o) { if (o.type === "title" || o.type === "demo") marks.push(o.start, o.end); });
    marks = marks.map(q).filter(function (t, i, a) { return a.indexOf(t) === i && t < S.duration; }).sort(function (a, b) { return a - b; });
    var cur = null;
    marks.forEach(function (t) { var m = modeAt(t + 0.001); if (m !== cur) { tl.set("#captions", { attr: { "data-mode": m } }, t); cur = m; } });
    S.captions.forEach(function (c, k) {
      var el = $("cap" + k);
      tl.set(el, { visibility: "visible" }, q(c.start));
      var next = S.captions[k + 1];
      // linger 0.4 s after the last word, but never past the next line or the cut
      var off = Math.max(c.start + 0.1, Math.min(c.end + 0.4, next ? next.start : 1e9, c.segEnd || 1e9));
      tl.set(el, { visibility: "hidden" }, q(off));
      c.words.forEach(function (w, j) {
        tl.set("#cap" + k + "-" + j, { color: S.vars["pop-on-video"] }, q(w[0]));
        tl.set("#cap" + k + "-" + j, { color: "#ffffff" }, q(Math.max(w[0] + 0.05, w[1])));
      });
    });
  }

  // ── logo end slate: dissolve from the last frame, logo rises in, lines follow ──
  function slate(tl) {
    if (!S.slate) return;
    var t0 = S.arollEnd, xf = Math.min(0.45, t0);
    tl.set("#slate", { visibility: "visible" }, q(t0 - xf));
    tl.fromTo("#slate", { opacity: 0 }, { opacity: 1, duration: xf, ease: "power1.inOut", immediateRender: false }, q(t0 - xf));
    var parts = $$(".slate-inner > *");
    tl.set(parts, { opacity: 0 }, q(t0 - xf));
    parts.forEach(function (el, i) {
      var big = i === 0;
      tl.fromTo(el, { opacity: 0, y: big ? 28 : 16, filter: "blur(" + (big ? 12 : 6) + "px)" },
        { opacity: 1, y: 0, filter: "blur(0px)", duration: big ? 0.9 : 0.6, ease: "power3.out", immediateRender: false }, q(t0 + 0.1 + i * 0.28));
    });
  }

  function build() {
    var tl = gsap.timeline({ paused: true });
    faceMotion(tl);
    screenMode(tl);
    if (S.fadeOut > 0) tl.fromTo("#fade-black", { opacity: 0 }, { opacity: 1, duration: S.fadeOut, ease: "power1.in" }, q(S.duration - S.fadeOut));
    S.overlays.forEach(function (o) { A[o.type](tl, o); });
    captions(tl);
    slate(tl);
    window.__timelines["main"] = tl;
    if (window.__hfForceTimelineRebind) window.__hfForceTimelineRebind();
  }
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(build); else build();
})();
