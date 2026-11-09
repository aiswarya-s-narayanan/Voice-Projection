# voice-projection

A talking kimono girl for the browser, built as a food-ordering assistant. Give it text and she says it out loud. While she speaks:

- **Lips** move with the words.
- **Face** shows emotion: happy, sad, surprised, thinking or angry. She also blinks.
- **Body:** she welcomes guests with a wave and a polite bow, offers the menu with her open palm, nods, shakes or tilts her head, and keeps her hands moving while she talks. When she's quiet, she breathes and sways slightly.

The avatar is one flat picture of the character. The engine bends parts of that picture, so movements stay small.

## Try it

Open `demo/index.html` in Chrome, Edge or Safari by double-clicking it, or run `npm run demo`. She greets you with a wave and a bow when the page opens. Type a sentence or click a sample line, then press **OK**. Turn your sound on.

## Use it in your page

```html
<div id="avatar" style="width: 500px; height: 800px"></div>

<script src="voice-projection/avatars/kimono/rig.js"></script>
<script src="voice-projection/avatars/kimono/image.js"></script>
<script src="voice-projection/src/voice-projection.js"></script>
<script>
  VoiceProjection.createAvatar(document.getElementById('avatar'), { rig: 'kimono' }).then((avatar) => {
    avatar.welcome(); // a guest opened the chat
    avatar.speak('Welcome! What would you like to order today?'); // each chatbot reply
  });
</script>
```

With a bundler, `require('voice-projection')` returns the same `VoiceProjection` object. The avatar itself needs a browser.

### Options for `createAvatar(element, options)`

| option | default | meaning |
|---|---|---|
| `rig` | first loaded rig | rig name or rig object |
| `image` | from `image.js` | image URL or `<img>` |
| `view` | `'full'` | `'full'` or `'close'` |
| `voice` | `true` | `false` = animate silently |
| `voiceName` | best English female voice | browser voice name |
| `rate`, `pitch` | `1`, `1.08` | voice speed and pitch |
| `onSentence(s, i, total)`, `onWord(i, s)`, `onEnd()` | | progress callbacks |

### Methods

- `speak(text)` returns a Promise that resolves when she finishes. Calling it again interrupts.
- `stop()`
- `welcome()` greets a guest without speaking: a happy wave, then a bow.
- `gesture('welcome' | 'wave' | 'bow' | 'present' | 'invite' | 'explain' | 'nod' | 'shake' | 'tilt' | 'emphasis')`
- `setEmotion(name, intensity)`, with `name` one of `neutral`, `happy`, `sad`, `surprised`, `thinking`, `angry`
- `setView('full' | 'close')`, or `setViewRect([x, y, width, height], 'center' | 'top')` to frame any part of the picture
- `getVoices()`, `setVoice(name)`, `setVoiceEnabled(bool)`, `setRate(n)`
- `destroy()`

`VoiceProjection.analyzeText(text)` returns the emotion, gestures and mouth shapes chosen for each sentence. It also works in Node.

## Gestures and emotions from the text

| In the reply | What she does |
|---|---|
| welcome, irasshaimase | waves, then bows |
| hello, hi, hey, bye, good morning | waves |
| thank you, thanks, arigato, sorry | bows |
| menu, special, recommend, dish, look, show, this, here, our | offers with her open palm |
| please, try, enjoy, come, taste | an inviting palm that lifts softly twice |
| yes, sure, ok, of course, certainly, added, confirmed, done | nods |
| no, nope, never | shakes her head |
| a question | tilts her head |
| an exclamation mark | a small emphasis with her hands and brows |
| delicious, tasty, great, love, hello | happy face |
| sorry, unfortunately, unavailable ("sold out" and "delay" make it stronger) | sad face |
| wow, or amazing with an exclamation mark | surprised face |
| hmm, maybe, perhaps | thinking face |

Negation is understood: "not happy" reads as sad. Emoji count too: 😊 reads as happy, 😢 as sad.

In longer sentences her hands open up as she starts explaining. Small hand beats on stressed words, alternating between her hands, keep her moving while she talks. Every movement stays inside a range checked to look clean on this picture.

Text in Malayalam, Tamil, Telugu, Kannada, Hindi, Japanese, Korean, Chinese or Arabic is spoken with a matching voice if the browser has one. The mouth then moves in a general rhythm, and emotions are only detected in English.

## How it works

- `avatars/kimono/avatar.jpg` is the character as one flat picture. `image.js` is the same picture packed into a script, so the demo works when opened straight from disk.
- `avatars/kimono/rig.js` gives the pixel positions of her eyes, brows, lips, head, hat and hands.
- The engine bends those areas with a WebGL mesh. The raised hand is a separate layer so it can wave in front of the kimono. Hands and head move on springs, so motion eases in and settles.
- The voice comes from the browser (Web Speech API). Lip timing follows the voice's word events when the voice provides them, and estimates the timing otherwise. On a Mac, "Samantha" provides them.

If you change the picture, run `npm run build:image` and update the positions in `rig.js`.

## Project files

| Path | What it is |
|---|---|
| `src/voice-projection.js` | the engine |
| `avatars/kimono/` | the picture (`avatar.jpg`, `image.js`) and its rig (`rig.js`) |
| `demo/index.html` | the demo page; `demo/picture.html` is an identical copy |
| `scripts/image-to-js.mjs` | packs the picture into `image.js` (`npm run build:image`) |
| `Indigo_Kimono_Character_Vector.svg*` | the original SVG the picture was made from |

Some leftover files belong to the video and SVG versions of the avatar. Their code (`src/video-avatar.js`, `src/svg-avatar.js`, `avatars/kimono/video-rig.js`) is no longer in the project, so these files don't work at the moment:

- `demo/video.html`
- `dev/svg-gallery.html`, `dev/svg-timeline.html`
- `scripts/track-clips.html`, `scripts/track-clips.mjs`
- `avatars/kimono/clips/`: the Gemini videos, their `.js` copies, `tracks.js`, the start frames and `HOW-TO-MAKE-CLIPS.md`
- `avatars/kimono/poses/` (empty)
