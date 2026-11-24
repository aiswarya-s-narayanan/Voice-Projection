"""Optional offline text-to-speech demo, isolated from Ditto's CUDA dependencies."""
from pathlib import Path
import tempfile

from .speech_text import normalize_speech_text
from .persistent_voice import voice


def prepare_voice(cancel):
    return voice.run(None, cancel) is not None


def close_voice():
    voice.close()


def _synthesize_audio(text, cancel):
    text = text.strip()
    if not text:
        raise ValueError("Enter some text first.")
    if len(text) > 800:
        raise ValueError("Please use 800 characters or fewer for the demo.")
    return voice.run(normalize_speech_text(text), cancel)


def synthesize_sentence_pcm(text, cancel):
    """One complete sentence at the renderer's 16 kHz rate, ready to enqueue."""
    from .audio import wav_to_pcm
    audio = _synthesize_audio(text, cancel)
    if audio is None or cancel.is_set():
        return None
    return wav_to_pcm(audio)


def synthesize(text, output, cancel):
    audio = _synthesize_audio(text, cancel)
    if audio is None or cancel.is_set():
        return False
    Path(output).write_bytes(audio)
    return not cancel.is_set()


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
