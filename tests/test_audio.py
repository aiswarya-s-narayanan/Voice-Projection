import io
import wave
import numpy as np
import pytest
from avatar_kiosk.audio import HubertWindows, wav_to_pcm


def wav_bytes(samples, rate=22050, channels=1):
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(samples.astype("<i2").tobytes())
    return output.getvalue()


def test_piper_rate_resampling_and_stereo_downmix():
    signal = np.full((22050, 2), [12000, 4000], dtype=np.int16)
    result = np.frombuffer(wav_to_pcm(wav_bytes(signal, channels=2)), "<i2")
    assert len(result) == 16000
    assert abs(result[100:-100].mean() - 8000) < 2


def test_bad_or_empty_wav_rejected():
    for data in (b"not a wav", wav_bytes(np.array([], dtype=np.int16))):
        with pytest.raises(ValueError):
            wav_to_pcm(data)


def test_windows_independent_of_piper_chunk_boundaries():
    pcm = np.arange(16000, dtype=np.int16).tobytes()
    whole = list(HubertWindows().feed(pcm))
    stream = HubertWindows()
    split = []
    for i in range(0, len(pcm), 222):
        split.extend(stream.feed(pcm[i:i + 222]))
    assert len(whole) == len(split)
    for a, b in zip(whole, split):
        np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(whole[0][:1920], 0)
    np.testing.assert_array_equal(whole[0][1920:], np.arange(4560) / 32768)


def test_partial_sample_rejected():
    with pytest.raises(ValueError):
        list(HubertWindows().feed(b"x"))
