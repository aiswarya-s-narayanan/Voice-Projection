"""Audio framing shared by the worker, HTTP API and tests."""
import io
import math
import wave

import numpy as np
from scipy.signal import resample_poly

RATE = 16000
FPS = 25
SAMPLES_PER_FRAME = RATE // FPS
MAX_SECONDS = 90


def wav_to_pcm(data: bytes) -> bytes:
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            rate, channels, width = wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
            if width != 2 or channels not in (1, 2) or not 8000 <= rate <= 96000:
                raise ValueError("Use PCM16 WAV, mono or stereo, 8–96 kHz")
            if wav.getnframes() > rate * MAX_SECONDS:
                raise ValueError("Speech is limited to 90 seconds per turn")
            raw = wav.readframes(wav.getnframes())
            if len(raw) != wav.getnframes() * channels * width:
                raise ValueError("Truncated WAV")
    except (wave.Error, EOFError) as exc:
        raise ValueError("Expected an uncompressed PCM16 WAV file") from exc
    if not raw:
        raise ValueError("Audio is empty")
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32).reshape(-1, channels).mean(axis=1)
    if rate != RATE:
        divisor = math.gcd(rate, RATE)
        samples = resample_poly(samples, RATE // divisor, rate // divisor)
    return np.clip(np.rint(samples), -32768, 32767).astype("<i2").tobytes()


class HubertWindows:
    """Overlap windows matching upstream run_chunk((3,5,2)); arbitrary input boundaries."""
    window = 6480
    stride = 3200

    def __init__(self):
        self.pending = np.zeros(1920, dtype=np.float32)

    def feed(self, pcm: bytes):
        if len(pcm) % 2:
            raise ValueError("PCM16 chunks must contain whole samples")
        self.pending = np.concatenate((self.pending, np.frombuffer(pcm, "<i2").astype(np.float32) / 32768))
        while len(self.pending) >= self.window:
            yield self.pending[:self.window].copy()
            self.pending = self.pending[self.stride:]

    def finish(self, tail_frames: int):
        # Flush HuBERT right context and the motion model's future context.
        yield from self.feed(bytes((tail_frames * SAMPLES_PER_FRAME + self.window) * 2))
