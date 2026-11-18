"""Optional offline text-to-speech demo, isolated from Ditto's CUDA dependencies."""
import os
from pathlib import Path
import subprocess
import tempfile
import time

from .config import ROOT
from .speech_text import normalize_speech_text


def synthesize(text, output, cancel):
    text = text.strip()
    if not text:
        raise ValueError("Enter some text first.")
    if len(text) > 800:
        raise ValueError("Please use 800 characters or fewer for the demo.")
    text = normalize_speech_text(text)
    python = Path(os.environ.get("PIPER_PYTHON", ROOT / ".venv-piper/bin/python"))
    model = Path(os.environ.get("PIPER_MODEL", ROOT / "models/piper/en_US-lessac-medium.onnx"))
    if not python.exists() or not model.exists():
        raise RuntimeError("Demo voice is not installed. See the Text-to-speech demo section in README.md.")
    if cancel.is_set():
        return False
    with tempfile.TemporaryFile(mode="w+b") as errors:
        process = subprocess.Popen(
            [str(python), "-m", "piper", "--model", str(model), "--output_file", str(output)],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors,
        )
        try:
            process.stdin.write(text.encode("utf-8"))
            process.stdin.close()
            deadline = time.monotonic() + 60
            while process.poll() is None:
                if cancel.wait(0.05):
                    return False
                if time.monotonic() > deadline:
                    raise RuntimeError("Demo voice timed out. Try a shorter sentence.")
            if process.returncode:
                errors.seek(0)
                detail = errors.read().decode("utf-8", errors="replace")[-1500:]
                raise RuntimeError("Piper could not create speech: " + detail)
            return not cancel.is_set()
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def synthesize_sentences(text, output, cancel, emotion='auto'):
    """Synthesize one WAV with exact sentence offsets measured from PCM frames.

    Return the expression timeline, or None when cancelled. Keep a single
    playback turn so sentence changes never restart the renderer or audio clock.
    """
    import wave
    from .expressions import resolve_emotion
    from .expression_timeline import split_sentences

    if not text.strip() or len(text) > 800:
        raise ValueError('Enter between 1 and 800 characters.')
    sentences = split_sentences(text)
    cues, frames, expected = [], 0, None
    with tempfile.TemporaryDirectory(prefix='avatar-sentences-') as temp:
        with wave.open(str(output), 'wb') as joined:
            # Valid header even if cancellation happens before the first sentence.
            joined.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            for index, sentence in enumerate(sentences):
                path = Path(temp) / f'{index}.wav'
                if not synthesize(sentence, path, cancel):
                    return None
                with wave.open(str(path), 'rb') as part:
                    params = (part.getnchannels(), part.getsampwidth(), part.getframerate())
                    if expected is None:
                        expected = params
                        joined.setnchannels(params[0])
                        joined.setsampwidth(params[1])
                        joined.setframerate(params[2])
                    if params != expected or part.getcomptype() != 'NONE' or not part.getnframes():
                        raise ValueError('Sentence voice output has incompatible or empty audio')
                    cues.append({'start': frames / params[2],
                                 'emotion': resolve_emotion(emotion, sentence)})
                    joined.writeframes(part.readframes(part.getnframes()))
                    frames += part.getnframes()
    return None if cancel.is_set() else cues
