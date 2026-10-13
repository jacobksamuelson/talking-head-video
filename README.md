# talking-head-video

A [Claude Code](https://claude.com/claude-code) skill that turns your recordings into a polished product video: your face on camera, the product in clean cards beside you, and no video editing on your part.

Give it a camera clip, a narrated screen recording, or both. It:

- keeps your best takes and removes retakes, "um"s, and dead air
- evens out and cleans up the audio, even when two recordings used different mics
- frames your face, with punch-in zooms at the cuts
- shows screen recordings as clean cards that zoom into what you're talking about
- adds name tags, captions, number cards, screenshots, title cards, and an end card, each timed to the words you say
- checks every cut before you see a draft, flagging clipped words, choppy runs of cuts, and abrupt switches
- renders a 1080p MP4 ready for LinkedIn

It can also write the script with you and check your camera, light, and mic from a 5-second test clip.

Inspired by Toast's product launch videos (Maggie Crowley).

## Install

You need a Mac with Apple Silicon (M1 or newer) and Claude Code.

```bash
git clone https://github.com/jacobksamuelson/talking-head-video ~/.claude/skills/talking-head-video
brew install ffmpeg uv node@22
```

The first video downloads a speech-recognition model (about 1.6 GB) and the renderer. After that it runs offline.

## Use

In Claude Code, just ask:

- **"Check my video setup"** with a 5-second test clip attached.
- **"Make a video about …"** Claude writes a script, creates a project folder in `~/Movies/talking-head-video/`, and tells you what to record.
- **"Edit it"** after you drop your recordings in the project's `raw/` folder. You get a draft to give notes on, then the final file in `out/`.

`RECORDING.md` covers camera, light, mic, and how to deliver lines. Read it once before your first recording. To use your brand colors, ask Claude to set them, or see `reference/storyboard.md` → `theme`.

## How it works

- **Transcription:** [MLX Whisper](https://github.com/ml-explore/mlx-examples) runs locally. It transcribes everything twice, once normally and once keeping every "um," so fillers can be found and removed.
- **Cutting and audio:** ffmpeg handles the cuts, framing, and audio leveling.
- **Overlays:** the cards and animations are HTML animated with [GSAP](https://gsap.com), rendered to video by [HyperFrames](https://github.com/heygen-com/hyperframes) (Apache-2.0).
- **Review:** after every edit, a check compares what should be heard with what is heard and inspects the waveform at every cut.

## License

MIT for this skill's code; see `LICENSE`. Bundled third-party files keep their own licenses:

- Inter font: SIL Open Font License 1.1, in `assets/fonts/Inter-LICENSE.txt`
- GSAP: the [GSAP Standard License](https://gsap.com/standard-license), noted in `assets/vendor/gsap.min.js`
