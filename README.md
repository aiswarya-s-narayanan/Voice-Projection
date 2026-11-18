# Chef · Ditto avatar integration

This project provides a talking character using `Avatar/avatar.jpg`, the official
Ditto online pipeline, and a native desktop display. You can type text to test it
with a local Piper demo voice, or send audio from the separate Chef food-ordering
voice agent. Silero, Whisper, Ollama, menu, cart, and order-submission logic remain
in that separate project; this demo does not listen to the microphone or answer
questions by itself.

Documentation updated for speech normalization, hat/charm motion, and emotion controls on **17 November 2026**.

**Status:** the avatar service, native display, and GPU rendering work on this
machine's RTX 3060 (12 GB). Real-service tests verified consecutive replies,
unchanged audio samples, and interruption recovery without model reload. The
voice agent is on your colleague's machine: use [INTEGRATION.md](INTEGRATION.md)
to connect its Piper output. The NVIDIA access failure in the first session was
sandbox isolation, not a broken host driver.

The live preset sends 25 synchronized audio/video packets per second, with a new
neural face every third packet (~8.3 facial updates/second). The desktop separately
animates body/head movement on its 40 ms display timer. Previous service checks
measured 2–3 seconds to the first frame after audio submission; this excludes
voice generation and is not a sub-second or 25-unique-neural-frames/sec guarantee.
**By default, audio playback waits for the complete reply to be rendered and received**
to prevent chopped speech when the GPU is slower than real time. First-frame
rendering timings below are therefore not time-to-first-audible-speech timings.

The earlier body-motion preview is [natural-avatar-preview.mp4](outputs/natural-avatar-preview.mp4),
using a locally generated Piper greeting with the head/hat and body motion enabled.
[Render metrics](outputs/natural-avatar-preview.json) record about 9 seconds for
model loading/warmup and 2.73 seconds to the first frame after that, on the tested
RTX 3060. The older [service checks](outputs/service-check.json) cover consecutive
replies, audio preservation, and interruption recovery. These are saved test results,
not a statement that a service is currently running. Files under `outputs/` are
generated local artifacts and may be absent from a fresh checkout.

## Quick start on this configured machine

```bash
cd /home/force-1/Downloads/Voice-Avatar
./start-avatar.sh
```

Wait for **Ready**, type a sentence, then click **Speak text** or press **Ctrl+Enter**.
**Stop speaking** interrupts it. Choose **Emotion → auto** for English text cues, or
select neutral, happy, sad, surprise, thinking, or suggestion. **Idle blinking**
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

The optional stride of 5 renders fewer unique facial images than the default 3;
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

- Local HTTP sidecar, with Piper WAV and streaming PCM input.
- Persistent Ditto worker, cached image registration, online frame output.
- Native desktop display with paired audio/video playback driven by the speaker clock.
- Text-entry demo with a local English voice, automatic/manual emotions, and optional idle/body movement.
- Idle eyelid blinking without running continuous GPU inference.
- Per-reply emotion metadata for WAV and streaming clients.
- VAD interruption endpoint; stale turn IDs are rejected.
- Bounded queues, input limits, timeout handling, and explicit errors when models/GPU are missing.
- A small standard-library Python client for the existing voice agent.

The optional text demo synthesizes speech locally; it does not invent menu data
or submit orders. For the external voice-agent integration, the avatar
display owns audio playback; playing the same WAV in the old TTS code would cause
duplicate speech and lose synchronization.

## Text-to-speech demo

The desktop window has a text box and **Speak text** button. Type an English
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

CLI equivalent with the avatar window and service running:

```bash
.venv/bin/python examples/speak_text.py "Welcome! What would you like to order?"
```

Current expression artifacts: [sad v2](outputs/emotion-sad-v2.mp4),
[happy v2](outputs/emotion-happy-v2.mp4),
[before/after face comparison](outputs/emotion-v2-comparison.jpg),
[idle blink video](outputs/idle-blink-preview.mp4), and
[blink states](outputs/idle-blink-states.jpg). Files named `*-preview` and the old
2D eyebrow comparison predate the expressive-v2 correction.

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

The **Emotion** selector defaults to **auto**. The desktop and text CLI synthesize
sentences individually, join their PCM into one WAV, and use the measured audio
boundaries to select a new expression for each sentence. Facial controls blend
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

Thinking, suggestion, curious, and concerned are conversational presets, not additional trained emotion
classes. Head cues require **Natural movement**; neural facial emotion controls still work
when that toggle is off. The strength of the generated expression depends on the
portrait and Ditto model; the supplied portrait already has a smile, so sadness
may remain subtle. Piper's voice/prosody is not changed by the emotion selector.

Auto mode is a small English phrase matcher, not an LLM or audio emotion
recognizer. It selects cues independently for each sentence in the text demo:
apologies, concern, surprise, thinking, suggestions, greetings, then questions.
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
portrait requires updating eye coordinates in `avatar_kiosk/idle_blink.py`.
No additional packages or model downloads are required for these features.

CLI examples (service and desktop must be running):

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
and the eye coordinates in `idle_blink.py`.
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
| `GET /health` | Worker state, missing assets, and display connection |
| `POST /speak` | Raw PCM16 WAV body; returns a turn ID |
| `POST /turns` | Begin a streaming turn |
| `POST /turns/{id}/audio` | Raw 16 kHz PCM16 bytes |
| `POST /turns/{id}/end` | Flush model context and finish the turn |
| `POST /interrupt` | Stop queued output while keeping models loaded |
| `WS /events` | Paired JPEG + PCM packets with turn IDs and timestamps |

`POST /speak` and `POST /turns` accept optional query parameters `emotion`
(`auto`, `neutral`, `happy`, `sad`, `surprise`, `thinking`, `suggestion`,
`curious`, `concerned`), optional JSON `timeline`, and `text`
(up to 800 characters). Invalid emotions or oversized text return HTTP 422 before
a turn is started. The Python client URL-encodes these parameters. Spoken text
passed this way may appear in HTTP access logs; omit it and send an explicit
emotion if that is undesirable. The WAV/PCM body formats are unchanged.

One kiosk, one display, one active turn are supported. Bind to loopback as shown;
this is a local sidecar, with no authentication layer for public hosting. OpenAPI
documentation is available at `/docs`.

The text-to-speech demo runs in the desktop process, not in an HTTP text endpoint.
External integrations send audio through `/speak` or the streaming endpoints.

For a custom WebSocket player, events include `status`, `ready`, `started`, `frame`,
`done`, `interrupted`, and `error`. A `frame` contains `turn`, zero-based `index`,
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
  the desktop adds shared head/hat motion and subtle body movement. It does not
  create waving hands or walking.
- Interruption clears playback and cancels outstanding rendering. The model stays
  loaded; the real-service test returned to ready in about 0.15 seconds. A stuck
  worker is terminated by the watchdog and reported as an error.
- Maximum utterance duration is 90 seconds. The Chef README's short replies fit
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
`AVATAR_IMAGE`, `AVATAR_MAX_SIZE` (default longest side 1280), `AVATAR_RENDER_STRIDE`
(default 3; 1 renders every frame and was slower than real time here),
`AVATAR_BATCH_SIZE` (default 1), `AVATAR_SAMPLING_STEPS` (default 10). A TensorRT deployment
must use its corresponding online config and compatible engines together.

## Tests

```bash
.venv/bin/pip install pytest httpx
.venv/bin/python -m pytest -q
```

Tests exercise text emotion selection/overrides, API emotion validation and worker
metadata, idle blink timing, eyebrow easing and mouth-region preservation, WAV validation/resampling,
streaming chunk boundaries, playback
clock synchronization, stale-turn rejection, cancellation, playback acknowledgments,
and API lifecycle. The current run passed **57 tests**. API tests were run outside
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
- **New controls are missing / old service warning:** close the old desktop and
  restart both components with `./start-avatar.sh`. The title should read
  **Chef · Expressive avatar v2** and `/health` should report `expressive-v2`.
- **Expressions seem wrong:** choose an explicit emotion; auto mode uses phrase
  cues per sentence in the text demo. Send a timed `timeline=` from external clients for sentence changes.
  Check the **Speaking · emotion** status, turn off **Full character** for a closer
  view, and ensure both service and display are on expressive-v2.
- **Eyes do not blink:** enable **Idle blinking**, wait up to 6 seconds while idle,
  and confirm the image is the supplied portrait. Speech uses Ditto's eyes.
- **Port 8765 already has a service:** use the existing demo or stop it first. Closing
  a launcher-started window stops both components; with the manual two-terminal setup,
  stop the sidecar separately with Ctrl+C in its terminal. If that terminal is lost,
  run `lsof -iTCP:8765 -sTCP:LISTEN`, identify the avatar service PID, and run
  `kill <PID>` with that actual number before relaunching.
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
