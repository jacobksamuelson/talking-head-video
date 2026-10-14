---
name: talking-head-video
description: Make polished talking-head product videos from the user's recordings (webcam or phone camera takes and/or narrated ⌘⇧5 screen recordings) — their face on camera with animated product overlays (screenshots in floating cards with zoom + highlight, AI chat prompts that type and stream answers, kinetic title cards, lower thirds, stat callouts, prompt bubbles, full-frame product demos with their face in a corner circle), screen recordings framed as cards or full-bleed with smooth follow zooms and highlight marks, jump-cut editing with punch-ins, retakes removed automatically, cleaned -16 LUFS audio, boxed captions, a logo end slate. Covers the whole loop — script + shot list, how to record, setup check, ingest/transcribe, cut, storyboard, render. Use when the user wants a video "like the Toast/Maggie one", a launch or product-update video, a LinkedIn video, says "check my video setup", "edit my recording", "make a video from this footage", or drops camera files in a videos project. Also for narrated screen recordings on their own ("turn this screen recording into something better than a Loom").
---

# Talking-head product video

The pipeline: **plan → record (the user) → ingest → cut → storyboard → assemble → build → QA → draft → notes → final.**

- `ffmpeg` handles cutting, punch-in framing, and audio.
- **HyperFrames** (Apache-2.0, HTML → MP4, pinned 0.8.137) renders the overlays over the face footage.
- Everything is driven by two hand-edited JSON files.

`SKILL` below means this skill's directory (`~/.claude/skills/talking-head-video`).

| file | for |
|---|---|
| `RECORDING.md` | the user's guide: gear, framing, light, audio, delivery, screenshots. Point them to it and quote the relevant part. |
| `reference/style.md` | editing taste. Read before writing a script or storyboard. |
| `reference/storyboard.md` | `cuts.json` + `storyboard.json` schema and every overlay type. Read before authoring. |
| `scripts/` | `new_project.sh`, `ingest.py`, `assemble.py`, `build.mjs`, `capture.sh`, `hf` |

Projects live in `~/Movies/talking-head-video/<slug>/`:

- `raw/`: anything with the user's voice — camera takes (QuickTime on Maximum, or a phone) and narrated screen recordings (⌘⇧5, "Screen Recording …")
- `screens/`: silent visuals — screenshots and mic-off screen recordings used as overlays
- `script.md`, `project.json`, `cuts.json`, `storyboard.json`
- `work/`: generated
- `public/`: the HyperFrames project
- `out/`: renders

## 0. Setup check (first run on a machine)

```bash
ffmpeg -version | head -1; uv --version; ls ~/.nvm/versions/node | grep -E '^v2[2-9]'
SKILL/scripts/hf doctor        # Chrome + ffmpeg for rendering; whisper-cpp/TTS/MusicGen/Docker lines are optional, ignore them
```

`hf` runs HyperFrames on Node 22+ with telemetry off. Never call `npx hyperframes` directly under Node 20. First-time transcription downloads the Whisper model (~1.6 GB, cached).

**Camera setup check:** when the user sends a short test clip, run `uv run SKILL/scripts/ingest.py --check <clip>` and relay the ✅/⚠️/❌ list in plain words, with the fix for each. The checks cover 4K, HDR off, face at ~62% across, distance, exposure, noise, and level.

## 1. Plan with the user

1. Run `SKILL/scripts/new_project.sh <slug> "Title"`. It prints the folder.
2. Ask, briefly: who the video is for, the one thing they should take away, and which product moments to show (URLs, features, prompts).
3. Write `script.md` from the template: 5–8 beats, 60–100 s (≈140 words/min), short spoken sentences, each beat paired with its on-screen visual. Follow the structure in `reference/style.md`:
   - open on the viewer's problem, never "Hi, I'm…"
   - say the roadmap out loud ("Here are three…")
   - give each beat a claim → a concrete example → the product showing it
   - close in one or two sentences

   List the visuals the user must capture by hand, and capture public URLs yourself:
   `SKILL/scripts/capture.sh <url> <proj>/screens/NN-name.png 1440 900`
4. Add product names and jargon to `project.json` → `vocab`. This steers transcription.
5. Hand off with the folder path and the **Recording a video** and **Product visuals** sections of `RECORDING.md`. On a first recording, also include the one-time setup and ask for a 5-second test clip.

## 2. Ingest

```bash
uv run SKILL/scripts/ingest.py <proj>
```

- Classifies each take as `face` (camera) or `screen` (narrated screen recording: "Screen Recording …" filename or no face found).
- Probes each take, detects speech, and transcribes each speech chunk separately (MLX Whisper large-v3-turbo with word timestamps; chunking keeps Whisper from merging a false start into its retake). It also finds the face.
- Proposes KEEP/DROP per phrase: retakes (a later phrase restarts the same words → the earlier one drops), filler-only phrases, and slate chatter.
- Runs a second, filler-keeping transcription (Whisper normally drops "um"/"uh") and adds a `remove` list to each phrase: fillers, doubled words, and hesitations over 0.6 s. On camera takes, fillers in the middle of a shot are silenced in assembly rather than cut, since a run of jump cuts reads as choppy. On screen recordings, only the filler sound goes, since the pause is often a click.
- Writes `work/takes.json` and `work/phrases.json` and prints the table plus warnings.

Deal with warnings before going on. HDR, low resolution, portrait footage, or a missing face each change what's possible, so tell the user plainly.

## 3. Cut (`cuts.json`)

Copy `work/phrases.json` → `cuts.json`. Then review every line against the script:

- Confirm each retake call. Keep the **best** take, usually the last. Drop off-script asides, stray "so…" starts (or `trimStart`), and anything that repeats a point.
- Reorder phrases only if the script order demands it.
- For screen-recording takes, silent actions up to 3 s are kept. Set `"joinNext": true` on a phrase whose following silent action matters and runs longer.
- Plan framing. Zoom is relative to each take's automatic base framing (webcam footage gets cropped in and the face placed right of center). Set `zoom` 1.3–1.45 on the one or two lines that carry the argument. Set `faceX` where a card will need the face pushed aside (see step 4).
- Target length: the script's. Aim for under 90 s unless the user asked for longer.

## 4. Storyboard (`storyboard.json`)

Run `python3 SKILL/scripts/assemble.py <proj> --fast` first. That produces `work/words.edited.json` (the exact words to anchor on) and `work/timeline.json` (segments, face position per segment).

Then write overlays per `reference/storyboard.md`, one per script beat that has a visual, anchored to the spoken phrase. Over narrated screen recordings, add a `zoom` for each thing the user points at, using the transcript and a look at the footage to find the rect. Extract a frame with ffmpeg and read it to locate the region. Use `to` when the result streams in or runs down the page, and add a `mark` on the one line that carries the point.

Defaults for LinkedIn:

- `"theme": "neutral"` (set brand colors through `theme`)
- `"captions": {"style": "boxed"}`
- `"slate"` with the user's logo (ask for an SVG or PNG; their own company's logo only)
- `sfx` whoosh only (no pops)
- `"screenStyle": "fill"` when the product is the star of the video

## 5. Assemble → polish → build → check

```bash
python3 SKILL/scripts/assemble.py <proj>             # final-quality A-roll (drop --fast)
uv run SKILL/scripts/polish.py <proj>                # listens to the A-roll for leftover um/uh, cuts them, re-assembles (repeat ≤3)
uv run SKILL/scripts/review.py <proj>                # REQUIRED: checks every cut; writes work/review.md
node SKILL/scripts/build.mjs <proj>                  # any Node ≥18; only `hf` needs 22
cd <proj>/public && SKILL/scripts/hf lint .
SKILL/scripts/hf snapshot . --at <mid-point of each overlay, comma-separated>
```

- Resolve every build `WARN`: face covered → change `faceX`/`zoom` in cuts.json and re-assemble, or switch `side`. Highlight outside focus → widen `focus`. Compressed chat → widen `until` or shorten text.
- **Read `public/snapshots/contact-sheet.jpg` and the full-size frames yourself.** Check text overlapping the face, clipped cards, unreadable captions, and empty frames. Fix and rebuild until clean.
- **Cut review gate.** No draft goes to the user until `review.py` shows 0 ❌, and every ⚠️ is fixed or checked against the waveform. It flags:
  - a cut inside a word (it would have caught "be|fore")
  - a clipped or extra word at a cut
  - 3+ camera cuts within 8 s (choppy)
  - a screen ↔ camera switch with under 0.45 s of air
  - a mid-sentence content cut
  - no breath at a content cut
  - dead air over 1.4 s
  - an intro-first opening ("Hey, I'm Sam…") and a close over ~12 s. These are story notes, not cut bugs. Fix them in the script or cuts, or tell the user and let them decide.

  Fixes:
  - **Clipped word:** move the cut into the silence. Ingest and polish snap their cuts to the quietest 20 ms, but a hand-written `remove` range doesn't snap, so check the waveform for those.
  - **Cut inside a word:** don't trust "quiet" in a broadband energy scan. An "f"/"s" is quiet in broadband but loud above 2.5 kHz.
  - **Abrupt switch:** add `holdAfter` (screen side) or `padBefore` (into silence).
  - **Choppy:** mute the fillers instead of cutting, or cut whole sentences.
  - **No breath:** add a `gap` to the remove entry.
  - **Mid-sentence:** end the kept part at a full stop.
- Read `work/polish.verbatim.json` once, as the transcript of the finished cut. Look for clipped words (e.g. "311" coming out as "3-1") and for noise in held silences. Fix by deleting the offending `remove` entry, or set `"mute": true` on a wordless hold.
- Takes recorded at different levels (different mic or app) are matched automatically before joining; the "level match" line says how much each was boosted.
- Only `assemble.py` reads `cuts.json`, `framing`, `grade`, and `audio`. Only `build.mjs` reads overlays, captions, sfx, music, and theme. Re-run whichever matches what you changed.

## 6. Draft → notes → final

```bash
cd <proj>/public && SKILL/scripts/hf render . --quality draft --output ../out/draft.mp4 && open ../out/draft.mp4
```

Renders run at about real time on an M-series Mac. Send the user the file (SendUserFile) with a two-line summary: length, what was cut, any judgment calls. For timeline scrubbing they can use `SKILL/scripts/hf preview .` (HyperFrames Studio in the browser).

Apply their notes, re-run the needed steps, then render the final:

```bash
SKILL/scripts/hf render . --quality delivery --output ../out/<slug>.mp4
ffprobe -v error -show_entries format=duration -of csv=p=0 ../out/<slug>.mp4   # duration matches timeline
```

Also export a poster frame for the LinkedIn thumbnail: `ffmpeg -ss <a strong face moment> -i ../out/<slug>.mp4 -frames:v 1 ../out/<slug>-poster.jpg`.

## Gotchas

- Do not send `hf feedback`, `publish`, or `cloud` commands. They upload data, so ask first.
- Product footage must not show real customer or user data.
- Whisper writes numbers and names its own way ("24,680", "AI"). Anchor overlays on the exact words in `words.edited.json`.
- macOS screen recordings have a variable frame rate. `assemble.py` cuts them from a steady 30 fps proxy (`work/cfr/`); cutting the original directly drifts out of sync.
- `assemble.py` caches segments in `work/segs/` (keyed by range + framing), so re-runs are fast. Delete the folder to force a re-encode.
- `hf lint` always shows one `composition_file_too_large` warning. Ignore it; the composition is generated.
- HyperFrames lint rules this pipeline already follows: one paused timeline registered inline, no tweens on `.clip` elements, no nested timed media, every `<audio>` has an id.
- 9:16 vertical output is not built yet. The crop math in `assemble.py` and the CSS geometry would need a portrait variant.
