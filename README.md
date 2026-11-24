# Chef · Ditto avatar integration

This project provides a talking character using `Avatar/avatar.jpg`, the official
Ditto online pipeline, a local browser interface, and an optional native desktop display. You can type text to test it
with a local Piper demo voice, or send audio from the separate Chef food-ordering
voice agent. Silero, Whisper, Ollama, menu, cart, and order-submission logic remain
in that separate project; this demo does not listen to the microphone or answer
questions by itself.

Documentation updated on **23 November 2026** for streaming browser playback
(reduced initial delay to ~2–5 seconds), sentence expressions,
face/head/hat alignment, charm movement, idle blinking, speech clarity, voice speed,
persistent Piper synthesis, overlapping voice/render preparation, GPU batch rendering,
and the lighter GPU render preset.

**Status:** the avatar service, browser/native displays, and GPU rendering work on this
machine's RTX 3060 (12 GB). Real-service tests verified consecutive replies,
unchanged audio samples, and interruption recovery without model reload. The
voice agent is on your colleague's machine: use [INTEGRATION.md](INTEGRATION.md)
to connect its Piper output. The NVIDIA access failure in the first session was
sandbox isolation, not a broken host driver.

The live preset sends 25 synchronized audio/video packets per second, with a new
neural face every fifth packet (5 facial updates/second). The desktop separately
animates body/head movement on its 40 ms display timer. The browser runs a
continuous animation loop, with the Canvas fallback throttled to roughly 25 FPS. Previous service checks
measured 2–3 seconds to the first frame after audio submission; this excludes
voice generation and is not a sub-second or 25-unique-neural-frames/sec guarantee.
**The browser uses dynamic streaming playback with a calculated start rule**:
the server announces the expected utterance frame count via an `audio_length`
event right after Piper voice generation. The browser measures incoming GPU render
speed and starts audio playback when enough frames have buffered
(`total_frames × (1 - render_rate / 25) + SAFETY_FRAMES`), typically reducing
initial delay to typically **2–5 seconds** while aiming to avoid playback running dry.
If the GPU temporarily falls behind, playback pauses cleanly to re-buffer 1 second
of frames before resuming, rather than repeatedly micro-stuttering. First-frame
rendering timings below are therefore not time-to-first-audible-speech timings.

The earlier body-motion preview is [natural-avatar-preview.mp4](outputs/natural-avatar-preview.mp4),
using a locally generated Piper greeting with the head/hat and body motion enabled.
[Render metrics](outputs/natural-avatar-preview.json) record about 9 seconds for
model loading/warmup and 2.73 seconds to the first frame after that, on the tested
RTX 3060. The older [service checks](outputs/service-check.json) cover consecutive
replies, audio preservation, and interruption recovery. These are saved test results,
not a statement that a service is currently running. Files under `outputs/` are
generated local artifacts and may be absent from a fresh checkout.

## Where changes are made

Project root on this machine: `/home/force-1/Downloads/Voice-Avatar`.

| File | Responsibility |
|---|---|
| [`models/piper/en_US-lessac-medium.onnx.json`](models/piper/en_US-lessac-medium.onnx.json) | Active voice speed: `inference.length_scale = 1.18`; local model config |
| [`avatar_kiosk/persistent_voice.py`](avatar_kiosk/persistent_voice.py) | Persistent subprocess, serialized requests, cancellation, timeout and recovery |
| [`avatar_kiosk/piper_worker.py`](avatar_kiosk/piper_worker.py) | Load Piper once in `.venv-piper`, then synthesize requested sentences |
| [`scripts/benchmark_voice.py`](scripts/benchmark_voice.py) | Measure per-sentence CLI versus persistent-worker voice preparation |
| [`avatar_kiosk/demo_tts.py`](avatar_kiosk/demo_tts.py) | Piper synthesis, 16 kHz sentence PCM, and optional standalone joined-WAV export |
| [`avatar_kiosk/runtime.py`](avatar_kiosk/runtime.py) | Single-turn lifecycle, bounded sentence queue, duration limits and interruption |
| [`scripts/check_sentence_pipeline.py`](scripts/check_sentence_pipeline.py) | Actual GPU check of overlapped preparation, PCM preservation and expression timing |
| [`avatar_kiosk/speech_text.py`](avatar_kiosk/speech_text.py) | Spoken temperature/unit and text normalization |
| [`avatar_kiosk/expressions.py`](avatar_kiosk/expressions.py) | Supported emotions and automatic English phrase cues |
| [`avatar_kiosk/emotion_motion.py`](avatar_kiosk/emotion_motion.py) | Facial presets and smooth sentence expression transitions |
| [`avatar_kiosk/head_alignment.py`](avatar_kiosk/head_alignment.py) | Remove residual global face drift before shared head/hat motion |
| [`avatar_kiosk/worker.py`](avatar_kiosk/worker.py) | Ditto rendering, facial controls, alignment, JPEG quality and audio/frame packets |
| [`avatar_kiosk/config.py`](avatar_kiosk/config.py) | Rendering defaults, including `max_size = 1440` and `batch_size = 2`, and environment overrides |
| [`avatar_kiosk/server.py`](avatar_kiosk/server.py) | Browser assets, text/audio API, synthesis cancellation and WebSocket events |
| [`avatar_kiosk/web/index.html`](avatar_kiosk/web/index.html) | Browser controls and expression selector |
| [`avatar_kiosk/web/style.css`](avatar_kiosk/web/style.css) | Browser appearance and responsive layout |
| [`avatar_kiosk/web/app.js`](avatar_kiosk/web/app.js) | Streaming audio playback, frame buffering/reuse, Stop and renderer coordination |
| [`avatar_kiosk/web/motion.js`](avatar_kiosk/web/motion.js) | Shared head/hat gestures, charm physics, idle eyelids, WebGL and Canvas rendering |
| [`avatar_kiosk/desktop.py`](avatar_kiosk/desktop.py) | Native desktop controls and display |
| [`avatar_kiosk/ambient_motion.py`](avatar_kiosk/ambient_motion.py), [`avatar_kiosk/idle_blink.py`](avatar_kiosk/idle_blink.py) | Native desktop motion and blinking |
| [`start-avatar-browser.sh`](start-avatar-browser.sh), [`avatar_kiosk/launcher.py`](avatar_kiosk/launcher.py) | Start the local service and open the browser |
| [`tests/`](tests/) | Python regressions and `browser_motion.test.cjs` motion checks |
| [`README.md`](README.md) | Current setup, behavior, settings and project file map |

Voice-speed adjustments use the Piper JSON configuration. Browser thinking
animation and preparation-state transitions live in `web/motion.js` and
`web/app.js`; the indicator markup and styling live in `web/index.html` and
`web/style.css`. Keep this README updated when changing those behaviors.

## Run in a web browser

Close the existing desktop avatar, then run from this project directory:

```bash
./start-avatar-browser.sh
```

Open **http://127.0.0.1:8765/** if the browser does not open automatically.
Click **Connect avatar**, wait for Ready, enter text, and click **Speak message**.
The first click enables browser audio. Keep the launcher terminal and browser tab
open. Press Ctrl+C in the terminal to stop the service.

The page includes automatic sentence expressions, manual emotion selection,
portrait/full-character framing, and Stop (including during voice generation).
As soon as **Speak message** is clicked, a **Thinking** indicator and gentle idle
head/hat tilt, breathing, charm swing, and blinking remain visible throughout
voice synthesis and frame buffering. This animation runs locally without extra
GPU inference. It eases into speaking motion when audio playback begins, and
clears on Stop, cancellation, failure, or disconnection. It provides visible
feedback during preparation; it does not shorten the actual rendering delay.
The browser uses **dynamic streaming playback**: audio starts as soon as the
measured GPU render rate and total utterance length satisfy
`need = expectedFrames * (1 - rate / 25) + SAFETY_FRAMES` (at least 0.5 s buffered).
This reduces initial speaking delay to roughly **2–5 seconds** for typical short
replies on the RTX 3060. Detailed timing metrics (`window.avatarTiming` and console logs
for `click→started`, `first frame`, `first sound`, and `stalls`) allow live monitoring
in DevTools (F12). If the GPU runs dry, playback re-buffers a 1 s reserve before
resuming cleanly, avoiding micro-stuttering. Completed turns resolve directly
without relying on `source.onended`, preventing stuck busy states.
The face and expression label follow the browser audio clock; sentences share one
continuous audio buffer. The same local Piper voice and Ditto GPU renderer are used.
The renderer removes residual face translation, rotation, and scale from the
expression/stitching keypoints before generating the face. Eye, brow, and lip
controls are excluded from the alignment fit. This keeps the shared head/hat
transform responsible for head pose, including sentence-specific tilts and nods.
The browser adds continuous head/hat movement, gentle breathing, and a damped
charm swing using WebGL. Face, hair, and hat share one transform; the charm
follows that transform with a small delayed swing around its attachment point.
Speech energy and sentence mood provide restrained head accents, which ease
back to idle after Stop. Both portrait and full-character views use the same
source coordinates. Both eyes blink together at randomized 2.5–5.5 second
intervals while idle,
with a quick close and slower reopening over 240 ms. Blinking is applied before
head movement so the eyelids stay attached to the face; speech uses Ditto's eyes.
If WebGL is unavailable, a Canvas mesh applies the same motion at a lower cadence.
Both paths render a 720-pixel-wide canvas; audio and facial playback keep their
original clock.

Only one display may connect at a time: use either the desktop or one browser tab.
The service runs locally and still requires the configured GPU and models.
External WAV/PCM clients continue to work with the browser connected as the display.
`POST /speak-text` accepts JSON `{"text":"Hello! How can I help?", "emotion":"auto"}`
(up to 800 characters and 100 sentences) and pipelines sentence audio with exact
expression timings. `/interrupt` also
cancels pending text synthesis. The original `./start-avatar.sh` still opens the
native desktop.

### Low-latency streaming browser playback (2–5 second speaking delay)

The browser interface employs progressive streaming playback to achieve low initial
speaking latency:

1. **Pre-announced utterance length**: Immediately after the persistent Piper worker
   synthesizes speech (~0.08–0.11 s), the server emits an `audio_length` WebSocket
   event with the total expected frame count (`ceil(total_audio_bytes / 1280)`).
2. **Calculated start rule**: Rather than waiting for the entire reply to finish GPU
   rendering (which previously contributed 7–12+ seconds of initial delay), the browser
   measures incoming GPU packet delivery rate over the first 0.5 seconds:
   $$\text{need} = \text{expectedFrames} \times \left(1 - \frac{\text{render\_rate}}{25}\right) + \text{SAFETY\_FRAMES}$$
   Playback begins the moment buffered frames satisfy this condition (with a floor of
   `MIN_START_FRAMES = 12` frames / ~0.5 s). This aims to start speech in **2–5 seconds**
   without running dry for the rest of the utterance.
3. **Clean stall recovery & re-buffering**: If GPU contention causes the buffer to run dry,
   the player pauses into a `"Buffering…"` state until a full 1-second reserve
   (`REBUFFER_FRAMES = 25`) arrives, resuming cleanly rather than micro-stuttering.
4. **Reliable turn termination**: Completed turns calculate total duration from packet count
   and audio clock timestamps, directly sending the `played` acknowledgment and freeing the
   ready state without depending on audio source ended callbacks.
5. **Console timing instrumentation**: Open browser DevTools (F12) to view live timing:
   ```text
   click→started 0.15s | first frame 4.36s | first sound ~5.0s | frames buffered 32 of 85
   stalls: 0
   ```
   (Times above are illustrative; actual first-frame time on the RTX 3060 measured ~4.36 s.)
   Global timing metrics are accessible anytime via `window.avatarTiming`.
6. **Tuning for your hardware** (in `avatar_kiosk/web/app.js`):
   - `SAFETY_FRAMES` (default `12`, ~0.5 s): Raise to `20`–`25` if running heavy background
     GPU workloads (e.g. Whisper or Ollama simultaneously) and `stalls > 0`.
   - `MIN_START_FRAMES` (default `12`): Minimum buffer threshold before audio starts.
   - `REBUFFER_FRAMES` (default `25`): Buffer cushion before resuming after a dry pause.

### Speaking image clarity

The speed-oriented default is now **1440 pixels on the longest side**, with
**6 sampling steps**, **render stride 5**, and **JPEG quality 85**. JPEG retains
full color resolution (**4:4:4**). The browser reuses repeated render-stride
pictures in its buffer and avoids decoding an unchanged picture again.

This is a quality/speed tradeoff: 1440 is the full portrait's height, not its
width. The portrait is approximately 810×1440, and the browser's face crop is
only about 405 pixels wide before enlargement to 720 pixels. Speaking can
therefore look softer than idle. The previous 2560 setting supplied a native
720-pixel crop. Both browser renderers still use a 720-pixel output width.

To preserve the earlier source detail while keeping the cheaper sampling and
stride settings, stop the existing backend and launch with:

```bash
AVATAR_MAX_SIZE=2560 AVATAR_JPEG_QUALITY=92 ./start-avatar-browser.sh
```

To restore all previous rendering settings:

```bash
AVATAR_MAX_SIZE=2560 AVATAR_SAMPLING_STEPS=10 AVATAR_RENDER_STRIDE=3 AVATAR_JPEG_QUALITY=92 ./start-avatar-browser.sh
```

Current local artifacts:

- [Idle / previous speech / updated speech comparison](outputs/speech-clarity-comparison.jpg)
- [Higher-resolution speech preview with audio](outputs/clear-speech-preview.mp4)
- [Combined head/hat/expression browser preview, silent](outputs/browser-aligned-head-preview.webm)

Backend rendering/config changes require a service restart. Browser JavaScript
changes require a hard refresh and reconnect. Voice JSON speed changes apply to
the next synthesis without either step.

## Native desktop quick start on this configured machine

```bash
cd /home/force-1/Downloads/Voice-Avatar
./start-avatar.sh
```

Wait for **Ready**, type a sentence, then click **Speak text** or press **Ctrl+Enter**.
**Stop speaking** interrupts it. Choose **Emotion → auto** for English text cues, or
select any of the eleven presets listed under Speaking expressions below. **Idle blinking**
is enabled by default. **Natural movement** toggles breathing, sway, coordinated
head/hat motion, and conversational tilt/nod cues. Use Alt+Tab to find **Chef · Food ordering assistant**
if another application covers the window.

For a fresh installation, complete **Setup** and then the demo voice installation
below before using text-to-speech. Do not run a second launcher while one is active.

After updating the code, close the existing Chef window and relaunch to load both
the new desktop controls and worker settings. If you started the service manually,
stop that terminal with Ctrl+C too. For “Port 8765 already has a service”, see
Troubleshooting below.

## Optional adaptive playback

Close the old launcher/window (and any manually launched service), then run:

```bash
AVATAR_RENDER_STRIDE=5 ./start-avatar.sh --playback-mode adaptive
```

`--playback-mode adaptive` measures packet arrival speed per reply. It starts
before the renderer finishes only after **three consecutive measurement windows**
(each at least 0.5 seconds) sustain at least **30 packets/second**, versus 25 needed
for playback. It also requires at least **0.8 seconds of queued audio**, with a
larger reserve for observed delivery gaps. This observation time begins with the
first received frame, not the user's button click. Short replies or insufficient
rendering headroom fall back to waiting for `done`.

The service now forwards frames at rendering speed instead of artificially pacing
them at 25 packets/second. Restart the service as well as the desktop to use this
change. The existing bounded queues and slow-display errors still apply.

The default stride of 5 renders fewer unique facial images than the previous 3;
audio is unchanged, but facial animation may be less smooth. It is a setting to
benchmark, not a guarantee of sufficient rendering speed. The ordinary command
`./start-avatar.sh` retains **complete** buffering by default.

No arrival-rate estimate can predict a later GPU or network stall. If adaptive
playback exhausts its reserve, it pauses, buffers the remaining reply, and disables
early starts for subsequent turns until the desktop is restarted. The UI reports
that fallback. Thus adaptive mode reduces delay when there is sustained headroom;
it cannot promise gap-free speech under arbitrary future load. Use
`--playback-mode complete` when avoiding renderer-related mid-reply gaps matters
more than start latency.

To measure local GPU output without playing sound, with other GPU renderers closed:

```bash
.venv/bin/python scripts/benchmark_playback.py outputs/temperature-speech-check.wav --stride 5
```

The recorded stride-5 check on this machine used 9.265 seconds of audio. First
frame arrival was 7.57 seconds, rendering finished at 16.97 seconds, and both
modes scheduled first audio at 17.00 seconds. Adaptive mode correctly stayed in
complete-buffer mode because the arrival rate did not provide the required
headroom. Both modes preserved PCM with zero simulated underruns. This run does
**not** demonstrate a latency improvement; rendering still needs to be faster for
early starts on that workload. See [recorded results](outputs/adaptive-playback-check.json).

This saves `outputs/adaptive-playback-check.json` with first-frame time,
render-complete time, first scheduled audio for both modes, underruns, and PCM
preservation. It simulates DAC callbacks on live GPU output; it does not measure
speaker hardware or WebSocket transport. Use your own WAV path if this local
sample is absent.

## What is included

- Local HTTP sidecar with text-to-speech, Piper WAV, and streaming PCM input.
- Browser studio with synchronized audio/video, portrait/full-character views, and Stop.
- Persistent Ditto worker, cached image registration, online frame output.
- Native desktop display with paired audio/video playback driven by the speaker clock.
- Text-entry demo with a local English voice, automatic/manual emotions, and optional idle/body movement.
- Idle eyelid blinking without running continuous GPU inference.
- Sentence-level expression timelines and optional per-reply metadata for WAV/PCM clients.
- Face stabilization, shared head/hat gestures, damped charm swing, and idle blinking.
- Higher-resolution speaking frames and a configurable, slightly slower Piper voice.
- VAD interruption endpoint; stale turn IDs are rejected.
- Bounded queues, input limits, timeout handling, and explicit errors when models/GPU are missing.
- A small standard-library Python client for the existing voice agent.

The optional text demo synthesizes speech locally; it does not invent menu data
or submit orders. For the external voice-agent integration, the avatar
display owns audio playback; playing the same WAV in the old TTS code would cause
duplicate speech and lose synchronization.

## Text-to-speech demo

The browser has a **Speak message** button; the desktop has **Speak text**. Type an English
sentence and click the button (or press Ctrl+Enter). **Stop speaking** cancels
speech generation or playback. This is direct text-to-speech, not an LLM chatbot.
The current demo limit is 800 characters; short replies work best.

The demo voice is installed in a separate environment so Piper's CPU ONNX runtime
does not replace Ditto's GPU runtime. It runs locally after the one-time download:

```bash
python3.12 -m venv .venv-piper
.venv-piper/bin/pip install piper-tts==1.8.0
.venv-piper/bin/python -m piper.download_voices --download-dir models/piper en_US-lessac-medium
```

The interpreter and voice files were verified present on this machine during this
documentation check. Restart the desktop to load
the text controls if an older window is open. Optional overrides: `PIPER_PYTHON`
and `PIPER_MODEL`. Default voice: English `en_US-lessac-medium`.

CLI equivalent with the browser or native display connected to the service:

```bash
.venv/bin/python examples/speak_text.py "Welcome! What would you like to order?"
```

Earlier expression artifacts: [sad v2](outputs/emotion-sad-v2.mp4),
[happy v2](outputs/emotion-happy-v2.mp4),
[before/after face comparison](outputs/emotion-v2-comparison.jpg),
[idle blink video](outputs/idle-blink-preview.mp4), and
[blink states](outputs/idle-blink-states.jpg). These older artifacts document earlier checks. See the current browser and clarity
previews below for the latest rendering behavior.

### Persistent voice worker and preparation delay

Piper now stays running between sentences and replies. `demo_tts.synthesize()`
sends requests to one managed subprocess through JSON lines. That subprocess
runs inside `.venv-piper`, loads `PiperVoice` once, and returns WAV bytes.
Piper's CPU dependencies remain separate from Ditto's GPU environment.

The production service preloads the voice in the background at startup while
Ditto loads. Browser text entry, desktop text entry, and the normal text CLI all
use the service's shared Piper worker through `POST /speak-text`. Standalone
WAV export (`--wav-only`) and direct `demo_tts` calls use a process-local worker.
Only one voice synthesis request runs at a time; the GPU renderer can run in
parallel with it. Sentence audio remains contiguous and expression offsets are
measured from the actual output samples.

Stop during active synthesis terminates the voice worker to discard pending
output safely; the next request reloads it. A timeout, crash, or protocol error
also clears the worker so a later request can recover. Normal completed requests
keep it alive. Service shutdown and normal process exit close the subprocess.
A missing optional voice does not prevent external WAV/PCM operation.

**Measured on 23 November 2026:** for the same three-sentence text, the former
per-sentence Piper CLI took **2.39 seconds** to prepare speech. The persistent
worker loaded once in **0.42 seconds**, then prepared complete replies in
**0.08–0.11 seconds**, reusing the same process for all nine test sentences.
This saved roughly **2.3 seconds per warm reply in that sample**, not a guaranteed
saving for every message. These timings exclude Ditto rendering and the browser's
desktop complete-reply playback buffer (or the browser's streaming start rule delay), which still contribute to initial delay.

Reproduce the voice-only benchmark without connecting a display:

```bash
.venv/bin/python scripts/benchmark_voice.py
```

Restart the avatar service once after installing this code change. When using
`./start-avatar-browser.sh`, stop its terminal with Ctrl+C and launch it again;
then reconnect the existing browser tab. Subsequent voice-speed JSON edits still
apply to new synthesis without restarting.

### Overlapping sentence voice generation and GPU rendering

The text endpoint now queues **each sentence as soon as its voice is ready**,
instead of waiting for a complete paragraph WAV:

1. The persistent CPU Piper worker synthesizes sentence 1 and converts it to
   16 kHz PCM.
2. The service starts one avatar turn and queues sentence 1 with its emotion.
3. The separate GPU worker starts setup/audio processing while Piper synthesizes
   sentence 2. Each further sentence follows the same path.
4. The service sends a single end command after the last sentence. The **browser**
   uses dynamic streaming playback and starts audio as soon as enough frames are ready;
   the **desktop display** buffers the complete reply before speaking (by default).

`server.py` awaits each sentence on a background thread, then calls
`Runtime.feed_sentence()`. The command carries PCM and emotion together. Inside
`worker.py`, the next expression cue is appended **before** that sentence's audio
is processed, at `accumulated_PCM_bytes / 32000` seconds. All sentences share the
same renderer, audio windowing, and playback clock; no per-sentence renderer
restart or extra playback gap is inserted. The frontend continues its Thinking
animation until speech starts.

This overlaps two preparation stages; it does not speed up the browser's start rule or
make GPU rendering faster. Ditto also needs lookahead audio, so a short first
sentence may not immediately produce visible frames. The time saved depends on
how much voice synthesis remains after sentence 1. With persistent Piper already
preparing short replies in about 0.1 seconds, this extra saving may be small;
GPU rendering and full-reply buffering still dominate the initial wait.

Stop or a display disconnect cancels ongoing Piper synthesis and interrupts the
partial GPU turn. A later sentence failure also discards the partial reply.
Requests are limited to 800 characters, 100 sentences, and 90 seconds of generated
audio, plus the existing playback memory bound. Sentence commands use the bounded
worker queue; the producer holds only the current sentence's PCM.

The browser and native desktop text controls use this automatically. Python clients
can opt into the same path without constructing WAVs or expression timestamps:

```python
avatar.speak_text("Hello! I am here to help. What would you like to order?")
```

Existing `speak_wav`, PCM streaming, and standalone WAV-export behavior remain
available. Restart the service after installing the pipeline change; reconnect
the browser (or restart the desktop to load its new text-entry client).

To verify against the actual GPU, first stop the running avatar service to avoid
a second model instance, then run:

```bash
.venv/bin/python scripts/check_sentence_pipeline.py
```

This checks sequential versus pipelined preparation, exact returned PCM, and
per-frame emotion labels at the measured boundaries. Its timings are single runs
with stochastic voice durations, not a controlled latency benchmark.

Latest real-GPU check on 23 November 2026: first audio queued in **0.025 s** with
pipelining versus **0.105 s** sequentially. Both runs preserved every PCM sample
and all per-frame expression labels. Complete-render times were 11.24 s and
10.70 s respectively, but the synthesized replies differed in duration (3.43 s
versus 3.20 s), so this does **not** establish an overall playback-delay speedup.
See [recorded results](outputs/sentence-pipeline-check.json). The demonstrated
improvement is earlier GPU input/setup and the ability to overlap subsequent
synthesis, not a promise of instant playback.

### Voice pace

The active voice is configured in
[`models/piper/en_US-lessac-medium.onnx.json`](models/piper/en_US-lessac-medium.onnx.json):

```json
"inference": {
  "noise_scale": 0.667,
  "length_scale": 1.18,
  "noise_w": 0.8
}
```

`length_scale` is now **1.18**, up from **1.12**: approximately **5% slower than
that previous setting**, or **15% slower than the original 1.0 setting**. Speed is
approximately inversely proportional to this value; exact duration varies with
text and synthesis. Larger values slow speech; smaller values speed it up.
The pitch and sample rate are not changed to achieve the slower pace.

The persistent Piper worker rereads the small JSON inference settings for each
synthesis call without reloading the model, so no service restart or
browser refresh is needed for this setting. New sentences use the updated pace;
already-generated audio keeps its existing speed. Sentence offsets are measured
from the generated PCM, so lip movement and expressions stay synchronized.
This applies to browser text entry, the desktop text demo, and the text CLI.
Externally supplied WAV/PCM must be slowed by the application generating it.

The `models/` directory is ignored by version control. A fresh voice download or
replacement can reset this local setting: set `inference.length_scale` back to
`1.18` in the adjacent `.onnx.json` file after downloading. If `PIPER_MODEL` points
to a different voice, edit that voice's JSON configuration instead.

### Pronouncing temperatures and units

The text demo normalizes explicit symbols before passing text to Piper. For example,
`24°C` is sent as **24 degrees Celsius**, so the voice reads the temperature instead
of saying the letter C. This also applies to the CLI text demo.

| Written text | Text sent to the voice |
|---|---|
| `24°C`, `24 ° C`, `24℃` | `24 degrees Celsius` |
| `75°F`, `75℉` | `75 degrees Fahrenheit` |
| `−1°C` | `minus 1 degree Celsius` |
| `24–26°C` | `24 to 26 degrees Celsius` |
| `250ml`, `1 kg` | `250 milliliters`, `1 kilogram` |
| `20%`, `tea & coffee` | `20 percent`, `tea and coffee` |

Common explicit units (`kg`, `g`, `mg`, `ml`, `mL`, `km`, `cm`, `L`), degree
symbols, signed temperatures, basic bold/link markup, and long dashes are handled.
Ordinary letters, such as **Vitamin C**, and menu names are preserved. This is
conservative English normalization, not a general abbreviation/pronunciation engine.
The text displayed in the editor and sent for emotion selection is unchanged.

A fresh Piper WAV using the supplied Bahrain sentence is saved at
[temperature-speech-check.wav](outputs/temperature-speech-check.wav).
Already-generated external WAV/PCM cannot be corrected by changing this service's
text metadata. In the external voice agent, normalize the text **before its TTS**:

```python
from avatar_kiosk.speech_text import normalize_speech_text
spoken_text = normalize_speech_text(response_text)
# Pass spoken_text to the external agent's speech synthesizer.
```

### Speaking expressions and idle blinking

The **Emotion** selector defaults to **auto**. The browser, desktop, and text CLI
send text to the service, which synthesizes and queues sentences incrementally.
It uses measured PCM boundaries to select a new expression for each sentence. Facial controls blend
toward the new preset over roughly half a second, while jaw articulation follows
Ditto. The whole paragraph remains one playback turn. The status and head cues
follow the expression of the frame currently reaching the speaker.
Manual selection applies that mood throughout. Timed turns use a neutral Ditto
condition plus the facial controls below, avoiding a lingering first-sentence mood.
Sentence synthesis can add preparation time and change phrasing at boundaries.

**Expressive v2 correction:** the original approach changed the emotion label but
Ditto's relative-motion reference could subtract the sustained emotional pose;
its expression mask also replaced non-eye/non-lip movement with the source face.
The adapter now retains full facial expression motion and restores a bounded
upper-face offset against the neutral warmup reference. Direct neural controls
add distinct eyebrow, eyelid, gaze, and mouth-corner cues after that subtraction.
Jaw and phonetic open/close controls are left to the audio model. Mouth-corner
bias can still affect perceived articulation, so check actual speech visually.
These controls ease in over roughly half a second and vary gently with the
matching audio energy; they are not fixed 2D eyebrow warps. The earlier
`face_expression.py` overlay is no longer used by the desktop or preview renderer.
The keypoint meanings were cross-checked against the public
[AdvancedLivePortrait expression editor](https://github.com/PowerHouseMan/ComfyUI-AdvancedLivePortrait/blob/main/nodes.py);
this project uses its own small preset table in `emotion_motion.py` and adds no
new model dependency.

The desktop defaults to a closer **portrait view** so expressions are visible.
Enable **Full character** to restore the full-body framing. After speech, the face
blends back to the idle portrait over 350 ms. The status shows **Speaking · sad**
(or the active preset), and the window title is **Chef · Expressive avatar v2**.
Both desktop and service must be restarted after updating. The new desktop rejects
an old service with a clear restart message; `/health` reports
`"animation_revision": "expressive-v2"` for the current service.

| Selection | Facial / movement behavior | Example text in auto mode |
|---|---|---|
| neutral | Ditto neutral | “Your order is number twelve.” |
| happy | Ditto happy, lifted smile corners, softened eyes | “Welcome! Enjoy your meal.” |
| sad | Ditto sad, reduced smile, softer eyelids and raised brows | “Sorry, that dish is sold out.” |
| surprise | Ditto surprise with raised brows | “Wow, that is amazing!” |
| thinking | Ditto neutral, asymmetric brows, small gaze shift and head tilt | “Hmm, let me check.” |
| suggestion | Mixed happy/neutral, light brow lift, gentle nod | “I recommend the soup.” |
| curious | Asymmetric brow lift and attentive eyes | “How can I help?” |
| concerned | Inner brow lift and restrained mouth corners | “Are you worried?” |
| excited | Lifted brows, wider eyes, smile, buoyant nod | “Fantastic!” |
| reassuring | Softer eyes, restrained smile, gentle affirmative nod | “I am here to help.” |
| skeptical | Asymmetric brows and smile, questioning head tilt | “Are you sure?” |

Thinking, suggestion, curious, concerned, excited, reassuring, and skeptical are
conversational presets, not additional trained emotion classes. The browser
enables shared head/hat movement automatically. On desktop, head cues require
**Natural movement**; facial controls still work when that toggle is off. The strength of the generated expression depends on the
portrait and Ditto model; the supplied portrait already has a smile, so sadness
may remain subtle. Piper's voice/prosody is not changed by the emotion selector.

Auto mode is a small English phrase matcher, not an LLM or audio emotion
recognizer. It selects cues independently for each sentence in the text demo:
reassurance, skepticism, excitement, apologies, concern, surprise, thinking,
suggestions, greetings, then questions (in that priority order).
Unmatched sentences use neutral. Negation and sarcasm can be misclassified;
manual selection or explicit API timelines give callers control.

External WAV and streaming callers can pass `timeline=[{"start": 0,
"emotion": "happy"}, {"start": 2.4, "emotion": "concerned"}]` to
`KioskAvatar.speak_wav()` or `begin()`. Starts are seconds relative to the supplied
audio, must increase, and must begin at zero. The HTTP query parameter `timeline`
is the JSON-encoded list (at most 100 cues). Supply actual TTS sentence timestamps;
text alone does not align an arbitrary recording. Without a timeline, external
calls retain one expression per turn. Explicit timelines take precedence over
the turn-level emotion. Invalid timelines return HTTP 422 before starting a turn.

Try **auto** with: “Hello! I am sorry that happened. Are you worried?
I recommend trying again. How can I help?” Restart the service and desktop after
updating to load sentence-level controls.

**Idle blinking** closes and reopens both eyelids over 240 ms, with randomized
2.5–5.5 second pauses. It runs on the desktop timer and is independent of
**Natural movement**. The idle blink resets when a speech turn starts; Ditto owns
the eyes during speech. It uses a local eyelid deformation calibrated to
`Avatar/avatar.jpg`, applied before the shared head/hat movement. A replacement
portrait requires updating eye coordinates in both `avatar_kiosk/idle_blink.py`
(desktop) and `avatar_kiosk/web/motion.js` (browser).
No additional packages or model downloads are required for these features.

CLI examples (service running and one browser or desktop display connected):

```bash
.venv/bin/python examples/speak_text.py "Wow, that is amazing!"
.venv/bin/python examples/speak_text.py "Let me check your order." --emotion thinking
.venv/bin/python examples/speak_text.py "I recommend the soup." --emotion suggestion
```

### Natural movement

The desktop's **Natural movement** toggle enables gentle breathing, weight shift,
and small head tilts while idle and speaking. A shared 2D transform moves the head,
hair, and the full hat together, with more visible eased tilts during speech.
The hanging hat chain/tassel inherits that movement, then adds a small damped swing
around its attachment point. It lags changes in head tilt and settles toward a
vertical hanging position. **Natural movement** enables both the shared tilt and
the charm swing. See the [hat/charm motion preview](outputs/hat-charm-motion.mp4).
This is a local 2D deformation calibrated to the supplied portrait; it is not a
cloth simulation or a separately rigged 3D accessory. A different portrait needs
its charm pivot and deformation region recalibrated in `ambient_motion.py`.
Ditto is configured to generate expressions/lip sync only,
so it no longer independently turns the face under a static hat. Motion eases
between idle and speaking and anchors the feet rather than moving the entire image.

This is a lightweight portrait animation layer, not a full 3D skeleton or generated
hand gestures. It is tuned to the supplied full-body image; a different character
crop will require adjusting the head/neck and chest regions in `ambient_motion.py`
and the eye coordinates in `idle_blink.py`. Update the corresponding source
coordinates in `avatar_kiosk/web/motion.js` for the browser too.
The movement is applied by the desktop display. API consumers that implement their
own player can reuse that module to get the same effect.

The **Test avatar** button plays `outputs/avatar-final-preview.wav` (an older saved
sample); it does not read the text box. Use **Speak text** to speak what you typed.
On a fresh checkout that saved sample may not exist; the text demo does not need it.

## Setup

Run commands from this project directory. Python 3.10–3.12 is recommended for
Ditto; the default system Python 3.13 is not the environment used here.

If `vendor/ditto` was not included when copying the project, restore the pinned
source first (skip these commands if it is already present):

```bash
git clone https://github.com/antgroup/ditto-talkinghead.git vendor/ditto
git -C vendor/ditto checkout c3e47eee2e626500017a0556b470d6d4182f85e8
```

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-ditto.txt torch==2.5.1 torchvision==0.20.1
.venv/bin/pip install -e .
.venv/bin/python scripts/download_models.py
.venv/bin/python scripts/doctor.py
```

Keep `.venv` dedicated to the avatar. Other voice-agent packages (such as Pipecat
or LiveKit) may require CPU ONNX Runtime or newer Protobuf versions and should use
a separate environment. This avatar pins GPU ONNX Runtime 1.20.2 and Protobuf
4.25.8 for MediaPipe 0.10.21. A CPU `onnxruntime` installation can overwrite the
GPU package's shared module even when `pip show onnxruntime-gpu` still lists it.

The official source is checked out at `vendor/ditto`, commit
`c3e47eee2e626500017a0556b470d6d4182f85e8`. Keep this revision when using the adapter:
it relies on the online SDK's writer and overlap behavior. Original source and
license files are preserved. Weights come from `digital-avatar/ditto-talkinghead`
on Hugging Face; configuration pickle files must come from that trusted source.

On Linux the native display also needs Tk and PortAudio system libraries
(commonly `python3-tk` and `libportaudio2`). Ditto's image blending extension needs
a C/C++ compiler and Python development headers. `doctor.py` reports missing
Python module availability, model-path presence, and GPU access. It does not modify
drivers or system packages, check the optional Piper demo voice, or prove that
sound reaches your chosen speaker.

## Run

Both components can be started together:

```bash
./start-avatar.sh
# Optional: ./start-avatar.sh --fullscreen
```

Closing the window also stops the service when using this launcher. Alternatively:

Start the sidecar in one terminal:

```bash
.venv/bin/python -m uvicorn avatar_kiosk.server:app --host 127.0.0.1 --port 8765 --workers 1
```

Start the native kiosk display in another terminal:

```bash
.venv/bin/python -m avatar_kiosk.desktop
# Add --fullscreen for the kiosk. Escape leaves fullscreen.
```

Wait for the display to report ready. Test with an actual WAV made by your Piper:

```bash
.venv/bin/python examples/send_wav.py /path/to/piper-response.wav
```

The service can start without weights to expose diagnostic status at
`http://127.0.0.1:8765/health`; speech requests are rejected until the GPU worker
is ready. No substitute lip-sync model is used on failure; the desktop's independent
idle motion may still move the image. If the display
disconnects on an initialization error, fix the error and restart both processes.

## Connect the existing voice agent

The reference document is `vendor/ditto/voice-kiosk-readme.md`. Its linked source
directory `/home/force-4/Documents/Kiosk Voice Agent` is not on this machine.
Apply these changes in the actual voice-agent checkout when available:

1. Install this package in that project's environment with
   `pip install -e /absolute/path/to/Voice-Avatar`. The client uses the standard library.
2. In `tts.py`, after Piper produces its WAV, replace the direct speaker playback
   with `avatar.speak_wav(wav_path)` below. Keep the WAV until that call returns.
3. On Silero speech-start in `vad.py`/`main.py`, cancel the current TTS task, then
   call `avatar.interrupt()` so queued speech is discarded too.
4. Wait for `avatar.status()['state'] == 'ready'` before submitting the next turn.
   A 409 means loading/busy/no display; handle it in the existing playback scheduler.
5. Keep existing fallback audio behavior explicit: Edge-TTS output must be decoded
   to PCM16 WAV before sending. pyttsx3 direct speaker output cannot drive this
   avatar unless captured to an audio file first.

```python
from avatar_kiosk.client import KioskAvatar

avatar = KioskAvatar("http://127.0.0.1:8765")
turn_id = avatar.speak_wav("piper-response.wav", text="Welcome! What would you like?")
# On customer speech-start, after cancelling the current TTS generation:
avatar.interrupt()
```

Pass the exact spoken text (up to 800 characters) for automatic expression cues,
or choose an explicit emotion without supplying text:

```python
avatar.speak_wav("piper-response.wav", emotion="sad")
# For streaming, select the expression before feeding audio:
turn = avatar.begin(emotion="suggestion")
# feed_pcm16(turn, ...), then end(turn), as described below.
```

Both arguments are optional and old clients remain compatible; an audio-only turn
without metadata uses neutral. The server does not transcribe audio for expression
selection. Metadata travels to the GPU worker, and the `started` WebSocket event
includes the resolved `emotion` for desktop head cues. Interruption and subsequent
turns do not inherit the previous emotion.

See `examples/chef_integration.py` for hook functions. This is an integration
template because the actual voice-agent implementation was not supplied.

For incremental Piper audio, use `begin()`, `feed_pcm16(turn, chunk)`, and
`end(turn)`. Stream input is **16 kHz mono signed little-endian PCM16** with no WAV
header. Each request must contain whole samples and at most 1 second of audio.
Resample with a stateful resampler when the Piper voice emits a different sample
rate; do not independently resample each chunk. The WAV endpoint automatically
converts mono/stereo PCM16 WAV at 8–96 kHz to the required format.

## API and playback

| Endpoint | Purpose |
|---|---|
| `GET /` | Browser avatar studio |
| `POST /speak-text` | JSON text/emotion; synthesize speech with measured sentence timings |
| `GET /health` | Worker state, missing assets, and display connection |
| `POST /speak` | Raw PCM16 WAV body; returns a turn ID |
| `POST /turns` | Begin a streaming turn |
| `POST /turns/{id}/audio` | Raw 16 kHz PCM16 bytes |
| `POST /turns/{id}/end` | Flush model context and finish the turn |
| `POST /interrupt` | Stop queued output while keeping models loaded |
| `WS /events` | Paired JPEG + PCM packets with turn IDs and timestamps |

`POST /speak` and `POST /turns` accept optional query parameters `emotion`
(`auto`, `neutral`, `happy`, `sad`, `surprise`, `thinking`, `suggestion`,
`curious`, `concerned`, `excited`, `reassuring`, `skeptical`), optional JSON `timeline`, and `text`
(up to 800 characters). Invalid emotions or oversized text return HTTP 422 before
a turn is started. The Python client URL-encodes these parameters. Spoken text
passed this way may appear in HTTP access logs; omit it and send an explicit
emotion if that is undesirable. The WAV/PCM body formats are unchanged.

One kiosk, one display, one active turn are supported. Bind to loopback as shown;
this is a local sidecar, with no authentication layer for public hosting. OpenAPI
documentation is available at `/docs`.

The text-to-speech demo runs in the desktop process, not in an HTTP text endpoint.
External integrations send audio through `/speak` or the streaming endpoints.

For a custom WebSocket player, events include `status`, `ready`, `started`, `audio_length`,
`frame`, `done`, `interrupted`, and `error`. An `audio_length` event is sent right after
voice generation and contains `turn` (turn ID string) and `frames` (integer: total expected
frame count — used by the browser's start rule). A `frame` contains `turn`, zero-based `index`,
`pts_ms`, and base64-encoded `jpeg` and `pcm` data (16 kHz mono signed PCM16).
`done` means generation/delivery has finished, not that the speakers have finished.
After playing the last sample, send `{"type":"played","turn":"YOUR_TURN_ID"}`
on the same WebSocket. The service stays in `playing` until this acknowledgment;
the included desktop handles it automatically.

Each output packet contains 40 ms of audio and its corresponding image. The desktop
uses PortAudio's DAC timestamp to display the face when the matching audio reaches
the speakers. By default, the desktop buffers the **entire reply** before starting audio.
The old three-frame (120 ms) buffer could empty repeatedly when GPU rendering was
slower than playback, inserting audible silence between pieces of a sentence.
The display now shows **Buffering reply for smooth playback…**, then **Speaking**
only after the audio callback starts consuming the completed reply.

This deliberately trades a longer wait before speech for uninterrupted sample
playback. Short sentences reduce that wait. Streaming PCM input is still accepted,
but the desktop waits for the turn to end and all output packets to arrive before
speaking in complete mode. Adaptive mode may start sooner when its rate checks
pass. Live conversation with very low latency needs a renderer that can keep
up with audio; a small buffer alone cannot make a slow renderer real time.

Frames are retained as compressed JPEGs, decoded only when due on the display
clock. The queue is bounded to 90 seconds and 256 MiB per reply; an oversized reply
fails explicitly. Stop speaking discards buffered audio immediately, including
while preparation is in progress. PortAudio uses its high-latency device setting
for additional output headroom; DAC timestamps still align video with the speaker.
The final partial audio frame is zero-padded to 40 ms. These changes do not alter
Piper's speech samples, pitch, or speaking speed, and do not guarantee against
unrelated hardware/device underruns.

## Current limitations and GPU acceptance checks

- The source is a stylized full-body character. Ditto animates expressions while
  the browser and desktop add shared head/hat motion and subtle body movement. It does not
  create waving hands or walking.
- Interruption clears playback and cancels outstanding rendering. The model stays
  loaded; the real-service test returned to ready in about 0.15 seconds. A stuck
  worker is terminated by the watchdog and reported as an error.
- Maximum utterance duration is 90 seconds, also subject to the 256 MiB playback
  buffer limit. Higher-resolution replies can reach the memory limit sooner. The Chef README's short replies fit
  within this limit. It does not support multiple customer sessions.
- GPU rendering is verified. Review lip accuracy with your actual Piper voice and
  restaurant audio before deployment; frame/audio timestamps and sample preservation
  are tested, but this does not establish phoneme-level perceptual accuracy.
- Validate code, weight, and auxiliary-model licenses separately for commercial use.

For final voice-agent acceptance, test a short greeting, a longer menu reply, and repeated
turns. Confirm the mouth follows the first/last syllables, the last word is not
cut off, voice remains unchanged, and interruption stops output. Measure latency
to first audible reply and sustained FPS while Whisper and Ollama also run.

Environment overrides: `DITTO_REPO`, `DITTO_DATA_ROOT`, `DITTO_CONFIG`,
`AVATAR_IMAGE`, `AVATAR_MAX_SIZE` (default longest side 1440), `AVATAR_RENDER_STRIDE`
(default 5; 1 renders every frame and was slower than real time here),
`AVATAR_BATCH_SIZE` (default 2), `AVATAR_SAMPLING_STEPS` (default 6),
`AVATAR_JPEG_QUALITY` (default 85, clamped to 1–100). Changes apply after a backend
restart; refreshing the browser alone does not reload worker settings.

### GPU preparation optimizations (23 November 2026)

The default worker now uses 1440 / 6 steps / stride 5 / JPEG 85. Stride 5
produces five distinct neural face pictures per second, while PCM and packet
positions remain at 25 per second. Browser head/hat motion still runs on its
animation clock. Voice speed and sentence expression timing are unchanged.
Desktop display buffering behavior is unchanged (complete mode by default). Fewer distinct mouth pictures can make lip motion less smooth.

A controlled-input smoke check used the same 2.82125-second WAV on the RTX 3060:

| Preset | First frame | Complete render | PCM preserved |
| --- | ---: | ---: | --- |
| Previous: 2560 / 10 / 3 / 92 | 4.85 s | 9.58 s | Yes |
| Speed default: 1440 / 6 / 5 / 85 | 4.36 s | 7.27 s | Yes |
| Sharp alternative: 2560 / 6 / 5 / 92 | 4.36 s | 7.65 s | Yes |

The sharp alternative retained source detail for about 0.38 seconds more than
the speed preset in this sample. Its [timing report](outputs/render-sharp-fast.json)
and [preview](outputs/render-sharp-fast.mp4) are also saved.

The speed default used about 24% less preparation time in this single comparison, not a
universal speed guarantee. Measurements exclude model startup and Piper, include
preview video encoding, and were made on a shared GPU. The browser uses dynamic
streaming playback and does not wait for the whole reply; first-frame time is still not
time to audible speech (the start rule delay also applies).
Source resizing affects composition/encoding; the neural model's internal crop
sizes remain fixed. Reducing source size alone does not proportionally reduce
all GPU work.

Reproduce with the backend stopped so two copies do not compete for VRAM:

```bash
AVATAR_MAX_SIZE=2560 AVATAR_SAMPLING_STEPS=10 AVATAR_RENDER_STRIDE=3 AVATAR_JPEG_QUALITY=92 .venv/bin/python scripts/smoke_render.py outputs/clear-speech-preview.wav --seconds 3 --output outputs/render-baseline.mp4
.venv/bin/python scripts/smoke_render.py outputs/clear-speech-preview.wav --seconds 3 --output outputs/render-fast.mp4
```

Each preview has an adjacent JSON timing report and JPEG first frame. The smoke
checker verifies that all input PCM is preserved, including the final partial
stride. Current reports: [baseline](outputs/render-baseline.json) and
[speed preset](outputs/render-fast.json). Config and JPEG encoding are edited in
`avatar_kiosk/config.py` and `avatar_kiosk/worker.py`; benchmark metadata is in
`scripts/smoke_render.py`.

**TensorRT status: not enabled.** This installation has no `tensorrt` Python
runtime, ONNX source models, TensorRT engines, or matching online TensorRT config.
Changing a flag cannot convert the installed PyTorch checkpoints. The bundled
[Ditto instructions](vendor/ditto/README.md) describe the compatible runtime and
engine assets; its converter is `vendor/ditto/scripts/cvt_onnx_to_trt.py`.
A separate TensorRT environment and matching assets must be provisioned and
validated before switching the running service. Use `DITTO_DATA_ROOT` for the
compatible engine directory and `DITTO_CONFIG` for
`v0.4_hubert_cfg_trt_online.pkl` together, then run the same smoke check before
adopting that backend. No TensorRT speedup has been measured or claimed here.

Check `nvidia-smi` before comparisons. If Whisper, Ollama, or another workload is
using the GPU, close it through its own application when appropriate and repeat
the same-input test. This change does not terminate unrelated applications.

## Tests

```bash
.venv/bin/pip install pytest httpx
.venv/bin/python -m pytest -q
node tests/browser_motion.test.cjs
```

Tests exercise text emotion selection/overrides, API emotion validation and worker
metadata, idle blink timing, eyebrow easing and mouth-region preservation, WAV validation/resampling,
streaming chunk boundaries, playback
clock synchronization, stale-turn rejection, cancellation, playback acknowledgments,
and API lifecycle. Pipeline tests verify that sentence 1 reaches the worker before
sentence 2 finishes synthesis, cancellation during the second sentence, later
synthesis failures, manual overrides, and sentence/duration limits. The latest full verification passed **95 Python tests and
8 browser motion tests**. Browser checks also exercised real GPU speech playback,
Stop, mobile layout, WebGL/Canvas motion, and eye-region-only idle blinking. API tests were run outside
the restricted sandbox, where its event-loop restrictions had stalled them.
Adaptive tests cover sustained fast delivery, slow/borderline delivery, misleading
bursts, unexpected stalls, complete-buffer fallback, interruption, and exact PCM
packet playback.
The tests additionally cover the supplied temperature sentence, explicit units,
unchanged ordinary text, charm lag/settling, and shared head/hat motion regions.
A fresh normalized Piper WAV and an eight-second hat-motion preview were generated;
the preview frames were visually inspected.
The tests cover neutral-reference restoration without shared-state mutation,
keeping phonetic channels out of the added controls, bounded speech emphasis,
and distinct happy/sad/surprise presets. The legacy 2D accent module is also
covered but is no longer in the display path. GPU previews were rendered for
expressive-v2 sadness and happiness using the same 3-second greeting audio;
compare these visually rather than treating preset names as proof of quality.
The updated smoke renderer checks returned PCM against the input exactly.
Playback regression tests simulate generation five times slower than playback,
verify every buffered PCM packet plays consecutively, exercise replies beyond the
old 10-second queue limit, and verify cancellation during buffering. A fresh
Piper sample was generated at `outputs/voice-playback-check.wav`; physical speaker
output was not recorded during this check.
The initial GPU check exposed incompatible CPU ONNX Runtime and Protobuf packages
in `.venv`; the GPU runtime and MediaPipe-compatible Protobuf were restored and
pinned before successful rendering. Preview JSON files contain measured timings;
these short runs shared the GPU with an existing process and are not latency
acceptance benchmarks. Tests do not establish the perceptual quality of every emotion or audible speaker output.

To generate a fresh preview with the current movement layer, first create a demo WAV:

```bash
mkdir -p outputs
.venv/bin/python examples/speak_text.py "Welcome! What would you like to order?" --wav-only outputs/demo-greeting.wav
.venv/bin/python scripts/smoke_render.py outputs/demo-greeting.wav --seconds 4 --ambient --output outputs/natural-avatar-preview.mp4
```

To render a chosen expression, add `--emotion`, for example:

```bash
.venv/bin/python scripts/smoke_render.py outputs/demo-greeting.wav --seconds 2 --ambient --emotion surprise --output outputs/emotion-surprise-preview.mp4
```

The rendering command uses its own GPU worker and does not require the service or
desktop. Close the running demo first to avoid loading a second set of GPU models.

For real-service checks, start **only the sidecar** using the manual command above,
leave the desktop closed, and run:

```bash
mkdir -p outputs
.venv/bin/python scripts/check_service.py
```

That script occupies the single display connection, verifies actual generated
frames and audio, acknowledges playback, and checks cancellation without playing
sound. It writes `outputs/service-check.json`. It must not compete with the desktop
for the display connection. Unit tests alone do not establish GPU inference success.

## Troubleshooting

With the service and window open and no reply playing:

```bash
.venv/bin/python scripts/doctor.py --service
tail -n 40 outputs/server.log
```

- **A turn ID prints but nothing is visible:** the ID means the audio was accepted.
  Find the Chef window with Alt+Tab. The terminal itself does not display animation.
- **Choppy speech or pauses between words:** restart the desktop after updating.
  It now waits for a complete reply before playing; **Buffering reply for smooth
  playback…** is expected. A longer initial wait replaces repeated audio gaps.
  If an already buffered reply still crackles, check the system output device/load.
- **Animation but no sound:** playback uses the system default audio output. Check
  Ubuntu Settings → Sound → Output and its volume; a connected headset may receive
  the audio instead of the monitor speakers.
- **Browser changes are missing:** refresh the existing tab with Ctrl+Shift+R,
  then click Connect avatar. Only one display may connect at a time.
- **Voice pace is too fast or slow:** adjust `inference.length_scale` in the Piper
  JSON file below. Larger values are slower. This affects newly synthesized speech,
  not a WAV that is already generated or supplied by another application.
- **Speech looks blurrier than idle:** the speed preset uses a smaller source image.
  Set `AVATAR_MAX_SIZE=2560 AVATAR_JPEG_QUALITY=92` to restore source detail. Restart the backend after changing worker/config code;
  refresh the browser after frontend changes.
- **New desktop controls are missing / old service warning:** close the old desktop and
  restart both components with `./start-avatar.sh`. The title should read
  **Chef · Expressive avatar v2** and `/health` should report `expressive-v2`.
- **Expressions seem wrong:** choose an explicit emotion; auto mode uses phrase
  cues per sentence in the text demo. Send a timed `timeline=` from external clients for sentence changes.
  Check the **Speaking · emotion** status, turn off **Full character** for a closer
  view, and ensure both service and display are on expressive-v2.
- **Eyes do not blink:** in the browser, blinking is automatic; on desktop, enable
  **Idle blinking**. Wait up to 6 seconds while idle,
  and confirm the image is the supplied portrait. Speech uses Ditto's eyes.
- **Port 8765 already has a service:** use the existing demo or stop it first. Closing
  a launcher-started window stops both components; with the manual two-terminal setup,
  stop the sidecar separately with Ctrl+C in its terminal. If that terminal is lost or
  the process is still holding the port in the background, run:

  ```bash
  fuser -k 8765/tcp
  ```

  Or identify the PID with `lsof -iTCP:8765 -sTCP:LISTEN` and run `kill <PID>`.
- **Busy/not ready:** wait for `ready` or interrupt the current turn. A disconnected
  display or missing final playback acknowledgment also prevents the next turn.
- **Demo voice missing:** complete the isolated `.venv-piper` setup above. Do not
  install Piper's CPU ONNX runtime into Ditto's `.venv`.
- **MediaPipe `GetPrototype` / `TaskRunner.create` errors or missing CUDA provider:**
  conflicting dependencies may have been installed into `.venv`. Restore the avatar
  packages (keep Pipecat/LiveKit and Piper in separate environments):

  ```bash
  .venv/bin/pip uninstall -y onnxruntime
  .venv/bin/pip install --force-reinstall --no-deps onnxruntime-gpu==1.20.2 protobuf==4.25.8
  ```

  Restart both components after repair.
- **GPU inaccessible only from a sandbox:** verify `nvidia-smi` in a normal local
  terminal before assuming the host driver is broken.

The launcher writes server output to `outputs/server.log`; desktop errors appear
in the terminal used to launch it. `outputs/desktop.log` exists only when desktop
output was explicitly redirected there. If an initialization error closes the
display connection, correct the cause and restart both components.
