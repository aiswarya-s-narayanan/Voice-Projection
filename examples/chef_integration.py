"""Integration template, not a replacement implementation of the Chef agent.

The supplied project has its README only; adapt these hooks to the real tts.py
and vad.py. Keep the existing menu/cart/submission code in the Chef project.
"""
from avatar_kiosk.client import KioskAvatar

avatar = KioskAvatar()


def on_piper_wav_ready(wav_path, *, text="", emotion="auto"):
    # Replace the existing direct WAV speaker playback with this call.
    # Both audio and video are played by avatar_kiosk.desktop.
    return avatar.speak_wav(wav_path, text=text, emotion=emotion)


def on_customer_speech_start():
    # First cancel your agent's current TTS task so it cannot enqueue old speech.
    # Then stop the avatar. Call this on VAD speech START, not end-of-speech.
    return avatar.interrupt()
