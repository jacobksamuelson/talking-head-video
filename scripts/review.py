# /// script
# requires-python = ">=3.10"
# dependencies = ["mlx-whisper", "opencv-python-headless<5", "numpy"]
# ///
"""Review every cut in the assembled A-roll before anyone watches it.

Run after polish.py (it re-listens to public/aroll.mp4 if that transcript is stale). For each
cut between segments it checks:

  ❌ word integrity  the words we meant to keep vs. what is actually heard around the cut.
                     A missing or changed word means a clipped word ("before" heard as "but");
                     an extra word means a sliver of a cut-out word ("So—").
  ❌ choppy          3+ cuts within 8 s on camera footage
  ❌ abrupt switch   screen ↔ camera with under 0.35 s between the last word and the cut
  ⚠️ mid-sentence    a jump within one take where the last kept word doesn't end a sentence
                     (the voice is still rising into words that were removed)
  ⚠️ no breath       under 0.15 s of air across a cut, so two clauses run together
  ⚠️ edge voice      speech-level sound in the last/first 40 ms of a piece (possible clip)
  ⚠️ dead air        a silence over 1.4 s that isn't a deliberate hold

Writes work/review.md and prints it. Fix every ❌; fix or knowingly accept every ⚠️.
Usage: uv run review.py <project_dir>
"""
import difflib
import json
import re
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import ingest  # noqa: E402
import polish  # noqa: E402

norm = lambda t: re.sub(r"[^a-z0-9']", "", t.lower())
mmss = lambda t: f"{int(t // 60)}:{t % 60:05.2f}"


def load_wav(path):
    w = wave.open(str(path))
    sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return x, sr


def rms_db(x, sr, a, b):
    seg = x[max(0, int(a * sr)): max(0, int(b * sr))]
    return 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9) if len(seg) else -99.0


def band_db(x, sr, t, win=0.03):
    """(broadband, >2.5 kHz) energy in dB around t. Fricatives like "f"/"s" are quiet broadband
    but loud up high; true silence is quiet in both."""
    a, b = int((t - win / 2) * sr), int((t + win / 2) * sr)
    if a < 0 or b > len(x) or b - a < 8:
        return -99.0, -99.0
    seg = x[a:b] * np.hanning(b - a)
    sp = np.abs(np.fft.rfft(seg)) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / sr)
    return 10 * np.log10(sp.sum() + 1e-12), 10 * np.log10(sp[f > 2500].sum() + 1e-12)


def main():
    proj = Path(sys.argv[1]).expanduser().resolve()
    work = proj / "work"
    tl = json.loads((work / "timeline.json").read_text())
    segs = tl["segments"]
    takes = {t["id"]: t for t in json.loads((work / "takes.json").read_text())}
    cuts = json.loads((proj / "cuts.json").read_text())
    by_id = {c.get("id"): c for c in cuts}

    # what we meant to keep: the filler-keeping transcript of each source take (same model and
    # prompt as the re-listen below, so the two compare cleanly), mapped onto the output timeline
    vsrc = {}
    for tid, t in takes.items():
        f = work / "transcript" / (re.sub(r"[^\w.-]+", "_", Path(t["file"]).stem) + ".verbatim.json")
        ws = [w for w in json.loads(f.read_text()) if not ingest.FILLER.match(w["text"])] if f.exists() else []
        # drop Whisper's hallucination loops on silence ("T-B, T-B, T-B, …")
        vsrc[tid] = [w for i, w in enumerate(ws) if sum(1 for v in ws[max(0, i - 3): i + 4] if norm(v["text"]) == norm(w["text"])) < 4]
    expected = []
    for s in segs:
        off = s["out"][0] - s["src"][0]
        for w in vsrc.get(s["take"], []):
            mid = (w["start"] + w["end"]) / 2
            if s["src"][0] <= mid <= s["src"][1] and not any(m[0] <= mid <= m[1] for m in s.get("mutes", [])):
                expected.append({"text": w["text"], "start": w["start"] + off, "end": w["end"] + off, "seg": s["i"]})
    expected.sort(key=lambda w: w["start"])
    removed_words = lambda take, a, b: [w for w in vsrc.get(take, []) if a < (w["start"] + w["end"]) / 2 < b]

    # what is actually heard (re-listen if the transcript is older than the A-roll)
    aroll = proj / "public" / "aroll.mp4"
    vb = work / "polish.verbatim.json"
    if not vb.exists() or vb.stat().st_mtime < aroll.stat().st_mtime:
        _, heard = polish.fillers_in(aroll, work)
    else:
        heard = json.loads(vb.read_text())
    heard = [w for w in heard if not ingest.FILLER.match(w["text"])]

    audio = {}
    for tid, t in takes.items():
        wav = work / "audio" / (re.sub(r"[^\w.-]+", "_", Path(t["file"]).stem) + ".wav")
        if wav.exists():
            x, sr = load_wav(wav)
            voiced = np.percentile([band_db(x, sr, c)[0] for c in np.linspace(1, max(1.5, len(x) / sr - 1), 400)], 95)
            audio[tid] = (x, sr, t.get("levels", {}).get("speech_db", -20), voiced)

    issues = []
    add = lambda sev, t, kind, msg: issues.append((sev, t, kind, msg))
    held = {s["i"]: any((by_id.get(p) or {}).get("holdAfter") for p in s["phrases"]) for s in segs}

    FILLERISH = {"um", "uh", "umm", "uhh", "er", "erm", "hmm", "mm", "pause"}
    ops = difflib.SequenceMatcher(None, [norm(w["text"]) for w in expected], [norm(w["text"]) for w in heard], autojunk=False).get_opcodes()
    for a, b in zip(segs, segs[1:]):
        T = a["out"][1]
        same_take = a["take"] == b["take"]
        jump = same_take and b["src"][0] - a["src"][1] > 0.05
        kind = "take switch" if not same_take else ("jump" if jump else "punch-in")
        labels = [r[2] if len(r) > 2 else "edit" for pid in set(a["phrases"]) | set(b["phrases"]) for r in (by_id.get(pid) or {}).get("remove", [])
                  if r[1] > a["src"][1] - 0.05 and r[0] < b["src"][0] + 0.05]
        filler_cut = jump and set(a["phrases"]) & set(b["phrases"]) and labels and all(l in FILLERISH or l.startswith("repeat") for l in labels)
        content_cut = (not same_take) or (jump and not filler_cut)

        # word integrity around the cut (from one global alignment, so window edges can't misalign)
        similar = lambda x, y: norm(x["text"])[:1] == norm(y["text"])[:1] and difflib.SequenceMatcher(None, norm(x["text"]), norm(y["text"])).ratio() >= 0.55
        for op, i1, i2, j1, j2 in ops:
            if op == "equal":
                continue
            if op == "replace" and i2 - i1 == j2 - j1 and all(similar(x, y) for x, y in zip(expected[i1:i2], heard[j1:j2])):
                continue  # same words, different spelling ("Soroosh" / "Sourouche")
            near = [w for w in expected[i1:i2] if abs(w["end"] - T) < 0.6 or abs(w["start"] - T) < 0.6]
            extra = [w for w in heard[j1:j2] if abs(w["start"] - T) < 0.6]
            if op in ("replace", "delete") and near:
                if op == "replace" and len(near) == 1 and any(similar(near[0], y) for y in heard[j1:j2]):
                    continue
                got = " ".join(w["text"] for w in heard[j1:j2]) or "nothing"
                add("❌", T, "clipped word", f"expected \"{' '.join(w['text'] for w in near)}\", heard \"{got}\" at the {kind}")
            elif op == "insert" and extra and content_cut:
                add("❌", T, "sliver", f"heard an extra \"{' '.join(w['text'] for w in extra)}\" at the {kind}: part of a removed word survived")

        # does a cut edge land inside a word in the source recording? (catches "be|fore": a
        # transcript of the result still reads "before" because Whisper fills the word back in)
        for side, tid, edge in (("end", a["take"], a["src"][1]), ("start", b["take"], b["src"][0])):
            if side == "start" and not content_cut and same_take:
                continue
            inside = [w for w in vsrc.get(tid, []) if w["start"] + 0.05 < edge < w["end"] - 0.05 and w["end"] - w["start"] < 1.0]
            if inside and tid in audio:
                x, sr, _, voiced = audio[tid]
                full, hi = band_db(x, sr, edge - 0.015 if side == "end" else edge + 0.015)
                if full < voiced - 20 and hi < voiced - 45:
                    inside = []  # the edge sits in true silence; the word's timestamp is just stretched
            for w in inside:
                sev = "❌" if content_cut else "⚠️"
                add(sev, T, "cut inside word", f"the {side} of a piece ({takes[tid]['name']} @ {edge:.2f}s) falls inside \"{w['text']}\" ({w['start']:.2f}–{w['end']:.2f}); move the cut to the silence after/before the word")

        before = [w for w in expected if w["end"] <= T + 0.05 and w["seg"] == a["i"]]
        after = [w for w in expected if w["start"] >= T - 0.05 and w["seg"] == b["i"]]
        last, first = (before[-1] if before else None), (after[0] if after else None)
        air = (T - last["end"] if last else 1.0) + (first["start"] - T if first else 1.0)
        hold = held.get(a["i"]) or a.get("hold")

        lead = (first["start"] - T) if first else 1.0
        if a["kind"] != b["kind"] and last and (T - last["end"]) + lead < 0.45:
            fix = "holdAfter (~0.6 s) on the screen phrase" if a["kind"] == "screen" else "padBefore (~0.5 s) on the next phrase, or holdAfter"
            add("❌", T, "abrupt switch", f"{a['kind']} → {b['kind']} with only {(T - last['end']) + lead:.2f}s between \"{last['text']}\" and \"{first['text'] if first else '…'}\"; add {fix}")
        if jump and content_cut and last and not re.search(r"[.?!]$", last["text"]):
            add("⚠️", T, "mid-sentence", f"words were cut after \"{last['text']}\" (no sentence end): the voice is mid-thought; end the kept part at a full stop")
        if air < 0.15 and not hold and content_cut:
            add("⚠️", T, "no breath", f"{air:.2f}s of air between \"{last['text'] if last else '…'}\" and \"{first['text'] if first else '…'}\"; add a gap to the remove entry")
        for side, tid, t0, t1 in (("end", a["take"], a["src"][1] - 0.04, a["src"][1]), ("start", b["take"], b["src"][0], b["src"][0] + 0.04)):
            if tid in audio and content_cut:
                x, sr, speech, _ = audio[tid]
                if rms_db(x, sr, t0, t1) > speech - 6:
                    add("⚠️", T, "edge voice", f"speech-level sound at the {side} of a piece ({takes[tid]['name']} @ {t0:.2f}s); check the cut isn't mid-word")

    # choppiness: cuts close together on camera
    face_cuts = [a["out"][1] for a, b in zip(segs, segs[1:]) if a["kind"] == "face" and b["kind"] == "face"]
    i = 0
    flagged = set()
    for j, t in enumerate(face_cuts):
        while face_cuts[i] < t - 8:
            i += 1
        if j - i + 1 >= 3 and i not in flagged:
            add("❌", face_cuts[i], "choppy", f"{j - i + 1} camera cuts between {mmss(face_cuts[i])} and {mmss(t)}; mute fillers instead of cutting, or cut a whole sentence")
            flagged.add(i)

    # dead air
    hw = sorted(heard, key=lambda w: w["start"])
    for p, n in zip(hw, hw[1:]):
        gap = n["start"] - p["end"]
        seg = next((s for s in segs if s["out"][0] <= p["end"] < s["out"][1]), None)
        if gap > 1.4 and not (seg and (held.get(seg["i"]) or seg.get("hold"))):
            add("⚠️", p["end"], "dead air", f"{gap:.1f}s silence after \"{p['text']}\"")

    issues.sort(key=lambda r: r[1])
    lines = [f"# Cut review: {len(segs) - 1} cuts, {sum(1 for r in issues if r[0] == '❌')} must-fix, {sum(1 for r in issues if r[0] == '⚠️')} to check", ""]
    lines += [f"- {sev} {mmss(t)} **{kind}**: {msg}" for sev, t, kind, msg in issues] or ["- ✅ no problems found"]
    (work / "review.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
