# /// script
# requires-python = ">=3.10"
# dependencies = ["mlx-whisper", "opencv-python-headless<5", "numpy"]
# ///
"""Remove the "um"s and "uh"s that survived the first cut.

Whisper is inconsistent about writing fillers down, so a single pass at ingest misses some.
This listens to the assembled A-roll (public/aroll.mp4) with a filler-keeping prompt, maps
each filler it hears back to its source take, adds it to that phrase's "remove" list in
cuts.json, re-assembles, and repeats until none are left (max 3 rounds).

Usage: uv run polish.py <project_dir> [--rounds 3] [--fast]
"""
import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ingest  # noqa: E402

MODEL = "mlx-community/whisper-large-v3-turbo"


def fillers_in(aroll: Path, work: Path):
    wav, out = work / "polish.wav", work / "polish.verbatim.json"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(aroll), "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)
    out.unlink(missing_ok=True)
    regions, _ = ingest.vad(wav)
    words = ingest.transcribe_verbatim(wav, ingest.chunk_regions(regions, 0.5), out, MODEL, ingest.VERBATIM_PROMPT)
    return [w for w in words if ingest.FILLER.match(w["text"])], words


def retime_words(work: Path, heard):
    """Re-time words.edited.json (corrected spellings) from what the finished cut actually
    contains. First-pass timestamps drift near cuts, which can drop a word that's still audible
    or misplace an overlay anchor."""
    path = work / "words.edited.json"
    orig = json.loads(path.read_text())
    segs = json.loads((work / "timeline.json").read_text())["segments"]
    seg_at = lambda t: next((s["i"] for s in segs if s["out"][0] <= t < s["out"][1]), segs[-1]["i"])
    heard = [w for w in heard if not ingest.FILLER.match(w["text"])]
    # words re-added from the heard transcript take the project's spelling of names (vocab + cuts text)
    cfg = json.loads((work.parent / "project.json").read_text()) if (work.parent / "project.json").exists() else {}
    known = {t for v in cfg.get("vocab", []) for t in v.split()} | {w["text"].strip(",.?!") for w in orig if w["text"][:1].isupper()}

    def spell(t):
        core = t.strip(",.?!")
        best = max(known, key=lambda k: difflib.SequenceMatcher(None, k.lower(), core.lower()).ratio(), default=None)
        if best and best != core and difflib.SequenceMatcher(None, best.lower(), core.lower()).ratio() >= 0.72:
            return t.replace(core, best)
        return t
    norm = lambda t: re.sub(r"[^a-z0-9']", "", t.lower())
    sm = difflib.SequenceMatcher(None, [norm(w["text"]) for w in orig], [norm(w["text"]) for w in heard], autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for o, h in zip(orig[i1:i2], heard[j1:j2]):
                out.append({**o, "start": h["start"], "end": h["end"], "seg": seg_at(h["start"])})
        elif op == "replace":
            a, b = heard[j1]["start"], heard[j2 - 1]["end"]
            n = i2 - i1
            for k, o in enumerate(orig[i1:i2]):   # keep the corrected text, spread over the heard span
                st = a + (b - a) * k / n
                out.append({**o, "start": round(st, 3), "end": round(a + (b - a) * (k + 1) / n, 3), "seg": seg_at(st)})
        elif op == "insert":
            for h in heard[j1:j2]:
                out.append({"text": spell(h["text"]), "start": h["start"], "end": h["end"], "seg": seg_at(h["start"])})
        else:  # delete: in our transcript but not heard; keep it where it was
            out.extend(orig[i1:i2])
    out.sort(key=lambda w: w["start"])
    path.write_text(json.dumps(out, indent=1))
    print(f"re-timed {len(out)} caption words from the finished cut")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--fast", action="store_true", help="pass --fast to assemble")
    args = ap.parse_args()
    proj = Path(args.project).expanduser().resolve()
    work = proj / "work"
    cuts_path = proj / "cuts.json"
    if not cuts_path.exists():
        sys.exit("cuts.json missing — copy work/phrases.json and edit it first")
    assemble = [sys.executable, str(Path(__file__).parent / "assemble.py"), str(proj)] + (["--fast"] if args.fast else [])
    aroll = proj / "public" / "aroll.mp4"
    if not aroll.exists() or aroll.stat().st_mtime < cuts_path.stat().st_mtime:
        subprocess.run(assemble, check=True, stdout=subprocess.DEVNULL)  # cuts changed since the last assemble
    heard = None
    for rnd in range(1, args.rounds + 1):
        left, heard = fillers_in(proj / "public" / "aroll.mp4", work)
        print(f"round {rnd}: {len(left)} filler(s) heard", flush=True)
        if not left:
            break
        tl = json.loads((work / "timeline.json").read_text())
        tk = {t["id"]: t for t in json.loads((work / "takes.json").read_text())}
        cuts = json.loads(cuts_path.read_text())
        added = 0
        for w in left:
            mid = (w["start"] + w["end"]) / 2
            seg = next((s for s in tl["segments"] if s["out"][0] <= mid < s["out"][1]), None)
            if not seg:
                continue
            to_src = lambda t: round(seg["src"][0] + (t - seg["out"][0]), 3)
            a, b = to_src(w["start"] - 0.03), to_src(w["end"] + 0.04)
            src_mid = to_src(mid)
            ph = next((p for p in cuts if p.get("keep", True) and p["take"] == seg["take"]
                       and p["start"] - 0.3 <= src_mid <= p["end"] + 0.3 and p.get("id") in seg["phrases"]), None)
            if not ph:
                continue
            rm = ph.setdefault("remove", [])
            if any(r[0] <= src_mid <= r[1] for r in rm):
                continue  # already cut; Whisper is hearing the edges
            wav = work / "audio" / (ingest.re.sub(r"[^\w.-]+", "_", Path(tk[seg["take"]]["file"]).stem) + ".wav")
            if wav.exists():
                snapped = ingest.snap_ranges([[a, b]], *ingest.load_mono(wav))
                if snapped:
                    a, b = snapped[0][:2]
            rm.append([a, b, w["text"].strip(",.?!").lower()])
            added += 1
            print(f"  {w['text']:<5} at {w['start']:.2f}s → {seg['take']} {a:.2f}–{b:.2f}")
        if not added:
            break
        cuts_path.write_text(json.dumps(cuts, indent=1))
        subprocess.run(assemble, check=True, stdout=subprocess.DEVNULL)
        heard = None
    if heard is None:  # the last round re-assembled; listen to the final cut once more
        _, heard = fillers_in(proj / "public" / "aroll.mp4", work)
    retime_words(work, heard)
    print("done — now run build.mjs")


if __name__ == "__main__":
    main()
