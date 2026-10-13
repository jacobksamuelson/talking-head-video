#!/usr/bin/env node
// Build the HyperFrames composition (public/index.html) from storyboard.json.
//
// Inputs:  storyboard.json, work/timeline.json, work/words.edited.json, public/aroll.mp4
// Output:  public/index.html (+ public/assets/*), work/overlays.resolved.json
//
// Overlay timing is anchored to spoken phrases ("at": "the words he says"), so
// re-cutting the A-roll keeps every overlay in sync. See reference/storyboard.md.
//
// Usage: node build.mjs <project_dir>
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const SKILL = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const proj = path.resolve(process.argv[2] || ".");
const W = 1920, H = 1080, FPS = 30;
const readJSON = (p, d) => (fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, "utf8")) : d);
const die = (m) => { console.error("ERROR: " + m); process.exit(1); };

const sb = readJSON(path.join(proj, "storyboard.json"), null) || die("storyboard.json missing");
const tlj = readJSON(path.join(proj, "work/timeline.json"), null) || die("run assemble.py first");
const words = readJSON(path.join(proj, "work/words.edited.json"), []);
const DUR = tlj.duration;
const pub = path.join(proj, "public");
const assets = path.join(pub, "assets");
fs.mkdirSync(assets, { recursive: true });

// ── themes ─────────────────────────────────────────────────────────────
const THEMES = {
  neutral: {
    fonts: { Display: [["Inter-700-latin.woff2", "600 900"]], UI: [["Inter-400-latin.woff2", "300 500"], ["Inter-700-latin.woff2", "501 900"]] },
    vars: {
      ink: "#14151a", "ink-soft": "#3d404b", muted: "#6b6f7d",
      accent: "#2F5BFF", "accent-2": "#FF5A1F", pop: "#FFD23F", "pop-on-video": "#FFD23F",
      grad: "linear-gradient(100deg, #2F5BFF 0%, #9B5CFF 50%, #FF5A1F 100%)",
      "card-bg": "rgba(255,255,255,.9)",
      "title-bg": "radial-gradient(1100px 700px at 12% 18%, rgba(47,91,255,.12), transparent 62%), radial-gradient(900px 700px at 90% 85%, rgba(255,90,31,.10), transparent 60%), #F4F5F8",
      "dark-bg": "radial-gradient(1000px 700px at 85% 12%, rgba(47,91,255,.5), transparent 60%), #0E1018",
      "title-ink": "#14151a", "title-weight": "700", "title-tracking": "-0.03em",
      radius: "30px", margin: "96px", sweep: "#FF5A1F",
    },
  },
};
const themeCfg = typeof sb.theme === "string" ? { base: sb.theme } : sb.theme || {};
const theme = THEMES[themeCfg.base || "neutral"] || die(`unknown theme ${themeCfg.base}`);
const vars = { ...theme.vars };
for (const [k, v] of Object.entries(themeCfg)) if (k !== "base") vars[k] = v;

// ── phrase anchoring ───────────────────────────────────────────────────
const norm = (s) => s.toLowerCase().replace(/[’‘]/g, "'").replace(/[^a-z0-9' ]+/g, "").trim();
const toks = (s) => s.toLowerCase().replace(/[’‘]/g, "'").replace(/[^a-z0-9' ]+/g, " ").split(/\s+/).map(norm).filter(Boolean);
const W_N = words.map((w) => norm(w.text));

function findPhrase(phrase, nth = 1, after = -1) {
  const t = toks(phrase);
  if (!t.length) die(`empty phrase anchor`);
  let seen = 0;
  for (let i = 0; i + t.length <= W_N.length; i++) {
    if (words[i].start < after) continue;
    let ok = true;
    for (let j = 0; j < t.length; j++) if (W_N[i + j] !== t[j]) { ok = false; break; }
    if (ok && ++seen === nth) return { start: words[i].start, end: words[i + t.length - 1].end, i };
  }
  // helpful failure: nearest windows by token overlap
  const scored = [];
  for (let i = 0; i < W_N.length; i++) {
    const win = W_N.slice(i, i + t.length);
    const s = t.filter((x) => win.includes(x)).length / t.length;
    scored.push([s, i]);
  }
  scored.sort((a, b) => b[0] - a[0]);
  const near = scored.slice(0, 3).map(([s, i]) => `"${words.slice(i, i + t.length).map((w) => w.text).join(" ")}" @${words[i]?.start}`);
  die(`phrase not found in edited transcript: "${phrase}"${nth > 1 ? ` (#${nth})` : ""}\n  closest: ${near.join(" | ")}`);
}

function resolveTime(spec, kind, fallbackLead) {
  if (spec === undefined || spec === null) return null;
  if (typeof spec === "number") return spec;
  const o = typeof spec === "string" ? { phrase: spec } : spec;
  if (o.t !== undefined) return o.t;
  if (o.segment !== undefined) {
    // anchor to the segment that holds a phrase id from cuts.json (e.g. a wordless hold)
    const sg = tlj.segments.find((x) => (x.phrases || []).map(String).includes(String(o.segment)));
    if (!sg) die(`no segment contains phrase id "${o.segment}"`);
    return (kind === "start" ? sg.out[0] : sg.out[1]) + (o.offset ?? 0);
  }
  const m = findPhrase(o.phrase, o.nth || 1);
  const off = o.offset ?? fallbackLead;
  return kind === "start" ? m.start + off : m.end + off;
}

// ── helpers ────────────────────────────────────────────────────────────
const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const q = (n) => Math.round(n * FPS) / FPS;
function mediaInfo(p) {
  const out = execFileSync("ffprobe", ["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration", "-of", "json", p]).toString();
  const j = JSON.parse(out);
  return { w: j.streams[0].width, h: j.streams[0].height, dur: parseFloat(j.format?.duration || "0") || 0 };
}
const copied = new Map();
function stage(rel) {
  if (copied.has(rel)) return copied.get(rel);
  const src = path.isAbsolute(rel) ? rel : path.join(proj, rel);
  if (!fs.existsSync(src)) die(`asset not found: ${rel}`);
  const name = path.basename(src).replace(/[^\w.-]+/g, "_");
  const dst = path.join(assets, "media", name);
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  if (!fs.existsSync(dst) || fs.statSync(dst).mtimeMs < fs.statSync(src).mtimeMs) fs.copyFileSync(src, dst);
  const r = { url: `assets/media/${name}`, abs: dst, ...mediaInfo(src), isVideo: /\.(mp4|mov|m4v|webm)$/i.test(src) };
  copied.set(rel, r);
  return r;
}
const SPARK = `<svg class="spark" viewBox="0 0 40 40"><defs><linearGradient id="sg-ID" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="var(--accent)"/><stop offset=".55" stop-color="#7B5CFF"/><stop offset="1" stop-color="var(--accent-2)"/></linearGradient></defs><path fill="url(#sg-ID)" d="M20 3c1.2 7.6 4.4 12.8 17 17-12.6 4.2-15.8 9.4-17 17-1.2-7.6-4.4-12.8-17-17C15.6 15.8 18.8 10.6 20 3z"/></svg>`;
const SEND = `<svg viewBox="0 0 24 24"><path d="M12 19V5M5.5 11.5 12 5l6.5 6.5" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const RING = `<svg viewBox="0 0 44 44"><defs><linearGradient id="rg-ID" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="var(--accent)"/><stop offset="1" stop-color="var(--accent-2)"/></linearGradient></defs><circle cx="22" cy="22" r="17" fill="none" stroke="#e6e7ef" stroke-width="5"/><path d="M22 5a17 17 0 0 1 17 17" fill="none" stroke="url(#rg-ID)" stroke-width="5" stroke-linecap="round"/></svg>`;

function richText(text) {
  // paragraphs (\n\n), **bold**, ==highlight==  →  word spans
  return String(text).split(/\n\s*\n/).map((para) => {
    let html = "", bold = false, hi = false;
    for (const tok of para.split(/(\*\*|==|\s+)/)) {
      if (tok === "**") { bold = !bold; continue; }
      if (tok === "==") { hi = !hi; continue; }
      if (!tok) continue;
      if (/^\s+$/.test(tok)) { html += " "; continue; }
      let w = `<span class="w${hi ? " hi" : ""}">${esc(tok)}</span>`;
      if (bold) w = `<b>${w}</b>`;
      html += w;
    }
    return `<p>${html.trim()}</p>`;
  }).join("");
}
const masked = (text, cls = "") => text.split(/\s+/).filter(Boolean).map((w) => `<span class="m"><span class="${cls}">${esc(w)}</span></span>`).join(" ");
const sideClass = (o, def = "side-left") => (o.side === "right" ? "side-right" : o.side === "center" ? "center" : def) + (o.v === "top" ? " v-top" : o.v === "bottom" ? " v-bottom" : "");

// ── components: markup + duration defaults ─────────────────────────────
const SIZES = { s: 560, m: 760, l: 980, xl: 1180 };
function shotMarkup(o, id, boxW, boxH) {
  const m = stage(o.src);
  const phone = o.chrome === "phone" || (o.chrome === undefined && m.h / m.w > 1.3);
  const chrome = phone || o.chrome === "none" ? 0 : 46;
  const pad = phone ? 24 : 0;
  const scale = Math.min((boxW - pad) / m.w, (boxH - chrome - pad) / m.h);
  const vw = Math.round(m.w * scale), vh = Math.round(m.h * scale);
  o._vp = { w: vw, h: vh };
  const hls = (o.highlight || []).map((h, k) => {
    const [x, y, w, hh] = h.rect;
    return `<div class="hl" id="${id}-hl${k}" style="left:${x * vw - 6}px;top:${y * vh - 6}px;width:${w * vw + 12}px;height:${hh * vh + 12}px"></div>`;
  }).join("");
  const media = m.isVideo
    ? `<video id="${id}-vid" src="${m.url}" muted playsinline data-start="${q(o.start).toFixed(4)}" data-duration="${q(o.end - o.start).toFixed(4)}" data-media-start="${o.mediaStart || 0}" data-track-index="3"></video>`
    : `<img src="${m.url}" alt="">`;
  const bar = chrome ? `<div class="chrome"><span class="dots"><i></i><i></i><i></i></span>${o.url ? `<span class="url">${esc(o.url)}</span>` : ""}</div>` : "";
  return `<div class="card shot${phone ? " phone" : ""}" id="${id}-card">${bar}<div class="vp" style="width:${vw}px;height:${vh}px"><div class="pan" id="${id}-pan" style="width:${vw}px;height:${vh}px">${media}${hls}</div></div></div>`;
}

const C = {
  screen: {
    dur: 4.5,
    html(o, id) {
      const boxW = SIZES[o.size || "m"] || o.size, boxH = o.maxHeight || 760;
      const cap = o.caption ? `<div class="cap" id="${id}-cap">${esc(o.caption)}</div>` : "";
      const badge = o.badge ? `<div class="badge" id="${id}-badge">${esc(o.badge)}</div>` : "";
      return `<div class="ov ${sideClass(o)}" id="${id}"><div class="shot-wrap" id="${id}-wrap">${badge}${shotMarkup(o, id, boxW, boxH)}${cap}</div></div>`;
    },
  },
  chat: {
    dur(o) {
      const cps = Math.max(o.cps || 22, (o.prompt || "").length / 2.6);
      let d = 0.45 + (o.prompt || "").length / cps + 0.6;
      if (o.answer) d += (o.think ?? 0.9) + o.answer.split(/\s+/).length / (o.wps || 9) + 2.2;
      else d += 1.6;
      return d;
    },
    html(o, id) {
      const chars = [...(o.prompt || "")].map((c) => `<span class="c">${esc(c)}</span>`).join("");
      const reply = o.answer ? `<div class="card reply" id="${id}-reply"><div class="think" id="${id}-think">${RING.replaceAll("ID", id)}</div><div class="ans" id="${id}-ans">${richText(o.answer)}</div></div>` : "";
      return `<div class="ov ${sideClass(o)}" id="${id}"><div class="chat-stack" id="${id}-stack" style="--chat-w:${o.width || 760}px"><div class="card ask" id="${id}-ask"><div class="pill-wrap"><div class="glow"></div><div class="pill">${SPARK.replaceAll("ID", id)}<div class="typed" id="${id}-typed">${chars}<span class="caret" id="${id}-caret"></span></div><div class="send" id="${id}-send">${SEND}</div></div></div></div>${reply}</div></div>`;
    },
  },
  title: {
    dur: 2.4,
    html(o, id) {
      const lines = o.lines || [o.text];
      const k = o.kicker ? `<div class="kicker"><span class="m"><span class="tw">${esc(o.kicker)}</span></span></div>` : "";
      const body = lines.map((l, i) => `<div class="tline${i > 0 && o.accentLast !== false && i === lines.length - 1 ? " accent" : ""}">${masked(l, "tw")}</div>`).join("");
      return `<div class="ov top title${o.style === "dark" ? " dark" : ""}" id="${id}" style="${o.size ? `--title-size:${o.size}px` : ""}"><div class="title-bg" id="${id}-bg"></div><div class="title-inner" id="${id}-inner">${k}${body}</div></div>`;
    },
  },
  lowerThird: {
    dur: 4.5,
    html(o, id) {
      return `<div class="ov lt${o._card ? " on-card" : ""}" id="${id}"><div class="lt-box"><div class="lt-bar" id="${id}-bar"></div><div class="lt-text"><div class="lt-name"><span class="m"><span class="ltw">${esc(o.name)}</span></span></div>${o.role ? `<div class="lt-role"><span class="m"><span class="ltw">${esc(o.role)}</span></span></div>` : ""}</div></div></div>`;
    },
  },
  bubbles: {
    dur: (o) => 2.6 + (o.items || []).length * 0.55,
    html(o, id) {
      const items = (o.items || []).map((it, k) => `<div class="bubble" id="${id}-b${k}">${esc(typeof it === "string" ? it : it.text)}</div>`).join("");
      return `<div class="ov ${sideClass(o)}" id="${id}"><div class="bubbles">${items}</div></div>`;
    },
  },
  callout: {
    dur: 3.6,
    html(o, id) {
      const k = o.kicker ? `<div class="kicker">${esc(o.kicker)}</div>` : "";
      const v = o.value !== undefined ? `<div class="value" id="${id}-val">${esc(o.value)}</div>` : "";
      const t = o.text ? `<div class="text">${esc(o.text)}</div>` : "";
      return `<div class="ov ${sideClass(o)}" id="${id}"><div class="card callout" id="${id}-card">${k}${v}${t}</div></div>`;
    },
  },
  demo: {
    dur: 6,
    html(o, id) {
      const room = sb.captions ? " cap-room" : "";
      return `<div class="ov under" id="${id}"><div class="demo-bg" id="${id}-bg"></div><div class="demo-stage${room}"><div id="${id}-wrap">${shotMarkup(o, id, o.width || 1380, sb.captions ? 840 : 920)}</div></div></div>`;
    },
  },
  endcard: {
    dur: 3,
    html(o, id) {
      const k = o.kicker ? `<div class="ec-kicker">${esc(o.kicker)}</div>` : "";
      const sub = o.text ? `<div class="ec-text">${esc(o.text)}</div>` : "";
      return `<div class="ov ${sideClass(o)}" id="${id}"><div class="card endcard" id="${id}-card">${k}<div class="ec-title">${esc(o.title)}</div>${sub}</div></div>`;
    },
  },
  zoom: {
    dur: 3,
    html: () => "",
  },
  html: {
    dur: 4,
    html(o, id) {
      const frag = fs.readFileSync(path.join(proj, o.file), "utf8");
      return `<div class="ov ${sideClass(o, "center")}" id="${id}"><div class="custom" id="${id}-card">${frag}</div></div>`;
    },
  },
};

// ── resolve overlays ───────────────────────────────────────────────────
const resolved = [];
(sb.overlays || []).forEach((o, i) => {
  const comp = C[o.type] || die(`unknown overlay type "${o.type}" (overlay ${i})`);
  const id = `ov${i + 1}`;
  let start = resolveTime(o.at, "start", -0.15);
  if (start === null) die(`overlay ${i} (${o.type}) needs "at"`);
  let end = resolveTime(o.until, "end", 0.35);
  const minDur = typeof comp.dur === "function" ? comp.dur(o) : comp.dur;
  if (end === null) end = start + (o.dur ?? minDur);
  start = Math.max(0, q(start));
  end = Math.min(DUR, q(end));
  if (end - start < 0.8) die(`overlay ${id} (${o.type}) is only ${(end - start).toFixed(2)}s long — check at/until`);
  if (o.type === "chat" && end - start < minDur - 0.3) console.warn(`WARN ${id}: chat window ${(end - start).toFixed(1)}s < natural ${minDur.toFixed(1)}s — reveal will be compressed`);
  const r = { ...o, id, start, end };
  if (o.type === "bubbles") r.itemTimes = (o.items || []).map((it, k) => (typeof it === "object" && it.at ? q(resolveTime(it.at, "start", -0.1)) : null));
  resolved.push(r);
});
// nothing should fade in underneath a full-frame title: start it as the title leaves
for (const t of resolved.filter((o) => o.type === "title"))
  for (const o of resolved)
    if (o !== t && o.type !== "lowerThird" && o.start >= t.start && o.start < t.end) {
      console.warn(`NOTE ${o.id} (${o.type}) started under title ${t.id}; moved to ${t.end.toFixed(2)}s`);
      o.start = t.end;
    }
for (let a = 0; a < resolved.length; a++)
  for (let b = a + 1; b < resolved.length; b++) {
    const A = resolved[a], B = resolved[b];
    if (A.type === "zoom" || B.type === "zoom") continue;  // zooms are trimmed to their recording later
    const zone = (o) => (["title", "demo"].includes(o.type) ? "full" : o.type === "lowerThird" ? "lt" : o.side || "left");
    if (zone(A) === zone(B) && A.start < B.end && B.start < A.end) console.warn(`WARN overlap: ${A.id} (${A.type}) and ${B.id} (${B.type}) share the ${zone(A)} zone during ${Math.max(A.start, B.start).toFixed(2)}–${Math.min(A.end, B.end).toFixed(2)}s`);
  }

// a highlight must stay inside whatever zoom (focus) is active when it appears
for (const o of resolved) {
  for (const h of o.highlight || []) {
    const t = h.at ?? 0.8;
    const f = (o.focus || []).filter((x) => (x.at || 0) <= t).pop();
    if (!f || f.reset) continue;
    const [fx, fy, fw, fh] = f.rect, [hx, hy, hw, hh] = h.rect;
    if (hx < fx || hy < fy || hx + hw > fx + fw || hy + hh > fy + fh)
      console.warn(`WARN ${o.id}: highlight [${h.rect}] at +${t}s falls outside the focus rect [${f.rect}] — it will be cropped. Widen the focus rect to contain it.`);
  }
}

// warn when a side card will sit on top of the face
const CARD_W = { screen: (o) => SIZES[o.size || "m"] || o.size, chat: (o) => o.width || 760, callout: () => 760, bubbles: () => 640 };
for (const o of resolved) {
  if (!CARD_W[o.type] || o.side === "center") continue;
  const wpx = CARD_W[o.type](o) + 96;
  for (const s of tlj.segments) {
    if (s.out[1] <= o.start || s.out[0] >= o.end || !s.face) continue;
    const faceL = (s.face.x - s.face.size * 0.55) * W, faceR = (s.face.x + s.face.size * 0.55) * W;
    const hit = o.side === "right" ? faceR > W - wpx : faceL < wpx;
    if (hit) console.warn(`WARN ${o.id} (${o.type}, ${o.side || "left"}) covers the face in segment ${s.i ?? tlj.segments.indexOf(s)} — in cuts.json give that phrase "zoom": 1.2 and "faceX": ${o.side === "right" ? 0.36 : 0.64}, or use side "${o.side === "right" ? "left" : "right"}"`);
  }
}

// screen-recording segments: zooms must sit inside one run of screen segments; face-only
// overlays don't belong on top of a screen recording
const screenRuns = [];
for (const s of tlj.segments) {
  if ((s.kind || "face") !== "screen") continue;
  const last = screenRuns[screenRuns.length - 1];
  if (last && Math.abs(last[1] - s.out[0]) < 0.01) last[1] = s.out[1];
  else screenRuns.push([s.out[0], s.out[1]]);
}
const inRun = (t) => screenRuns.find((r) => t >= r[0] - 0.01 && t < r[1]);
for (const o of resolved) {
  const run = inRun(o.start + 0.05);
  if (o.type === "zoom") {
    if (!run) die(`${o.id} (zoom) starts at ${o.start.toFixed(2)}s, which is not inside a screen recording`);
    if (o.end > run[1]) { console.warn(`NOTE ${o.id} (zoom) trimmed to end with its screen recording at ${run[1].toFixed(2)}s`); o.end = q(run[1]); }
    continue;
  }
  const overlaps = screenRuns.some((r) => o.start < r[1] && r[0] < o.end);
  const onScreen = screenRuns.reduce((n, r) => n + Math.max(0, Math.min(o.end, r[1]) - Math.max(o.start, r[0])), 0);
  if (o.type === "lowerThird" && (onScreen > (o.end - o.start) / 2 || o.style === "card")) { o._card = true; continue; }
  if (o.type === "lowerThird") continue;
  if (overlaps && ["demo", "screen", "chat", "bubbles"].includes(o.type))
    console.warn(`WARN ${o.id} (${o.type}) overlaps a screen recording — on screen footage use zoom, callout or title instead`);
}

// ── captions ───────────────────────────────────────────────────────────
let captionsHTML = "";
const capChunks = [];
if (sb.captions) {
  let cur = [];
  const flush = () => { if (cur.length) capChunks.push(cur); cur = []; };
  for (let i = 0; i < words.length; i++) {
    const w = words[i], prev = cur[cur.length - 1];
    const len = cur.map((x) => x.text).join(" ").length;
    if (prev && (w.start - prev.end > 0.35 || len + w.text.length > 34 || cur.length >= 6 || w.seg !== prev.seg)) flush();
    cur.push(w);
    if (/[.?!]$/.test(w.text)) flush();
  }
  flush();
  captionsHTML = `<div id="captions" data-mode="normal">${capChunks.map((c, k) => `<div class="cap-chunk" id="cap${k}">${c.map((w, j) => `<span class="cw" id="cap${k}-${j}">${esc(w.text)}</span>`).join(" ")}</div>`).join("")}</div>`;
}

// ── sfx + music ────────────────────────────────────────────────────────
const sfxCfg = sb.sfx === true ? { whoosh: true, pop: true } : sb.sfx || {};
const audioTags = [];
let sfxN = 0;
const addSfx = (name, t, vol) => {
  const dst = path.join(assets, "sfx", `${name}.wav`);
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  if (!fs.existsSync(dst)) fs.copyFileSync(path.join(SKILL, "assets/sfx", `${name}.wav`), dst);
  const len = { whoosh: 0.6, pop: 0.18, tick: 0.03 }[name];
  if (t + len > DUR) return;
  audioTags.push(`<audio id="sfx${++sfxN}" src="assets/sfx/${name}.wav" data-start="${q(Math.max(0, t)).toFixed(4)}" data-duration="${len}" data-volume="${vol}" data-track-index="5"></audio>`);
};
for (const o of resolved) {
  if (sfxCfg.whoosh && ["screen", "chat", "callout", "title", "demo"].includes(o.type)) addSfx("whoosh", o.start - 0.12, sfxCfg.whooshVolume ?? 0.35);
  if (sfxCfg.pop && o.type === "bubbles") (o.items || []).forEach((_, k) => addSfx("pop", o.itemTimes[k] ?? o.start + 0.25 + k * 0.42, sfxCfg.popVolume ?? 0.4));
}
if (sb.music?.src) {
  const src = path.join(proj, sb.music.src);
  const dst = path.join(assets, "music.m4a");
  execFileSync("ffmpeg", ["-v", "error", "-y", "-i", src, "-t", String(DUR), "-af", `afade=t=in:d=1,afade=t=out:st=${Math.max(0, DUR - 2.5)}:d=2.5`, "-c:a", "aac", "-b:a", "192k", dst]);
  audioTags.push(`<audio id="music" src="assets/music.m4a" data-start="0" data-duration="${DUR}" data-volume="${sb.music.volume ?? 0.12}" data-track-index="6"></audio>`);
}

// ── fonts + static assets ──────────────────────────────────────────────
fs.mkdirSync(path.join(assets, "fonts"), { recursive: true });
let fontCSS = "";
const needFonts = new Set(["Inter-400-latin.woff2", "Inter-700-latin.woff2"]);
fontCSS += `@font-face{font-family:"Inter";src:url("assets/fonts/Inter-400-latin.woff2") format("woff2");font-weight:300 500;font-display:block}\n`;
fontCSS += `@font-face{font-family:"Inter";src:url("assets/fonts/Inter-700-latin.woff2") format("woff2");font-weight:501 900;font-display:block}\n`;
for (const [fam, list] of Object.entries(theme.fonts))
  for (const [file, weight] of list) {
    needFonts.add(file);
    fontCSS += `@font-face{font-family:"${fam}";src:url("assets/fonts/${file}") format("woff2");font-weight:${weight};font-display:block}\n`;
  }
for (const f of needFonts) fs.copyFileSync(path.join(SKILL, "assets/fonts", f), path.join(assets, "fonts", f));
fs.copyFileSync(path.join(SKILL, "assets/vendor/gsap.min.js"), path.join(assets, "gsap.min.js"));
const runtimeJS = fs.readFileSync(path.join(SKILL, "assets/runtime.js"), "utf8");
const baseCSS = fs.readFileSync(path.join(SKILL, "assets/base.css"), "utf8");
const rootVars = `:root{${Object.entries(vars).map(([k, v]) => `--${k}:${v}`).join(";")}}`;

// ── story payload for runtime.js ───────────────────────────────────────
const story = {
  duration: DUR, fps: FPS, width: W, height: H,
  faceMotion: sb.faceMotion ?? "drift",
  vars,
  segments: tlj.segments.map((s) => ({ out: s.out, face: s.face, zoom: s.zoom, kind: s.kind || "face", screen: s.screen || null })),
  screenStyle: sb.screenStyle || "framed",
  fadeOut: sb.fadeOut || 0,
  captionsOn: !!sb.captions,
  overlays: resolved.map((o) => {
    const { html, ...rest } = o;
    return rest;
  }),
  captions: capChunks.map((c) => ({ start: c[0].start, end: c[c.length - 1].end, segEnd: tlj.segments[c[0].seg]?.out[1] ?? DUR, words: c.map((w) => [w.start, w.end]) })),
};

const overlayHTML = resolved.map((o) => C[o.type].html(o, o.id)).join("\n");
// the shot markup sets o._vp (viewport px) — refresh payload after markup is built
story.overlays = resolved.map(({ html, ...rest }) => rest);

const page = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=${W}, height=${H}">
<title>${esc(sb.title || "talking-head video")}</title>
<style>
${fontCSS}${rootVars}
${baseCSS}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-width="${W}" data-height="${H}" data-duration="${DUR}">
<div id="screen-bg" class="layer"></div><div id="screen-shadow"></div>
<div id="face" class="layer"><div id="face-drift" class="layer"><video id="aroll" src="aroll.mp4" playsinline data-has-audio="true" data-start="0" data-duration="${DUR}" data-track-index="0"></video></div></div>
<div id="pip-ring"></div>
<div id="fade-black"></div>
${overlayHTML}
${captionsHTML}
${audioTags.join("\n")}
</div>
<script>window.__STORY = ${JSON.stringify(story)};</script>
<script src="assets/gsap.min.js"></script>
<script>
${runtimeJS}
</script>
</body>
</html>
`;
fs.writeFileSync(path.join(pub, "index.html"), page);
fs.writeFileSync(path.join(proj, "work/overlays.resolved.json"), JSON.stringify(story.overlays, null, 1));

console.log(`index.html: ${DUR.toFixed(2)}s, ${resolved.length} overlays${sb.captions ? `, ${capChunks.length} caption chunks` : ""}${audioTags.length ? `, ${audioTags.length} audio cues` : ""}`);
for (const o of resolved) console.log(`  ${o.id.padEnd(5)} ${o.type.padEnd(10)} ${o.start.toFixed(2).padStart(6)} → ${o.end.toFixed(2).padStart(6)}  ${(o.prompt || o.caption || o.name || (o.lines || []).join(" / ") || o.text || o.value || o.src || "").toString().slice(0, 60)}`);
