import json
import threading
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from avatar_kiosk.expression_timeline import split_sentences, validate_timeline
from avatar_kiosk.emotion_motion import SentenceExpression
from avatar_kiosk.demo_tts import synthesize_sentences
from avatar_kiosk.server import create_app
from avatar_kiosk.config import Settings
from avatar_kiosk.playback import Playback
from test_server import FakeRuntime
from test_audio import wav_bytes


def test_sentence_boundaries_preserve_numbers_titles_and_punctuation():
    assert split_sentences('Dr. Smith paid 2.50. Really? Yes!') == [
        'Dr. Smith paid 2.50.', 'Really?', 'Yes!']


def test_tts_offsets_use_actual_samples_and_keep_one_wav(tmp_path, monkeypatch):
    def fake_synthesize(text, output, cancel):
        with wave.open(str(output), 'wb') as wav:
            wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            wav.writeframes(bytes(16000 if text == 'Hello!' else 32000))
        return True
    monkeypatch.setattr('avatar_kiosk.demo_tts.synthesize', fake_synthesize)
    output = tmp_path / 'joined.wav'
    cues = synthesize_sentences('Hello! Sorry, it is sold out. How can I help?', output, threading.Event())
    assert cues == [{'start': 0, 'emotion': 'happy'}, {'start': .5, 'emotion': 'sad'},
                    {'start': 1.5, 'emotion': 'curious'}]
    with wave.open(str(output)) as wav:
        assert wav.getnframes() == 40000
    monkeypatch.setattr("avatar_kiosk.demo_tts.synthesize", lambda *args: False)
    cancel = threading.Event()
    cancel.set()
    assert synthesize_sentences('Hello!', output, cancel) is None


@pytest.mark.parametrize('cues', [[], {}, [{'start': 1, 'emotion': 'happy'}],
    [{'start': float('nan'), 'emotion': 'happy'}], [{'start': True, 'emotion': 'happy'}],
    [{'start': 0, 'emotion': 'auto'}], [{'start': 0, 'emotion': []}],
    [{'start': 0, 'emotion': 'happy'}, {'start': 0, 'emotion': 'sad'}]])
def test_timeline_rejects_invalid_cues(cues):
    with pytest.raises(ValueError):
        validate_timeline(cues)


def test_transition_changes_smile_to_concern_without_jump_or_jaw_motion():
    effect = SentenceExpression([{'start': 0, 'emotion': 'happy'},
                                 {'start': 1, 'emotion': 'sad'},
                                 {'start': 2, 'emotion': 'neutral'}])
    values = [effect.sample(i / 25).reshape(21, 3) for i in range(100)]
    assert values[24][14, 1] < 0 < values[45][14, 1]
    assert np.max(np.abs(values[25] - values[24])) < .004
    assert np.linalg.norm(values[-1]) < .00001
    assert all(not value[[6, 12, 17, 19]].any() for value in values)


@pytest.mark.parametrize('route', ['/speak', '/turns'])
def test_timeline_reaches_worker_and_bad_timing_does_not_start_turn(route):
    runtime = FakeRuntime(Settings())
    cues = [{'start': 0, 'emotion': 'happy'}, {'start': .5, 'emotion': 'concerned'}]
    with TestClient(create_app(runtime)) as client:
        with client.websocket_connect('/events') as ws:
            ws.receive_json()
            wav = wav_bytes(np.ones(22050, dtype=np.int16))
            assert client.post(route, params={'timeline': 'null'}, content=wav).status_code == 422
            if route == '/speak':
                bad = [cues[0], {'start': 2, 'emotion': 'sad'}]
                assert client.post(route, params={'timeline': json.dumps(bad)}, content=wav).status_code == 422
            assert runtime.turn is None and runtime.commands.empty()
            result = client.post(route, params={'timeline': json.dumps(cues)}, content=wav)
            assert result.status_code == 200
            assert runtime.commands.get_nowait()[3] == cues


def test_display_expression_follows_audio_clock_not_packet_arrival():
    playback = Playback()
    playback.reset('turn')
    playback.add('turn', bytes(1280), b'first', 'happy')
    playback.add('turn', bytes(1280), b'second', 'sad')
    playback.finish('turn')
    playback.next(10)
    playback.next(10.04)
    assert playback.image_at(9.99) is None
    assert playback.image_at(10) == (b'first', 'happy')
    assert playback.image_at(10.04) == (b'second', 'sad')
