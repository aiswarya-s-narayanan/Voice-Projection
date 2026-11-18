import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from avatar_kiosk.expressions import resolve_emotion, EMOTIONS, DITTO_EMOTIONS
from avatar_kiosk.idle_blink import IdleBlink
from avatar_kiosk.server import create_app
from avatar_kiosk.config import Settings
from test_server import FakeRuntime
from test_audio import wav_bytes


@pytest.mark.parametrize('text, expected', [
    ('Welcome! Enjoy your meal.', 'happy'),
    ('Wow, that is amazing!', 'surprise'),
    ('Sorry, that dish is sold out.', 'sad'),
    ('Hmm, let me check.', 'thinking'),
    ('I recommend the soup.', 'suggestion'),
    ('Your order is number 12.', 'neutral'),
    ('Welcome! Unfortunately that is unavailable.', 'sad'),
    ('This is a thoughtful choice.', 'neutral'),
])
def test_text_cues(text, expected):
    assert resolve_emotion('auto', text) == expected


def test_manual_override_and_invalid_emotion():
    assert resolve_emotion('sad', 'Welcome!') == 'sad'
    with pytest.raises(ValueError):
        resolve_emotion('unknown')
    assert set(DITTO_EMOTIONS) == set(EMOTIONS)


@pytest.mark.parametrize('route', ['/speak', '/turns'])
def test_emotion_metadata_reaches_worker_and_validation_is_atomic(route):
    runtime = FakeRuntime(Settings())
    with TestClient(create_app(runtime)) as client:
        with client.websocket_connect('/events') as ws:
            ws.receive_json()
            data = wav_bytes(np.ones(22050, dtype=np.int16)) if route == '/speak' else b''
            for params in ({'emotion': 'bogus'}, {'text': 'x'*801}):
                assert client.post(route, params=params, content=data).status_code == 422
                assert runtime.turn is None and runtime.commands.empty()
            result = client.post(route, params={'text': 'I recommend the soup.'}, content=data)
            assert result.status_code == 200
            assert runtime.commands.get_nowait() == ('begin', result.json()['turn'], 'suggestion')


def test_blink_schedule_and_speech_reset():
    blink = IdleBlink(seed=7)
    assert blink.amount(0) == 0
    start = blink.next_blink
    assert 2.5 <= start <= 5.5
    assert blink.amount(start + .1) == 1
    assert blink.amount(start + .3) == 0
    assert blink.amount(start + .4, idle=False) == 0
    assert blink.next_blink is None
    assert blink.amount(10) == 0
    assert blink.next_blink > 12


def test_blink_only_changes_eye_regions_and_preserves_mouth():
    # Coordinate gradients expose any unintended remapping outside the eyelids.
    y, x = np.mgrid[:3344, :1882]
    image = Image.fromarray(np.stack((x % 255, y % 255, (x+y) % 255), axis=-1).astype('uint8'))
    result = np.asarray(IdleBlink.render(image, 1))
    original = np.asarray(image)
    assert np.any(result[300:395, 795:1020] != original[300:395, 795:1020])
    assert np.array_equal(result[400:], original[400:])
    assert np.array_equal(result[:270], original[:270])
    assert IdleBlink.render(image, 0) is image


def test_expression_accents_ease_out_and_preserve_lips():
    from avatar_kiosk.face_expression import FaceExpression
    y, x = np.mgrid[:1280, :720]
    image = Image.fromarray(np.stack((x % 255, y % 255, (x+y) % 255), axis=-1).astype('uint8'))
    effect = FaceExpression()
    for i in range(30):
        result = effect.apply(image, i*.04, 'surprise', speaking=True)
    assert np.any(np.asarray(result) != np.asarray(image))
    assert np.array_equal(np.asarray(result)[150:], np.asarray(image)[150:])
    assert effect.values[0] > 12
    for i in range(30, 90):
        effect.apply(image, i*.04, 'surprise', speaking=False)
    assert np.max(np.abs(effect.values)) < .01
