# Editing taste: what makes these better than a Loom

The inspiration is a 54-second product launch video from Toast (Maggie Crowley, VP of Product). The main frame is a sharp, warmly lit talking head with depth and a branded background element. Product shows up as clean floating cards beside the face, never as a raw screen share. Below is what to copy, plus the rules this skill enforces.

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
- **Captions on** for LinkedIn and social (most people watch muted). Off for embedded or internal videos where they distract.

## Look

- Light cards (white, soft shadow, slight glass), with a blue → violet → orange gradient on AI elements. The default theme uses Inter; override colors per video with `theme` in storyboard.json.
- Motion: things rise in from slight blur with an expo/power3 ease-out, and leave faster than they arrive. No bounces, except the prompt bubbles.
- Sound: subtle whoosh on card entrances, soft pops on bubbles, voice at -16 LUFS. Music is optional and needs a licensed track; keep it around 0.08–0.12 volume.

## Structure that works (60–90 s)

1. **Hook (0–5 s):** the news or the problem in one sentence, face only, plus the lower third.
2. **Show it (5–40 s):** 2–3 product moments, each tied to a spoken line (chat, screen, demo).
3. **Why it matters (40–60 s):** a callout or title card for the takeaway.
4. **Close:** face, punched in, with one clear next step.
