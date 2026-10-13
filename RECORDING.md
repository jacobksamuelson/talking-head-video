# How to record

This is the part only you can do. Everything after you save the file is automatic. The goal is footage that's sharp, well lit, and clean-sounding.

You can bring two kinds of recordings, and mix them in one video:

- **Camera takes:** you on a webcam (built into your monitor, or a USB one) recorded with **QuickTime Player**, or on your phone's back camera.
- **Narrated screen recordings:** your screen plus your voice, recorded with the Mac's built-in screen recorder (⌘⇧5). See the section near the end.

With a webcam, files land on the Mac directly. With a phone, AirDrop them over.

## One-time setup (about 15 minutes)

**Camera settings.**
- Turn off any **auto-framing** your camera has (Dell calls it "AI Auto Framing"; Logitech and others have their own). A frame that moves on its own fights the editor's zooms.
- Slide the camera's privacy shutter open.
- With the camera on, click the **green camera icon in the Mac menu bar** and turn off **Center Stage**, **Portrait**, **Studio Light**, and **Reactions**. With Reactions on, a thumbs-up sets off fireworks on screen.

**Recording app: QuickTime Player.**
1. Go to File › New Movie Recording.
2. Click the small arrow next to the red button and choose your **camera**, your **microphone** (see Audio), and Quality **Maximum**.
3. After recording, save straight into the project's `raw/` folder.

**Sit a bit closer than arm's length (about 60 cm), and about 15 cm to your left of the camera.**
- Sitting to your left puts you right of center in the recording, which leaves room for the product cards on the left.
- If your camera is 1080p or 2K, there's little spare picture for the editor to crop, so you get there mostly by where you sit. With 4K the editor can move you.
- Don't get much closer than 50 cm. Webcam lenses are wide, and up close they stretch your face.

The setup check tells you if you're placed right.

**Light: webcams need more of it than phones.** Small camera sensors turn grainy and smeary in a dim room.
- Put a lamp or key light in front of you, a bit above eye level and off to one side, or sit facing a window.
- Turn off harsh overhead lights.
- Never sit with a bright window behind you.
- A warm lamp somewhere in the background adds depth.

**Background:** something recognizable and tidy behind you, such as a shelf, a plant, or something from your company. More distance between you and the wall looks better.

**Audio: this is the biggest quality jump.** The monitor's and laptop's built-in mics sit far from your mouth, so they pick up room echo, which the editor can't remove.
- Best: a wireless clip-on mic whose receiver plugs into the Mac (DJI Mic Mini or Mic 2, Rode Wireless GO), clipped mid-chest.
- Also good: a USB mic on the desk just below the camera's view, pointed at your mouth.
- Pick it in QuickTime's microphone menu.
- If you have neither: use a small room with soft things in it (rug, couch, curtains), and turn off fans and AC.

**Wardrobe:** solid mid-tone colors. Avoid fine stripes, pure white, pure black, and other companies' logos.

### Check your setup before the real thing

Record **5 seconds** of yourself talking normally, save it anywhere, and ask Claude to **"check my video setup"** with the file. You'll get a pass/fix list covering resolution, HDR, distance, whether the editor can place you right of center, brightness, background noise, and mic level.

QuickTime usually records webcams at **1920×1080** on Maximum, which works. (The default "High" setting gives a soft 1280×720, so always pick Maximum.) At 1080p the editor has no spare picture to move you around, so **where you sit is your framing**: about 15 cm to your left of the camera. To get the camera's full 2560×1440 and more room to zoom, record with OBS (free) instead, and Claude can walk you through it. A phone's back camera at 4K (HDR off) also works and gives the most room. Once everything passes, note where your chair and lamp go.

## Recording a video

Claude writes the script first (`script.md` in the project folder). It's broken into **beats** of one to three sentences each, with a note on what appears on screen during each.

1. **Put the script right under the camera.** Use a narrow window at the top-center of the monitor, so your eyes barely move while you read. This is the big advantage of a monitor camera.
2. **Hit record once and leave it running.** One long file is easiest.
3. **For each beat:** read it, look into the **camera lens** (not your own face on screen), and say it. Then pause for about **2 seconds** and go to the next beat.
4. **Messed up? Pause, then restart the whole sentence from its beginning.** The editor finds repeated sentences and keeps your **last** take. You don't need to say "cut" (it removes that too if you do).
5. **Energy:** about 20% more than in conversation. Short sentences. Smile on the first and last line.
6. **Start and end each beat with your mouth closed for a moment.** That gives clean cut points.

Length guide: about 140 spoken words is a minute. LinkedIn videos land best at **45–90 seconds**.

## Narrated screen recordings

Use these when it's easier to *show* the product while you talk than to talk to the camera. A video can be all screen recordings, all camera, or a mix. For example: open on camera, walk through the product on screen, close on camera.

1. Turn on **Do Not Disturb** so no notifications pop up. Close extra tabs and windows, and hide the bookmarks bar.
2. Press **⌘⇧5**. Choose **Record Entire Screen** or **Record Selected Portion** (a browser window is ideal). Click **Options** and set **Microphone** to the same mic you use for camera takes.
3. Click Record, then talk while you click. The same rules apply as on camera: if you flub, pause and restart the sentence, and the editor keeps your last take.
4. Silent moments while you click, type, or wait for a page are fine. The editor keeps up to 3 seconds of silent action and cuts longer waits.
5. Leave the file named the way the Mac names it ("Screen Recording …"). That's how the editor knows it's a screen recording.

In the finished video, your screen shows as a clean rounded card on a soft background. It zooms into whatever you're talking about, with captions underneath.

Use demo or test accounts only, with **no real customer or user data** on screen.

## Product visuals

Pick whichever is easiest for each moment. The script lists what's needed.

- **Public web pages:** just give Claude the URL. It captures them at 2× resolution.
- **AI chat moments** (a prompt and its answer): just give the prompt and answer text. Claude rebuilds these as crisp animated cards, which usually look better than a recording.
- **Screenshots of logged-in product:** use a browser window around 1440×900 at 100% zoom, with the bookmarks bar hidden and extra tabs closed. Press **⌘⇧4**, then **Space**, then **Option-click** the window (Option drops the drop shadow). Use demo or test accounts only, with **no real customer or user data** on screen.
- **Silent screen recordings** (a short flow shown in a card next to you while you talk on camera): press ⌘⇧5, then **Record Selected Portion**, with the microphone off. Keep each one under 30 seconds and move the mouse slowly.

## Where files go

Claude creates a project folder at `~/Movies/talking-head-video/<name>/`.

- **Anything with your voice** goes in `raw/`: QuickTime camera takes and narrated screen recordings.
- **Silent visuals** go in `screens/`: screenshots and mic-off screen recordings. Name them by beat, like `03-mission-page.png`.

Then tell Claude "edit it." You'll get a draft to watch, give notes, and get the final file in `out/`.
