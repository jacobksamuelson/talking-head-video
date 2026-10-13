#!/usr/bin/env python3
"""Assemble the cut, framed, audio-polished A-roll from the kept phrases.

Reads   project.json, work/takes.json, cuts.json (falls back to work/phrases.json),
        storyboard.json (optional: framing pattern, grade, audio settings)
Writes  public/aroll.mp4         1920x1080 30fps, dense keyframes, -16 LUFS speech
        work/timeline.json       segments: source range → output range + framing
        work/words.edited.json   every kept word re-timed onto the edited timeline

Segments: consecutive kept phrases from the same take stay together (natural
pauses kept) unless the pause is longer than --max-pause, a dropped phrase sits
between them, or the next phrase asks for a different zoom (a punch-in). Each
new segment alternates framing (wide ↔ punched-in) so jump cuts read as edits.

Narrated screen recordings (takes with kind "screen") are fitted whole into the frame
instead of face-cropped, and keep silent stretches up to --max-pause-screen (3 s) so clicks
and typing survive; "joinNext": true on a phrase keeps everything up to the next phrase.

Per-phrase overrides in cuts.json: keep, zoom (relative to the take's base framing:
1.0 standard, 1.18 medium, 1.3–1.45 tight), faceX, faceY (where the face lands in the
output frame, 0–1), trimStart / trimEnd (seconds, + shortens).
Base framing is automatic: wide webcam footage is cropped so the face fills ~15.5% of
the frame width and sits right of center (storyboard framing.target/faceX/faceY).
Usage: python3 assemble.py <project_dir> [--max-pause 0.7] [--fast]
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

OUT_W, OUT_H, FPS = 1920, 1080, 30
PAD_IN, PAD_OUT = 0.12, 0.22

VOICE_CHAINS = {
    "none": "",
    "light": "highpass=f=75,afftdn=nr=6:nf=-50:tn=1,equalizer=f=250:t=q:w=1.2:g=-1.5,equalizer=f=3800:t=q:w=1.2:g=1.5,acompressor=threshold=-22dB:ratio=2.2:attack=8:release=140:makeup=1.5",
    "medium": "highpass=f=80,afftdn=nr=12:nf=-45:tn=1,equalizer=f=250:t=q:w=1.2:g=-2,equalizer=f=3800:t=q:w=1.2:g=2,deesser=i=0.3,acompressor=threshold=-22dB:ratio=3:attack=6:release=120:makeup=2",
}


def sh(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit("ffmpeg failed:\n" + " ".join(cmd) + "\n" + p.stderr[-2000:])
    return p


def load(path, default=None):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default


def base_crop(W, H):
    if W / H > OUT_W / OUT_H:
        return H * OUT_W / OUT_H, H
    return W, W * OUT_H / OUT_W


def plan_segments(phrases, takes, max_pause, pattern, max_pause_screen=3.0):
    kind = {t["id"]: t.get("kind", "face") for t in takes}
    kept = [p for p in phrases if p.get("keep", True)]
    by_take = {}
    for p in phrases:
        by_take.setdefault(p["take"], []).append(p)
    segs = []
    for p in kept:
        prev = segs[-1] if segs else None
        joined = False
        if prev and prev["take"] == p["take"]:
            last = prev["phrases"][-1]
            gap = p["start"] - last["end"]
            dropped_between = any(
                q["take"] == p["take"] and not q.get("keep", True) and q["start"] >= last["end"] - 0.01 and q["end"] <= p["start"] + 0.01
                for q in by_take[p["take"]]
            )
            zoom_change = "zoom" in p and abs(p["zoom"] - prev["zoom"]) > 0.01
            # screen recordings keep silent stretches (clicks, typing, page loads) up to 3 s;
            # "joinNext": true on a phrase keeps whatever follows it regardless of length
            limit = max_pause_screen if kind[p["take"]] == "screen" else max_pause
            if last.get("joinNext"):
                limit = 1e9
            if 0 <= gap <= limit and not dropped_between and not zoom_change and not p.get("cutBefore"):
                prev["phrases"].append(p)
                joined = True
        if not joined:
            i = len(segs)
            seg = {"take": p["take"], "phrases": [p], "zoom": p.get("zoom", pattern[i % len(pattern)]), "zoomExplicit": "zoom" in p}
            if "faceX" in p:
                seg["faceX"] = p["faceX"]
            if "faceY" in p:
                seg["faceY"] = p["faceY"]
            segs.append(seg)

    tk = {t["id"]: t for t in takes}
    for s in segs:
        first, last = s["phrases"][0], s["phrases"][-1]
        same = sorted(by_take[s["take"]], key=lambda q: q["start"])
        before = [q["end"] for q in same if q["end"] <= first["start"] + 0.01 and q is not first]
        after = [q["start"] for q in same if q["start"] >= last["end"] - 0.01 and q is not last]
        lo = (max(before) + 0.04) if before else 0.0
        hi = (min(after) - 0.04) if after else tk[s["take"]]["duration"]
        start = max(lo, first["start"] - PAD_IN - first.get("padBefore", 0)) + first.get("trimStart", 0)
        end = min(hi, last["end"] + PAD_OUT) - last.get("trimEnd", 0)
        # a punch-in split inside one continuous take: no padding into the neighbour
        start = max(start, 0.0)
        end = min(end, tk[s["take"]]["duration"])
        s["src"] = [round(start, 3), round(end, 3)]
    segs = split_removals(segs, pattern, {t["id"]: t.get("kind", "face") for t in takes})
    # contiguous punch-in splits must not overlap the previous segment
    for a, b in zip(segs, segs[1:]):
        if a["take"] == b["take"] and b["src"][0] < a["src"][1] and b["src"][0] > a["src"][0]:
            mid = round((a["phrases"][-1]["end"] + b["phrases"][0]["start"]) / 2, 3)
            a["src"][1], b["src"][0] = mid, mid
    return segs


def base_zoom(take, fr):
    """Crop that makes the face ~`target` of frame width (webcams are wide), keeping
    headroom for punch-ins. 1.0 when the footage is already framed (phone on a tripod)."""
    W, H = take["width"], take["height"]
    cw0, ch0 = base_crop(W, H)
    zmax = min(cw0 / OUT_W, ch0 / OUT_H) * 1.12
    face = take.get("face")
    if not face:
        return 1.0, zmax
    face_w = face["w"] * W / cw0
    return max(1.0, min(fr.get("target", 0.155) / face_w, zmax / 1.2)), zmax


FILLER_LABELS = {"um", "uh", "umm", "uhh", "er", "erm", "hmm", "mm"}


def split_removals(segs, pattern, kinds, edge=0.35):
    """Apply the per-phrase "remove" ranges (ums, doubled words, hesitations, hand edits).

    On camera footage, cutting out every "um" makes a run of jump cuts. So a filler or doubled
    word in the middle of a shot is silenced instead (picture continuous, a short pause in the
    audio), and hesitation "pause" ranges mid-shot are left alone. Only content edits and ranges
    at a shot's edges are cut; those mid-shot cuts flip the framing to hide the jump.
    Screen recordings cut every range (a jump in a screen recording isn't noticeable)."""
    out = []
    for s in segs:
        a0, b0 = s["src"]
        # entries: [start, end, label?, gap?] — gap = seconds of breath (held frame + silence) left at a cut
        rems = sorted((r[0], r[1], (r[2] if len(r) > 2 else "edit"), (r[3] if len(r) > 3 else 0.0)) for p in s["phrases"] for r in p.get("remove", []) if r[1] > a0 and r[0] < b0)
        face = kinds.get(s["take"]) == "face"
        cuts, mutes = [], []
        for a, b, label, gap in rems:
            mid_shot = a > a0 + edge and b < b0 - edge
            if face and mid_shot and (label in FILLER_LABELS or label.startswith("repeat")):
                # pad past the fade ramps, and merge with an overlapping range
                a, b = a - 0.04, b + 0.04
                if mutes and a <= mutes[-1][1]:
                    mutes[-1][1] = max(mutes[-1][1], b)
                else:
                    mutes.append([a, b])
            elif face and mid_shot and label == "pause":
                continue
            else:
                cuts.append([a, b, gap])
        pieces, holds, cur = [], [], a0
        for a, b, gap in cuts:
            if a - cur >= 0.2:
                pieces.append([cur, a])
                holds.append(gap)
            cur = max(cur, b)
        if b0 - cur >= 0.2:
            pieces.append([cur, b0])
            holds.append(0.0)
        alt = pattern[1] if abs(s["zoom"] - pattern[0]) < 0.01 and len(pattern) > 1 else pattern[0]
        for k, (a, b) in enumerate(pieces):
            q = dict(s)
            q["src"] = [round(a, 3), round(b, 3)]
            q["mutes"] = [m for m in mutes if m[0] >= a and m[1] <= b]
            q["hold"] = holds[k]
            if k % 2 == 1 and face and not s.get("zoomExplicit"):
                q["zoom"] = alt
            out.append(q)
    return out


def screen_fit(take):
    """Narrated screen recording: scale the whole capture to fit 1920x1080, centered."""
    W, H = take["width"], take["height"]
    k = min(OUT_W / W, OUT_H / H)
    ev = lambda v: int(round(v / 2) * 2)
    w, h = ev(W * k), ev(H * k)
    return {"w": w, "h": h, "x": (OUT_W - w) // 2, "y": (OUT_H - h) // 2}


def framing(seg, take, fr, warnings):
    """seg["zoom"] is relative to the take's base framing: 1.0 standard, ~1.18 medium, 1.3–1.45 tight."""
    W, H = take["width"], take["height"]
    cw0, ch0 = base_crop(W, H)
    base, zmax = base_zoom(take, fr)
    z = max(1.0, base * float(seg["zoom"]))
    if z > zmax + 1e-6:
        if seg.get("zoomExplicit"):  # the default wide/medium alternation clamps quietly on 1080p footage
            warnings.append(f"zoom {seg['zoom']} (x{base:.2f} base) on {take['name']} exceeds the sharp limit {zmax:.2f}x for {W}x{H}; clamped")
        z = max(1.0, zmax)
    face = take.get("face") or {"cx": 0.5, "cy": 0.4, "w": 0.2}
    fx, fy = face["cx"] * W, face["cy"] * H
    x_base, y_base = (W - cw0) / 2, (H - ch0) / 2
    # with spare picture to crop from, place the face right of center (room for cards on the left);
    # otherwise keep it where it was recorded
    croppable = base > 1.05
    tx = seg.get("faceX", fr.get("faceX", 0.6) if croppable else (fx - x_base) / cw0)
    ty = seg.get("faceY", fr.get("faceY", 0.42) if croppable else (fy - y_base) / ch0)
    cw, ch = cw0 / z, ch0 / z
    x0 = min(max(fx - tx * cw, 0), W - cw)
    y0 = min(max(fy - ty * ch, 0), H - ch)
    ev = lambda v: int(round(v / 2) * 2)
    crop = {"w": ev(cw), "h": ev(ch), "x": ev(x0), "y": ev(y0)}
    face_out = {
        "x": round((fx - crop["x"]) / crop["w"], 4),
        "y": round((fy - crop["y"]) / crop["h"], 4),
        "size": round(face["w"] * W / crop["w"], 4),
    }
    return z, crop, face_out


def cfr_proxy(take, work: Path):
    """Variable-frame-rate sources (macOS screen recordings emit frames only when the screen
    changes; phones vary too) seek inaccurately, so each cut would start late and the A-roll
    drifts out of sync with its audio. Convert once to a steady 30 fps file and cut from that."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate,avg_frame_rate", "-of", "csv=p=0", take["file"]], capture_output=True, text=True).stdout.strip()
    rates = {r for r in probe.replace("\n", ",").split(",") if r}
    steady = rates <= {f"{FPS}/1"} or rates <= {"30000/1001"}
    if take.get("kind") != "screen" and steady:
        return None
    src = Path(take["file"])
    out = work / "cfr" / (re.sub(r"[^\w.-]+", "_", src.stem) + ".mov")
    if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
        return str(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"converting {src.name} to a steady {FPS} fps proxy…", flush=True)
    sh(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "fast", "-crf", "12",
        "-g", str(FPS), "-keyint_min", str(FPS), "-sc_threshold", "0", "-c:a", "pcm_s16le", "-ar", "48000", str(out)])
    return str(out)


def take_loudness(take, work: Path):
    """Integrated loudness (LUFS) of a take's audio, cached. Gating skips the silences."""
    cache = work / "loudness.json"
    data = json.loads(cache.read_text()) if cache.exists() else {}
    src = take["file"]
    key = f"{src}|{Path(src).stat().st_mtime}"
    if key not in data:
        p = subprocess.run(["ffmpeg", "-v", "info", "-i", src, "-vn", "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True)
        m = re.findall(r"I:\s+(-?[\d.]+) LUFS", p.stderr)
        data[key] = float(m[-1]) if m else None
        cache.write_text(json.dumps(data, indent=1))
    return data[key]


def grade_filter(grade):
    if not grade:
        return ""
    parts = []
    eq = {k: grade[k] for k in ("contrast", "saturation", "brightness", "gamma") if k in grade}
    if eq:
        parts.append("eq=" + ":".join(f"{k}={v}" for k, v in eq.items()))
    if "temperature" in grade:
        parts.append(f"colortemperature=temperature={grade['temperature']}")
    if "lut" in grade:
        parts.append(f"lut3d=file='{grade['lut']}'")
    return ",".join(parts)


def mute_expr(mutes, s0, ramp=0.04):
    terms = []
    for a, b in mutes:
        m, h = (a + b) / 2 - s0, (b - a) / 2
        terms.append(f"max(0,min(1,(abs(t-{m:.3f})-{max(0.0, h - ramp):.3f})/{ramp}))")
    return "if(isnan(t),1," + "*".join(terms) + ")"  # ffmpeg evaluates once at init with t=NAN


def render_segment(i, seg, take, crop, grade, cache: Path, fast: bool, gain_db=0.0, hold=0.0):
    """hold: seconds of frozen last frame + silence appended (a beat before the next shot)."""
    s, e = seg["src"]
    src_frames = max(1, round((e - s) * FPS))
    src_dur = src_frames / FPS
    frames = src_frames + round(hold * FPS)
    dur = frames / FPS
    if take.get("kind") == "screen":
        # crop holds the fitted content rect; pad the rest (the composition frames it as a card)
        vf = f"fps={FPS},setpts=PTS-STARTPTS,scale={crop['w']}:{crop['h']}:flags=lanczos,pad={OUT_W}:{OUT_H}:{crop['x']}:{crop['y']}:color=0x0c0d14,setsar=1"
    else:
        vf = f"fps={FPS},setpts=PTS-STARTPTS,crop={crop['w']}:{crop['h']}:{crop['x']}:{crop['y']},scale={OUT_W}:{OUT_H}:flags=lanczos,setsar=1"
    g = grade_filter(grade) if take.get("kind") != "screen" else ""
    if g:
        vf += "," + g
    if hold > 0:
        vf = vf.replace("setpts=PTS-STARTPTS,", f"setpts=PTS-STARTPTS,trim=duration={src_dur:.6f},", 1)
        vf += f",tpad=stop_mode=clone:stop_duration={hold:.3f}"
    vf += ",format=yuv420p"
    mutes = seg.get("mutes") or []
    mute = f"volume='{mute_expr(mutes, s)}':eval=frame," if mutes else ""
    af = f"asetpts=PTS-STARTPTS,{mute}volume={gain_db:.2f}dB,aresample=48000,aformat=channel_layouts=mono,afade=t=in:d=0.015,atrim=0:{src_dur:.6f},afade=t=out:st={max(0, src_dur - 0.03):.6f}:d=0.03,apad,atrim=0:{dur:.6f}"
    src = take.get("proxy") or take["file"]
    key = hashlib.md5(json.dumps([src, s, frames, vf, af, fast, hold]).encode()).hexdigest()[:12]
    out = cache / f"seg_{i:03d}_{key}.mov"
    if not out.exists():
        sh([
            "ffmpeg", "-v", "error", "-y", "-ss", f"{s:.3f}", "-t", f"{src_dur + 0.2:.3f}", "-i", src,
            "-vf", vf, "-af", af, "-frames:v", str(frames),
            "-c:v", "libx264", "-preset", "veryfast" if fast else "medium", "-crf", "20" if fast else "14",
            "-g", str(FPS), "-keyint_min", str(FPS), "-sc_threshold", "0",
            "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1", str(out),
        ])
    return out, dur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--max-pause", type=float, default=0.7)
    ap.add_argument("--max-pause-screen", type=float, default=3.0, help="silence kept inside narrated screen recordings")
    ap.add_argument("--fast", action="store_true", help="quicker, lower-quality encode for drafts")
    args = ap.parse_args()
    proj = Path(args.project).expanduser().resolve()
    work, public = proj / "work", proj / "public"
    public.mkdir(exist_ok=True)
    takes = load(work / "takes.json")
    if not takes:
        sys.exit("Run ingest.py first.")
    cuts_path = proj / "cuts.json" if (proj / "cuts.json").exists() else work / "phrases.json"
    phrases = load(cuts_path)
    sb = load(proj / "storyboard.json", {}) or {}
    fr = sb.get("framing", {})
    pattern = fr.get("pattern", [1.0, 1.18])
    audio_cfg = sb.get("audio", {})
    voice = audio_cfg.get("voice", "light")
    lufs = audio_cfg.get("lufs", -16)

    tk = {t["id"]: t for t in takes}
    for t in takes:
        t["proxy"] = cfr_proxy(t, work)
    # takes recorded on different mics or apps come in at different levels; match them before joining
    used = {p["take"] for p in phrases if p.get("keep", True)}
    lufs_by_take = {tid: take_loudness(tk[tid], work) for tid in used}
    known = {k: v for k, v in lufs_by_take.items() if v is not None and v > -70}
    ref = max(known.values()) if known else None
    gains = {k: max(-12.0, min(18.0, ref - v)) for k, v in known.items()} if ref is not None else {}
    for k, g in gains.items():
        if abs(g) >= 1.0:
            print(f"level match: {tk[k]['name']} {known[k]:.1f} LUFS → {g:+.1f} dB")
    warnings = []
    segs = plan_segments(phrases, takes, args.max_pause, pattern, args.max_pause_screen)
    cache = work / "segs"
    cache.mkdir(exist_ok=True)
    files, out_t, timeline, words_out = [], 0.0, [], []
    for i, seg in enumerate(segs):
        take = tk[seg["take"]]
        kind = take.get("kind", "face")
        if kind == "screen":
            z, crop, face_out = 1.0, screen_fit(take), None
        else:
            z, crop, face_out = framing(seg, take, fr, warnings)
        # "mute": true on a phrase silences its segment (a held title card over clicks and breaths)
        mute = any(p.get("mute") for p in seg["phrases"])
        hold = max([p.get("holdAfter", 0) for p in seg["phrases"] if p is seg["phrases"][-1]] + [0])
        if i + 1 < len(segs) and segs[i + 1]["phrases"][-1] is seg["phrases"][-1]:
            hold = 0  # the phrase continues in the next piece; hold only after its last piece
        hold = max(hold, seg.get("hold", 0.0))
        f, dur = render_segment(i, seg, take, crop, sb.get("grade"), cache, args.fast, -91.0 if mute else gains.get(seg["take"], 0.0), hold)
        files.append(f)
        s0 = seg["src"][0]
        timeline.append({
            "i": i, "take": seg["take"], "kind": kind, "src": seg["src"], "out": [round(out_t, 4), round(out_t + dur, 4)],
            "zoom": round(z, 3), "crop": crop, "face": face_out, "phrases": [p["id"] for p in seg["phrases"]],
            "screen": {k: round(v / (OUT_W if k in "xw" else OUT_H), 4) for k, v in crop.items()} if kind == "screen" else None,
            "mutes": seg.get("mutes") or [], "hold": round(hold, 3),
            "text": " ".join(p["text"] for p in seg["phrases"]),
        })
        for p in seg["phrases"]:
            for w in p.get("words", []):
                # a word belongs to this piece if its midpoint is inside it (start times drift early)
                if seg["src"][0] - 0.05 <= (w["start"] + w["end"]) / 2 <= seg["src"][1] + 0.05:
                    words_out.append({
                        "text": w["text"], "seg": i, "phrase": p["id"],
                        "start": round(out_t + max(0.0, w["start"] - s0), 3),
                        "end": round(out_t + min(dur, w["end"] - s0), 3),
                    })
        out_t += dur
        print(f"seg {i:02d} {seg['take']} {seg['src'][0]:7.2f}–{seg['src'][1]:7.2f} → {timeline[-1]['out'][0]:6.2f}  zoom {z:.2f}  | {timeline[-1]['text'][:70]}")

    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{f}'\n" for f in files))
    joined = work / "aroll_joined.mov"
    sh(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])

    chain = VOICE_CHAINS.get(voice, voice)
    pre = (chain + ",") if chain else ""
    p1 = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(joined), "-vn", "-af", f"{pre}loudnorm=I={lufs}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p1.stderr, re.S)
    if not m:
        sys.exit("loudnorm measure failed:\n" + p1.stderr[-1500:])
    meas = json.loads(m.group(0))
    ln = (
        f"loudnorm=I={lufs}:TP=-1.5:LRA=11:measured_I={meas['input_i']}:measured_TP={meas['input_tp']}"
        f":measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}:offset={meas['target_offset']}:linear=true"
    )
    sh([
        "ffmpeg", "-v", "error", "-y", "-i", str(joined), "-c:v", "copy",
        "-af", f"{pre}{ln},aresample=48000", "-ac", "2", "-c:a", "aac", "-b:a", "256k",
        "-movflags", "+faststart", str(public / "aroll.mp4"),
    ])
    (work / "timeline.json").write_text(json.dumps({"fps": FPS, "width": OUT_W, "height": OUT_H, "duration": round(out_t, 4), "segments": timeline}, indent=1))
    (work / "words.edited.json").write_text(json.dumps(words_out, indent=1))
    print(f"\naroll.mp4: {out_t:.2f}s, {len(segs)} segments, loudness {meas['input_i']} → {lufs} LUFS (voice={voice})")
    for w in warnings:
        print("WARNING:", w)


if __name__ == "__main__":
    main()
