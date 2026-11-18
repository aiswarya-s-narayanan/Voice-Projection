# Connect the separate Chef voice project

The avatar side is implemented here. The voice project is on your colleague's
machine; no menu/cart/ordering code was copied or changed.

## Same machine deployment

Run `./start-avatar.sh` on the kiosk. Copy `avatar_kiosk/client.py` into the voice
project as `avatar_client.py`. This file uses only Python's standard library.

In the voice project's `tts.py`, keep the existing Piper synthesis and replace
the direct WAV speaker-playback call:

```python
from avatar_client import KioskAvatar

avatar = KioskAvatar("http://127.0.0.1:8765")

# After your existing Piper code finishes synthesizing the reply:
turn = avatar.speak_wav(wav_path)
```

Do not also play that WAV in the voice agent: the avatar window plays the audio
with its corresponding face frames. Submit the whole short reply as one turn;
for incremental synthesis use begin/feed/end on that same turn.

Call `avatar.interrupt()` when Silero detects customer speech START, after
cancelling the old TTS task. This immediately clears playback and invalidates
that turn. The models remain loaded. Wait until `avatar.status()['state']` is
`ready` before sending another reply. HTTP 409 means busy/not ready/no display;
HTTP 429 means the streaming input queue is full. Do not silently drop chunks.

For an asyncio voice application, run these synchronous client calls through
`await asyncio.to_thread(...)` so HTTP requests do not block microphone capture.

Piper WAV input must be uncompressed PCM16, mono or stereo, 8–96 kHz. The service
resamples it to 16 kHz. Edge-TTS MP3 must be decoded to WAV first. pyttsx3 direct
speaker output does not supply audio to this avatar.

## Testing between two machines

Keep the avatar service bound to loopback. From the **voice-agent machine**, open
an SSH tunnel to the avatar machine (replace the user and host):

```bash
ssh -N -L 8765:127.0.0.1:8765 USER@AVATAR_MACHINE
```

The client on the voice-agent machine can then use the same
`http://127.0.0.1:8765` URL. Audio and video play on the avatar machine. No API token
or restaurant menu credentials need to be sent to the avatar service.

The native display must be open. It acknowledges completion after the speaker
has played the last audio frame, allowing the next turn to begin without cutting
off the previous reply.

## Quick verification

```python
print(avatar.status())  # state: ready, display_connected: True
avatar.speak_wav("a_real_piper_reply.wav")
# When the customer interrupts:
avatar.interrupt()
```

The current live preset outputs 25 paired audio/video packets per second and
renders a new neural face every third packet (~8.3 visual updates/second). This
keeps speech continuous on the tested RTX 3060. The measured first-frame delay
was about 2–3 seconds after submitting audio; this does not include STT/LLM/TTS
time. See outputs/service-check.json for the local benchmark.
