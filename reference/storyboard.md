# Storyboard + cuts reference

Two files drive the edit. Both live in the project root and are hand-authored by Claude.

- `cuts.json`: **which phrases stay, and the framing for each.** Copy it from `work/phrases.json` after ingest and edit it.
- `storyboard.json`: **look, audio, and overlays.**

Canvas is 1920×1080 at 30 fps.

## cuts.json

This is an array of phrases from ingest, in playback order. Reordering the array reorders the video. Fields Claude may set:

| field | meaning |
|---|---|
| `keep` | `false` drops the phrase |
| `zoom` | framing for the segment that starts at this phrase, **relative to the take's base framing**. `1.0` = standard, `1.18` = medium, `1.3`–`1.45` = tight. If it differs from the previous phrase's segment, a **punch-in cut** happens here even inside one continuous take. Base framing is automatic: wide webcam shots are cropped so the face fills about 15.5% of the frame width (up to what the resolution allows sharply). |
| `faceX`, `faceY` | where the face lands in the output frame (0–1). When base framing crops in, the default is `0.6`/`0.42` (right of center, eyes near the top third). Otherwise the face stays where it was recorded. Use `faceX: 0.64` when a left card would cover the face, or `0.36` for right cards. It needs spare picture (base or zoom > 1). |
| `cutBefore` | `true` starts a new segment at this phrase even when it follows the previous one closely. Use it to drop a pause, or to make `trimStart`/`trimEnd` apply, since those only trim the first/last phrase of a segment. |
| `remove` | list of `[start, end, label, gap?]` source ranges taken out of the phrase. The optional `gap` (seconds) leaves a breath, a held frame plus silence, at a cut, so two clauses don't run together. On camera takes, a filler or doubled word in the middle of a shot is silenced rather than cut, so the picture doesn't jump; "pause" ranges mid-shot are left alone. Content edits (any other label) and ranges near a shot's edges are cut. Ingest fills it with "um"/"uh", doubled words, and long hesitations (camera takes only), and `polish.py` adds any it hears afterwards. Delete an entry to keep that moment. |
| `holdAfter` | seconds of frozen last frame + silence after this phrase, a beat before the next shot. Use it when the speaker runs straight into the next words and the cut feels abrupt. |
| `mute` | `true` silences the segment. Use it for a held, wordless moment under a title card. |
| `joinNext` | `true` keeps everything between this phrase and the next one, however long the silence. Use it for a silent click or typing moment in a screen recording that runs past 3 s. |
| `trimStart`, `trimEnd` | seconds shaved off the head or tail of the phrase (for a stray "so" or a breath) |

Segments form automatically. Consecutive kept phrases from one take stay together when the pause between them is under 0.7 s (3 s for narrated screen recordings, so silent clicks and typing survive) and nothing was dropped between them.

**Narrated screen recordings** are takes of kind `"screen"`. Ingest sets this for files named "Screen Recording …" or with no face; override it in project.json → `"kinds": {"file.mov": "face"}`. They are fitted whole into the frame instead of face-cropped. The composition shows them as a rounded card on the theme background. Set `"screenStyle"` in storyboard.json to `"full"` to fit them edge to edge with no card, or `"fill"` to fill the whole frame (full-bleed, cropping the edges that don't fit). Captions switch to the dark box over them. Each new segment alternates the `framing.pattern` zoom (default `[1.0, 1.18]`) unless a phrase sets `zoom`.

After `assemble.py`, `work/timeline.json` lists the segments with output times, and `work/words.edited.json` holds every kept word on the edited timeline. Read that file for exact anchor phrases.

## storyboard.json

```json
{
  "title": "AI Skills Studio launch",
  "theme": "neutral",                   // or {"base":"neutral","accent":"#...","accent-2":"#..."} to use your brand colors
  "captions": {"style": "boxed"},       // burned-in word-highlight captions; true = plain, 6-word lines
                                        // "boxed" = 2–4 words in a solid box; maxWords / maxChars tune chunk size
  "screenStyle": "framed",              // narrated screen recordings: framed (card) | full | fill (full-bleed)
  "slate": {"logo": "brand/logo.svg", "dur": 4},   // logo end slate after the last word; see "End slate" below
  "sfx": {"whoosh": true, "pop": true}, // subtle entrance sounds; false to disable
  "music": {"src": "music/bed.mp3", "volume": 0.1},   // optional, licensed track only
  "fadeOut": 1.2,                       // optional fade to black over the last N seconds
  "faceMotion": "drift",                // slow 2–3% push-in per segment; "none" or a number like 0.02
  "framing": {"pattern": [1.0, 1.18]},  // default zoom alternation per segment
  "grade": {"contrast": 1.04, "saturation": 1.06, "temperature": 5200},  // optional, ffmpeg eq/colortemperature
  "audio": {"voice": "light", "lufs": -16},            // voice chain: none | light | medium
  "overlays": [ ... ]
}
```

`framing`, `grade`, and `audio` are read by `assemble.py`, so re-run assemble after changing them. Everything else is read by `build.mjs`.

### Timing every overlay

- `at`: when it appears. Use a **phrase** from the edited transcript (`"at": "we built a coach"`), a number in seconds, or `{"phrase": "...", "nth": 2, "offset": -0.3}`. A phrase defaults to 0.15 s before its first word.
- `until`: when it leaves. Same forms; a phrase means 0.35 s after its last word. `{"t": 999}` runs to the end.
- `{"segment": "<phrase id>"}` anchors to the start (for `at`) or end (for `until`) of the segment containing that phrase from cuts.json. Use it for a wordless hold you added by hand, so the overlay follows when cuts move.
- `dur`: seconds, used when `until` is absent. Each type has a sensible default.

Matching ignores case and punctuation, but words must match the transcript exactly (Whisper may write "gonna", "AI", "24,680"). If an anchor isn't found, the build fails and prints the closest matches.

### Overlay types

**`lowerThird`**: name and role in the bottom-left, white on video.
`{"type":"lowerThird","at":"I'm Sam","dur":4.5,"name":"Sam Rivera","role":"Product, Acme"}`
Over a screen recording it switches automatically to a white card with dark text, which works well as a name tag for whoever's project is on screen. `"style":"card"` forces that look on camera footage too.

**`chat`**: an AI prompt pill types itself, the send button fires, the card lifts, an answer card streams in word by word with a warm color sweep. This is the signature move.
```json
{"type":"chat","at":"so I asked it","until":"and that's the point","side":"left",
 "prompt":"How were my sales last week?",
 "answer":"Here's how last week compared:\n\n**Sales:** $24,680 — ==up 9%== week over week.",
 "cps":22, "wps":9, "think":0.9, "width":760}
```
`answer` is optional. Answer markup: blank line = new paragraph, `**bold**`, `==accent==`. Keep answers to 20–45 words. If the window is shorter than the natural length, typing and reveal compress, and the build warns.

**`screen`**: a screenshot or screen recording in a floating card with optional browser chrome, zoom-to-region, and highlight rings.
```json
{"type":"screen","at":"here's the mission page","until":"start building","side":"left","size":"m",
 "src":"screens/03-mission.png","url":"acme.com/app","chrome":"browser",
 "caption":"Missions — live today",
 "focus":[{"at":1.2,"rect":[0.1,0.2,0.5,0.4],"dur":1.0},{"at":3.5,"reset":true}],
 "highlight":[{"at":1.8,"rect":[0.4,0.78,0.15,0.08],"dur":2.0}]}
```
- `size`: `s` 560, `m` 760 (default), `l` 980, `xl` 1180 px wide.
- `chrome`: `browser` (default), `none`, or `phone` (auto when the image is tall).
- `rect`s are fractions of the image: `[x, y, w, h]`. `at` is seconds after the overlay starts.
- A highlight must sit inside the active focus rect, or it gets cropped (the build warns).
- Video sources (`.mp4`/`.mov`) play muted from `mediaStart` seconds.

- `badge`: a bold pill floated above the card, e.g. `"badge": "Built with OpenAI"`, for partner credit. Use text, not another company's logo, unless the partner has approved it.

**`endcard`**: a calm closing card beside the face. Bring it in on the last line and run it to the end (`"until": {"t": 999}`). Pair it with `"fadeOut": 1.2` at the storyboard top level and a short silent `holdAfter` hold in cuts.json, so the shot doesn't end mid-blink.
`{"type":"endcard","at":"check it out","until":{"t":999},"side":"left","kicker":"Free to try","title":"Build Your First Dashboard","text":"Built with OpenAI · Link in the comments"}`

**`demo`**: the product takes over the frame on a soft background, and the face shrinks into a circle in the corner. Use it for anything longer than about 6 s of product, or when detail matters.
`{"type":"demo","at":"let me show you","until":"that's it","src":"screens/flow.mp4","url":"…","pip":"bottom-right","focus":[…]}`
`pip`: `bottom-right` (default), `bottom-left`, `top-right`. `pipSize` sets the diameter (default 300). A demo that runs to the end holds the corner circle.

**`title`**: a full-frame kinetic title card covering the face while the voice keeps playing. Use it for chapter turns and the one big idea.
`{"type":"title","at":"here's the thing","dur":2.2,"kicker":"New","lines":["Shared knowledge.","Smarter prompts."],"style":"light"}`
`style`: `light` (paper) or `dark` (deep navy, last line in the pop color). The last line gets the accent color (`"accentLast": false` turns that off). `size` sets font px (default 132). Keep it to 2 lines and 6 words or fewer.

**`bubbles`**: a stack of prompt pills popping in, for "the kinds of things people ask".
`{"type":"bubbles","at":"people ask things like","until":"…","side":"left","items":["How did my sales perform?","Are we staffed for dinner?",{"text":"Which items drive sales?","at":"driving"}]}`
Items pop 0.42 s apart unless an item has its own `at`.

**`callout`**: a big number or key line on a card. Numeric values count up.
`{"type":"callout","at":"nine percent","dur":3,"side":"right","kicker":"Week over week","value":"+9%","text":"sales, higher average ticket"}`
Without `value`, `text` is set large as a key point.

**`zoom`**: smooth zoom into part of a narrated screen recording, held until `until`, then eased back out. Only valid while a screen-recording segment is playing; it's trimmed at the end of that recording.
`{"type":"zoom","at":"click start building","until":"and you're in","rect":[0.38,0.74,0.24,0.14]}`
`rect` is `[x, y, w, h]` as fractions of the recorded screen. `scale` overrides the automatic fit (max 4), and `in` sets the zoom-in seconds (default 1.0). Zoom to whatever is being talked about within about a second of it being said; one zoom per idea.

While the zoom holds, the frame keeps moving:

- **`drift`**: a slow push-in, 4% by default. `"drift": 0` holds still.
- **`to`**: a follow pan for content that streams in or runs down the page. Give one rect, or a list of rects visited in turn; the zoom pans from `rect` to each over the hold. `toScale` fixes the zoom level for those rects.

`{"type":"zoom","at":"and it writes","until":"in seconds","rect":[0.05,0.1,0.6,0.3],"to":[0.05,0.45,0.6,0.35]}`

**`mark`**: a highlighter stroke (or a ring) on one line of a narrated screen recording, timed to the words. It's drawn inside the recording, so it rides along with any zoom. Only valid on screen-recording segments.
`{"type":"mark","at":"change the conclusion","until":"per person","rect":[0.19,0.16,0.36,0.03]}`
`rect` is in the same fractions as `zoom`. The default style is a highlighter wipe (the theme's `pop` color, multiplied, so it reads on light UIs). On dark UIs use `"style":"ring"`: an outline with a soft glow. Set a `--mark` color through `theme` to change both. Keep the page still while a mark shows; it doesn't follow scrolling.

**`html`**: escape hatch. Pass `"file":"custom/thing.html"`, a fragment that gets a fade/rise entrance and exit. Scope its CSS under a unique class. No `<script>`.

### End slate

`"slate"` at the top level adds a logo card **after** the last word: a dissolve from the final frame, then the logo rises in and the lines below it follow. Music and `fadeOut` run through the slate.

```json
"slate": {"logo": "brand/logo.svg", "dur": 4, "tagline": "Free to try", "url": "acme.com/app"}
```

- Set the pieces directly:
  - `logo`: an image path in the project, sized by `logoHeight` (default 120 px)
  - `text`: a typed wordmark, used when there's no logo
  - `sublogo`: an image path, sized by `sublogoHeight`
  - `tagline`, `url`: lines of text under the logo
  - `bg`: any CSS background (default: the theme's `dark-bg`)
- `dur`: 3–5 s; default 4.
- `brand`: a saved logo set from `assets/themes.json` → `brands` (empty to start). Add yours there, with paths relative to the skill folder, and every video can use `"slate": {"brand": "acme"}`.
- Use your own company's logo only. A partner's logo needs their approval; credit them in text instead.

### Placement rules the build checks

- Cards on `side: left` (default) want the face at about 60–70% across. The build warns when a card would cover the face in any segment it overlaps, and tells you which `faceX`/`zoom` to set in cuts.json.
- Two overlays in the same zone at the same time trigger a warning.
- Anything that starts underneath a full-frame `title` is pushed to the title's end.
- Captions hide during titles and switch to a dark box during demos and screen recordings.
- `screen`, `chat`, `bubbles`, and `demo` on top of a screen recording trigger a warning. Use `zoom`, `mark`, `callout`, or `title` there.
- `zoom` and `mark` must start inside a screen recording; they're trimmed at its end.
