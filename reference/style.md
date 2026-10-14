# Editing taste: what makes these better than a Loom

Two references:

- **Toast's "fall release"** (Maggie Crowley, VP Product, 54 s). A sharp, warmly lit talking head with depth and a branded background element. Product shows up as clean floating cards beside the face, never as a raw screen share.
- **Klaviyo's Composer launch** (Elias Torres, CPO, 1:56). It opens on the viewer's problem, says the roadmap out loud, and gives each feature a claim, an example, and the product doing it. The product runs full screen with slow zooms that follow the result. Captions are short and boxed. It ends on a one-line close and a logo slate.

Below is what to copy, plus the rules this skill enforces.

## Rhythm

- **Cut on every beat.** Each new segment changes framing (wide ↔ punched-in), so cuts read as intentional edits rather than glitches. Use a tight punch-in (1.3–1.45) on the one or two lines that carry the argument.
- **Kill dead air.** Pauses over 0.7 s become cuts. Keep about 0.3 s of breath at each cut.
- **Something changes every 4–8 seconds**: a cut, an overlay entering, a zoom inside a screenshot. Don't stack changes. Give the face 1–2 s of clean screen time between overlays.
- **Overlays appear as the words are said**, not before. Anchor to the exact phrase.
- **Cut hygiene.** These are the mistakes viewers notice:
  - cut only in silence, never inside a word
  - remove whole sentences, not clauses that end on a comma
  - leave about 0.2 s of breath at a content cut
  - keep 4+ seconds between cuts on camera; silence fillers there rather than cutting them
  - give every screen ↔ camera switch about half a second of air

## What goes on screen

- **One idea per overlay.** If the voice is saying it, the card should *show* it (the product, the number, the prompt), not repeat it as text.
- **Rebuild simple product moments natively.** A typed prompt and streamed answer (`chat`) beats a screen recording of the same thing: sharper, bigger text, no cursor, no UI noise.
- **Screenshots get focus.** Zoom (`focus`) to the part that matters within about 1.5 s, and ring the button or number being talked about (`highlight`). A static, full-page screenshot is a Loom habit.
- **Long product moments become a `demo`.** Over about 6 s, give the product the full frame and put the face in the corner circle.
- **Narrated screen recordings get zooms.** Raw full-screen footage is what makes a video feel like a Loom. Zoom (`zoom`) into the thing being described about once per sentence, and let it ease out between ideas. Cut waits longer than about 3 s. Book-end screen sections with camera segments when there are any.
- **Title cards are scarce:** 1–2 per minute, at chapter turns or for the single takeaway. Six words max. The last line goes in the accent color.
- **Lower third in the first 5 seconds**, once.
- **Captions on** for LinkedIn and social (most people watch muted). Use `{"style": "boxed"}`: 2–4 words at a time in a solid box reads faster on a phone. Turn captions off for embedded or internal videos, where they distract.
- **Product full screen when it's the star.** `"screenStyle": "fill"` makes narrated screen recordings fill the frame. Keep it moving:
  - A zoom holds with a slow push-in by default.
  - `to` makes the zoom follow content as it streams in.
  - A `mark` highlights the key line: highlighter on light UIs, `"style": "ring"` on dark ones.

## Look

- Light cards (white, soft shadow, slight glass), with a blue → violet → orange gradient on AI elements. The default theme uses Inter; override colors per video with `theme` in storyboard.json.
- Motion: things rise in from slight blur with an expo/power3 ease-out, and leave faster than they arrive. No bounces, except the prompt bubbles.
- Sound: subtle whoosh on card entrances and voice at -16 LUFS. Pops on bubbles are optional and can feel cheesy, so leave them off unless the video is playful. Music is optional and needs a licensed track. Keep it around 0.08–0.12 volume (about 10 dB under the voice); it runs through the end slate and fades with it.
- **End on a logo slate**: 3–5 s, logo and tagline on dark, after the last line. `"slate": {"logo": "brand/logo.svg", "tagline": "…"}`, with your own logo.

## Structure that works (60–100 s)

1. **Hook (0–5 s):** the viewer's problem or the news in one sentence, face only. Don't open with "Hi, I'm…"; the lower third already says who you are. `review.py` flags an intro-first opening.
2. **Roadmap (5–10 s):** say how many things are coming ("Here are three that stood out"), then signpost each one: "First…", "Second…", "My favorite…". People keep watching when they know where they are.
3. **Beats (2–3 of them):** each one goes claim → concrete example → show it.
   - "It writes the email for you" is a claim.
   - "Ask for a Black Friday email and it drafts the subject, the copy, and the images" is an example.
   - The product on screen then shows that exact example.
4. **Close:** one or two sentences, under about 12 s, face punched in, then the logo slate. `review.py` flags a longer close.
