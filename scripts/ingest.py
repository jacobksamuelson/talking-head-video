# /// script
# requires-python = ">=3.10"
# dependencies = ["mlx-whisper", "opencv-python-headless<5", "numpy"]
# ///
"""Ingest raw camera takes for a talking-head video project.

For every video in <project>/raw/ (camera takes AND narrated screen recordings) this:
  1. probes it (size, rotation, fps, HDR, audio)
  2. finds speech with an adaptive energy detector (VAD) and groups it into
     chunks separated by pauses
  3. transcribes each chunk separately with word timestamps (MLX Whisper).
     Chunking stops Whisper from silently merging a false start with its
     restart, which is what makes retake detection possible.
  4. finds the face position (OpenCV, median over sampled frames)
Then it proposes which phrases to keep: retakes (a phrase restarted soon
after), filler-only phrases and slate chatter are marked DROP.

Writes  work/takes.json  work/phrases.json  and prints a readable table.
Usage:  uv run ingest.py <project_dir> [--gap 0.5] [--model ...]
        uv run ingest.py --check <test_clip.mov>     # setup check: framing, light, audio
"""
import argparse
import difflib
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

VIDEO_EXT = {".mov", ".mp4", ".m4v", ".mkv", ".webm"}
FILLERS = {"um", "uh", "uhm", "erm", "hmm", "mm", "ah", "like", "so", "okay", "ok", "alright", "right", "yeah", "and"}
SLATE_PATTERNS = [
    r"\btake (one|two|three|four|five|\d+)\b",
    r"\blet me (try|do) (that|this|it) again\b",
    r"\b(one more|try that) (time|again)\b",
    r"\bstart (that )?over\b",
    r"\b(i'll|let me|i'm gonna|i'm going to) (start|do (that|this|it)) again\b",
    r"\bstart again\b",
    r"\b(are we|is it|we're) (rolling|recording)\b",
    r"\bcut that\b",
]


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def probe(path: Path) -> dict:
    info = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]).stdout)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(round(float(sd["rotation"])))
    if "rotate" in (v.get("tags") or {}):
        rot = int(v["tags"]["rotate"])
    w, h = int(v["width"]), int(v["height"])
    if abs(rot) % 180 == 90:
        w, h = h, w
    num, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den) if float(den or 0) else 30.0
    transfer = v.get("color_transfer", "")
    return {
        "width": w, "height": h, "rotation": rot, "fps": round(fps, 3),
        "duration": float(info["format"]["duration"]),
        "codec": v.get("codec_name"), "pix_fmt": v.get("pix_fmt"),
        "color_transfer": transfer, "hdr": transfer in ("arib-std-b67", "smpte2084"),
        "has_audio": a is not None,
    }


def extract_audio(src: Path, dst: Path):
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(dst)])


def vad(wav: Path, hop_s=0.02, fill=0.2, min_len=0.05):
    """Adaptive energy VAD → list of [start, end] speech regions (seconds)."""
    w = wave.open(str(wav))
    sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    hop = int(sr * hop_s)
    n = len(x) // hop
    if n == 0:
        return [], {}
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-10)
    db = 20 * np.log10(rms)
    noise, speech = float(np.percentile(db, 10)), float(np.percentile(db, 95))
    thr = noise + 0.4 * (speech - noise)
    on = db > thr
    regions, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        elif not v and start is not None:
            regions.append([start * hop_s, i * hop_s])
            start = None
    if start is not None:
        regions.append([start * hop_s, n * hop_s])
    merged = []
    for r in regions:
        if merged and r[0] - merged[-1][1] < fill:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    merged = [[round(a, 3), round(b, 3)] for a, b in merged if b - a >= min_len]
    return merged, {"noise_db": round(noise, 1), "speech_db": round(speech, 1), "snr_db": round(speech - noise, 1)}


def chunk_regions(regions, gap):
    chunks = []
    for r in regions:
        if chunks and r[0] - chunks[-1][1] < gap:
            chunks[-1][1] = r[1]
        else:
            chunks.append(list(r))
    return chunks


def transcribe(wav: Path, chunks, out: Path, model: str, prompt):
    """Word-level transcript of each speech chunk (cached at `out`)."""
    if out.exists():
        return json.loads(out.read_text())
    import mlx_whisper

    clips = []
    for a, b in chunks:
        clips += [max(0.0, a - 0.08), b + 0.12]
    res = mlx_whisper.transcribe(
        str(wav), path_or_hf_repo=model, word_timestamps=True, initial_prompt=prompt,
        condition_on_previous_text=False, language="en", clip_timestamps=clips,
        hallucination_silence_threshold=1.0,
    )
    words = []
    for seg in res.get("segments", []):
        for w in seg.get("words", []):
            t = w["word"].strip()
            if t:
                words.append({"text": t, "start": round(w["start"], 3), "end": round(w["end"], 3), "p": round(w.get("probability", 1.0), 3)})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(words, indent=1))
    return words


VERBATIM_PROMPT = "Umm, uh, so, like, I mean, uh... okay. Um, yeah, uh, the the, um."
FILLER = re.compile(r"^(um+|uh+|erm?|hmm+|mm+)[,.?!…]*$", re.I)


def find_disfluencies(words, breath=0.06, max_pause=0.6, screen=False):
    """From a verbatim transcript (Whisper prompted to keep fillers), return source ranges to cut:
    fillers (um/uh) with the pauses around them, the first of a doubled word ("the the"),
    and the middle of hesitations longer than max_pause. Each range keeps `breath` s of air.
    Screen recordings: cut only the filler sound and keep pauses (they're often a click or a page load)."""
    out = []
    norm = lambda t: re.sub(r"[^a-z0-9']", "", t.lower())
    for i, w in enumerate(words):
        prev = words[i - 1] if i else None
        nxt = words[i + 1] if i + 1 < len(words) else None
        if FILLER.match(w["text"]) and screen:
            out.append([round(w["start"] - 0.03, 3), round(w["end"] + 0.04, 3), w["text"].strip(",.?!").lower()])
        elif FILLER.match(w["text"]):
            # Whisper's word ends run early: leave more room after the previous word than before the next
            a = prev["end"] + 2 * breath if prev and w["start"] - prev["end"] < 1.0 else w["start"] - 0.03
            b = nxt["start"] - breath if nxt and nxt["start"] - w["end"] < 1.0 else w["end"] + 0.05
            out.append([round(a, 3), round(max(b, a + 0.05), 3), w["text"].strip(",.?!").lower()])
        elif nxt and norm(w["text"]).isalpha() and norm(w["text"]) == norm(nxt["text"]) and len(norm(w["text"])) <= 6:
            out.append([round(w["start"] - 0.02, 3), round(nxt["start"] - 0.02, 3), f"repeat '{norm(w['text'])}'"])
        elif not screen and nxt and nxt["start"] - w["end"] > max_pause and not FILLER.match(nxt["text"]):
            out.append([round(w["end"] + 0.2, 3), round(nxt["start"] - 0.15, 3), "pause"])
    return out


def load_mono(wav: Path):
    w = wave.open(str(wav))
    return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768, w.getframerate()


def snap_quiet(x, sr, t, radius=0.12, win=0.02):
    """Move a cut point to the quietest 20 ms within ±radius. Word timestamps are approximate,
    and a cut that lands in a voiced sound clips it (the "t" of "but", the "-fore" of "before")."""
    hop = int(sr * 0.005)
    best, best_t = 1e9, t
    for c in np.arange(t - radius, t + radius, 0.005):
        a, b = int((c - win / 2) * sr), int((c + win / 2) * sr)
        if a < 0 or b > len(x):
            continue
        e = float(np.mean(x[a:b] ** 2))
        if e < best:
            best, best_t = e, c
    return round(float(best_t), 3)


def snap_ranges(ranges, x, sr):
    out = []
    for r in ranges:
        a, b = snap_quiet(x, sr, r[0]), snap_quiet(x, sr, r[1])
        if b - a >= 0.05:
            out.append([a, b] + list(r[2:]))
    return out


def transcribe_verbatim(wav: Path, chunks, out: Path, model: str, prompt: str):
    """Filler-keeping transcript. Whisper only applies an initial prompt to its first 30 s
    window, so each speech chunk gets its own call (the model stays loaded between calls)."""
    if out.exists():
        return json.loads(out.read_text())
    import mlx_whisper

    w = wave.open(str(wav))
    sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    words = []
    for a, b in chunks:
        s0 = max(0.0, a - 0.08)
        clip = x[int(s0 * sr): int((b + 0.12) * sr)]
        if len(clip) < sr * 0.15:
            continue
        res = mlx_whisper.transcribe(clip, path_or_hf_repo=model, word_timestamps=True, initial_prompt=prompt,
                                     condition_on_previous_text=False, language="en")
        for seg in res.get("segments", []):
            for t in seg.get("words", []):
                txt = t["word"].strip()
                if txt:
                    words.append({"text": txt, "start": round(s0 + t["start"], 3), "end": round(s0 + t["end"], 3)})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(words, indent=1))
    return words


def find_face(src: Path, meta: dict, tmp: Path):
    import cv2

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    boxes = []
    tmp.mkdir(parents=True, exist_ok=True)
    for i in range(9):
        t = meta["duration"] * (0.06 + 0.88 * i / 8)
        f = tmp / f"probe_{i}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1", "-vf", "scale=960:-2", str(f)], capture_output=True)
        img = cv2.imread(str(f))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        H, W = gray.shape
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(W // 14, W // 14))
        if len(faces):
            x, y, w, h = max(faces, key=lambda b: b[2] * b[3])
            boxes.append(((x + w / 2) / W, (y + h / 2) / H, w / W, h / H))
    if not boxes:
        return None
    cx, cy, fw, fh = np.median(np.array(boxes), axis=0)
    return {"cx": round(float(cx), 4), "cy": round(float(cy), 4), "w": round(float(fw), 4), "h": round(float(fh), 4), "samples": len(boxes)}


def norm_tokens(text: str):
    return [t for t in re.sub(r"[^a-z0-9' ]+", " ", text.lower()).split() if t]


def build_phrases(take: str, chunks, words):
    """One phrase per VAD chunk; long chunks also split at sentence ends."""
    out = []
    for a, b in chunks:
        ws = [w for w in words if w["start"] < b + 0.1 and w["end"] > a - 0.1]
        if not ws:
            out.append({"take": take, "start": a, "end": b, "text": "", "words": []})
            continue
        groups, cur = [], [ws[0]]
        for w in ws[1:]:
            if cur[-1]["text"][-1:] in ".?!" and w["start"] - cur[-1]["end"] >= 0.25:
                groups.append(cur)
                cur = []
            cur.append(w)
        groups.append(cur)
        for gi, g in enumerate(groups):
            # VAD can miss a soft first/last syllable; Whisper can drift. Take the union.
            s = min(a, g[0]["start"]) if gi == 0 else g[0]["start"] - 0.05
            e = max(b, g[-1]["end"]) if gi == len(groups) - 1 else g[-1]["end"] + 0.05
            out.append({"take": take, "start": round(s, 3), "end": round(e, 3), "text": " ".join(w["text"] for w in g), "words": g})
    return out


def mark_drops(phrases):
    for i, ph in enumerate(phrases):
        ph["keep"], ph["reason"] = True, ""
        toks = norm_tokens(ph["text"])
        if not toks:
            ph["keep"], ph["reason"] = False, "no words"
            continue
        if all(t in FILLERS for t in toks):
            ph["keep"], ph["reason"] = False, "filler"
            continue
        if any(re.search(p, ph["text"].lower()) for p in SLATE_PATTERNS):
            ph["keep"], ph["reason"] = False, "slate/chatter"
            continue
        for j in range(i + 1, min(i + 5, len(phrases))):
            nx = phrases[j]
            if nx["take"] != ph["take"] or nx["start"] - ph["end"] > 45:
                break
            nt = norm_tokens(nx["text"])
            if not nt:
                continue
            k = min(len(toks), len(nt), 8)
            head_same = k >= 3 and toks[:3] == nt[:3]
            ratio = difflib.SequenceMatcher(None, toks[:k], nt[:k]).ratio() if k >= 3 else 0
            fragment = len(toks) <= 4 and nt[: len(toks)] == toks
            if head_same or ratio >= 0.75 or fragment:
                ph["keep"], ph["reason"] = False, f"retake → #{j}"
                break
    return phrases


def check_setup(path: Path):
    """Fast setup check on a short test clip: resolution, HDR, framing, exposure, audio."""
    import tempfile

    meta = probe(path)
    tmp = Path(tempfile.mkdtemp())
    face = find_face(path, meta, tmp)
    wav = tmp / "a.wav"
    extract_audio(path, wav)
    _, lv = vad(wav)
    w = wave.open(str(wav))
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    peak = float(np.abs(x).max()) / 32768 if len(x) else 0
    yavg = subprocess.run(
        ["ffmpeg", "-v", "info", "-ss", f"{meta['duration'] / 2:.2f}", "-i", str(path), "-frames:v", "1", "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    m = re.search(r"YAVG=([\d.]+)", yavg)
    luma = float(m.group(1)) if m else None
    bits = 10 if "10" in (meta.get("pix_fmt") or "") else 12 if "12" in (meta.get("pix_fmt") or "") else 8
    if luma is not None:
        luma = luma / (2 ** (bits - 8))
    rows = []
    def row(ok, label, msg):
        rows.append(("✅" if ok == 1 else "⚠️ " if ok == 0 else "❌", label, msg))
    W, H = meta["width"], meta["height"]
    row(1 if min(W, H) >= 2160 else 0 if min(W, H) >= 1080 else -1, "Resolution", f"{W}x{H} — {'4K, room to punch in' if min(W, H) >= 2160 else 'record 4K for sharp punch-ins'}")
    row(-1 if W < H else 1, "Orientation", "landscape" if W >= H else "portrait — turn the phone sideways")
    row(-1 if meta["hdr"] else 1, "HDR", "HDR is ON — turn it off (Settings › Camera › Record Video › HDR Video)" if meta["hdr"] else "SDR, good")
    row(1 if 29 <= meta["fps"] <= 30.5 else 0, "Frame rate", f"{meta['fps']} fps {'(good)' if 29 <= meta['fps'] <= 30.5 else '— 30 fps preferred'}")
    if face:
        cx, cy, fw = face["cx"], face["cy"], face["w"]
        cw0 = min(W, H * 16 / 9)
        zmax = min(cw0 / 1920, (cw0 * 9 / 16) / 1080) * 1.12
        need = 0.155 / (fw * W / cw0)          # crop needed so the face fills ~15.5% of the frame
        croppable = 1.05 < need <= zmax / 1.2
        if need < 0.55:
            row(0, "Distance", f"face is {fw:.0%} of frame width — too close (wide lenses distort faces up close): sit back ~20 cm")
        elif need <= 1.2 and not croppable:
            row(1, "Distance", f"face is {fw:.0%} of frame width — good")
        elif need <= 1.05:
            row(1, "Distance", f"face is {fw:.0%} of frame width — good")
        elif croppable:
            row(1, "Distance", f"face is {fw:.0%} of frame width — fine, the editor crops in {need:.1f}x and stays sharp")
        else:
            row(0, "Distance", f"face is only {fw:.0%} of frame width and this camera can't crop in that far sharply — sit closer (about arm's length)")
        if croppable:
            row(1, "Face position", f"{cx:.0%} across — fine, the editor will place you right of center")
        else:
            row(1 if 0.55 <= cx <= 0.7 else 0, "Face position", f"{cx:.0%} across — {'good, cards fit on your left' if 0.55 <= cx <= 0.7 else 'shift so you sit ~62% across (right third); cards go on the left'}")
        if not croppable:
            row(1 if 0.3 <= cy <= 0.48 else 0, "Eye line", f"face center {cy:.0%} down — {'good' if 0.3 <= cy <= 0.48 else ('a bit low in frame: tilt the camera down slightly or sit up taller' if cy > 0.48 else 'too high in frame: tilt the camera up slightly')}")
        elif cy > 0.62 or cy < 0.18:
            row(0, "Eye line", f"face center {cy:.0%} down — near the edge; tilt the camera so you're closer to the middle")
    else:
        row(-1, "Face", "no face found — check you're in frame and lit from the front")
    if luma is not None:
        row(1 if 85 <= luma <= 170 else 0, "Exposure", f"average brightness {luma:.0f}/255 — {'good' if 85 <= luma <= 170 else ('dark: add light in front of you' if luma < 85 else 'bright: lower exposure / move away from the window')}")
    snr = lv.get("snr_db", 0)
    row(1 if snr >= 28 else 0 if snr >= 18 else -1, "Audio noise", f"voice is {snr} dB above the room — {'clean' if snr >= 28 else 'okay, a lav mic will help' if snr >= 18 else 'noisy: use a lav mic or a quieter room'}")
    pk = 20 * np.log10(max(peak, 1e-6))
    row(-1 if peak > 0.98 else 0 if pk < -24 else 1, "Audio level", "clipping — lower the mic gain" if peak > 0.98 else f"peak {pk:.1f} dBFS — {'very quiet: raise mic gain or move the mic closer' if pk < -24 else 'good'}")
    print(f"Setup check: {path.name} ({meta['duration']:.1f}s)\n")
    for icon, label, msg in rows:
        print(f"{icon} {label:<14} {msg}")


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--check":
        check_setup(Path(sys.argv[2]).expanduser())
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--model", default="mlx-community/whisper-large-v3-turbo")
    ap.add_argument("--gap", type=float, default=0.5, help="pause (s) that starts a new phrase")
    ap.add_argument("--retranscribe", action="store_true")
    args = ap.parse_args()

    proj = Path(args.project).expanduser().resolve()
    work = proj / "work"
    work.mkdir(exist_ok=True)
    cfg = json.loads((proj / "project.json").read_text()) if (proj / "project.json").exists() else {}
    vocab = cfg.get("vocab") or []
    prompt = ("Vocabulary: " + ", ".join(vocab) + ".") if vocab else None

    # project.json → "exclude": ["old take.mov"] skips superseded recordings without deleting them
    skip = set(cfg.get("exclude") or [])
    vids = sorted(p for p in (proj / "raw").iterdir() if p.suffix.lower() in VIDEO_EXT and not p.name.startswith(".") and p.name not in skip)
    if not vids:
        sys.exit(f"No videos in {proj / 'raw'}")

    takes, phrases, warnings = [], [], []
    for idx, v in enumerate(vids):
        tid = f"t{idx + 1}"
        print(f"[{tid}] {v.name}: probing…", flush=True)
        meta = probe(v)
        if not meta["has_audio"]:
            warnings.append(f"{v.name} has no audio track — skipped.")
            continue
        # caches are keyed by file, not take number: adding a file can renumber the takes
        key = re.sub(r"[^\w.-]+", "_", v.stem)
        wav = work / "audio" / f"{key}.wav"
        extract_audio(v, wav)
        regions, levels = vad(wav)
        chunks = chunk_regions(regions, args.gap)
        tjson = work / "transcript" / f"{key}.json"
        if args.retranscribe and tjson.exists():
            tjson.unlink()
        print(f"[{tid}] transcribing {len(chunks)} chunks ({meta['duration']:.0f}s)…", flush=True)
        words = transcribe(wav, chunks, tjson, args.model, prompt)
        # second pass that keeps "um"/"uh" (Whisper drops them by default) → cut list
        vjson = work / "transcript" / f"{key}.verbatim.json"
        if args.retranscribe and vjson.exists():
            vjson.unlink()
        verbatim = transcribe_verbatim(wav, chunks, vjson, args.model, VERBATIM_PROMPT + (" " + prompt if prompt else ""))
        is_screen_name = bool(re.search(r"screen ?recording|^screen[-_ ]|^scr[-_]", v.name, re.I))
        face = None if is_screen_name else find_face(v, meta, work / "probe" / key)
        # kind: a camera take ("face") or a narrated screen recording ("screen"). Override in
        # project.json → "kinds": {"<filename>": "face" | "screen"}
        kind = (cfg.get("kinds") or {}).get(v.name) or ("screen" if is_screen_name or face is None else "face")
        if face is None and kind == "screen" and not is_screen_name:
            warnings.append(f"{v.name}: no face found, so it's treated as a screen recording. If it's a camera take, set \"kinds\": {{\"{v.name}\": \"face\"}} in project.json.")
        if meta["hdr"]:
            warnings.append(f"{v.name} is HDR ({meta['color_transfer']}): colors will be off. Re-record with HDR off (see RECORDING.md).")
        if kind == "face" and min(meta["width"], meta["height"]) < 1200:
            warnings.append(f"{v.name} is {meta['width']}x{meta['height']}: no room to crop in — framing stays as recorded and punch-ins will look soft.")
        if kind == "face" and meta["width"] < meta["height"]:
            warnings.append(f"{v.name} is portrait; 16:9 output expects landscape footage.")
        if levels.get("snr_db", 99) < 18:
            warnings.append(f"{v.name}: speech is only {levels['snr_db']} dB above the background — expect noise; a lav mic fixes this.")
        takes.append({"id": tid, "file": str(v), "name": v.name, "kind": kind, **meta, "face": face, "levels": levels, "speech": regions})
        new = build_phrases(tid, chunks, words)
        disfl = find_disfluencies(verbatim, screen=(kind == "screen"))
        disfl = snap_ranges(disfl, *load_mono(wav))
        # a "pause" is only cut if the voice detector agrees it's silent (Whisper can lose a word)
        heard = lambda r: sum(max(0.0, min(e, r[1]) - max(s0, r[0])) for s0, e in regions)
        disfl = [r for r in disfl if r[2] != "pause" or heard(r) < 0.12]
        for ph in new:
            rm = [r for r in disfl if r[1] > ph["start"] and r[0] < ph["end"]]
            if rm:
                ph["remove"] = rm
        phrases += new

    phrases = mark_drops(phrases)
    for i, ph in enumerate(phrases):
        ph["id"] = i
    (work / "takes.json").write_text(json.dumps(takes, indent=1))
    (work / "phrases.json").write_text(json.dumps(phrases, indent=1))

    print()
    for t in takes:
        f = t["face"]
        fs = f"face@({f['cx']:.2f},{f['cy']:.2f}) w={f['w']:.2f}" if f else "face=?"
        if t["kind"] == "screen":
            fs = "SCREEN RECORDING"
        print(f"{t['id']}: {t['name']}  {t['width']}x{t['height']} {t['fps']}fps {t['duration']:.1f}s  {fs}  snr={t['levels'].get('snr_db')}dB")
    print()
    kept = 0.0
    for ph in phrases:
        flag = "KEEP" if ph["keep"] else f"DROP({ph['reason']})"
        if ph.get("remove") and ph["keep"]:
            labels = [r[2] for r in ph["remove"]]
            flag += " −" + ",".join(sorted(set(labels), key=labels.index))
        if ph["keep"]:
            kept += ph["end"] - ph["start"]
        print(f"#{ph['id']:<3} {ph['take']} {ph['start']:7.2f}–{ph['end']:7.2f}  {flag:<18} {ph['text']}")
    print(f"\n≈{kept:.1f}s of speech kept from {sum(t['duration'] for t in takes):.1f}s recorded")
    for w in warnings:
        print("WARNING:", w)


if __name__ == "__main__":
    main()
