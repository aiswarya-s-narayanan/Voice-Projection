import numpy as np
import pytest
from avatar_kiosk.emotion_motion import restore_emotion, expression_controls, LIP_POINTS


def test_restore_sustained_emotion_without_mutating_shared_motion_or_lips():
    motion = {'exp': np.full((1, 63), .002, dtype=np.float32)}
    first = {'exp': np.full((1, 63), .02, dtype=np.float32)}
    neutral = {'exp': np.zeros((1, 63), dtype=np.float32)}
    result = restore_emotion(motion, first, neutral, 1, 'sad')
    assert np.all(motion['exp'] == .002)
    assert result['exp'][0, 3] > motion['exp'][0, 3]
    assert np.array_equal(result['exp'].reshape(21,3)[list(LIP_POINTS)],
                          motion['exp'].reshape(21,3)[list(LIP_POINTS)])
    assert restore_emotion(motion, first, neutral, 1, 'neutral') is motion
    assert restore_emotion(motion, first, None, 1, 'sad') is motion


@pytest.mark.parametrize('emotion', ['happy', 'sad', 'surprise', 'thinking', 'suggestion'])
def test_neural_accents_have_smooth_onset_and_do_not_drive_jaw(emotion):
    assert not expression_controls(emotion, 0).any()
    start = expression_controls(emotion, .04)
    settled = expression_controls(emotion, .8)
    assert 0 < np.linalg.norm(start) < np.linalg.norm(settled)
    assert np.max(np.abs(settled)) < .015
    assert not settled.reshape(21,3)[[6,12,17,19]].any()
    assert np.array_equal(expression_controls(emotion, 1, 1), expression_controls(emotion, 1, 50))


def test_happy_sad_and_surprise_are_distinct_neural_controls():
    happy = expression_controls('happy', 1).reshape(21,3)
    sad = expression_controls('sad', 1).reshape(21,3)
    surprise = expression_controls('surprise', 1).reshape(21,3)
    assert happy[14,1] < 0 < sad[14,1]
    assert surprise[11,1] < 0 < sad[11,1]
    assert not expression_controls('neutral', 1).any()


@pytest.mark.parametrize('emotion', ['excited', 'reassuring', 'skeptical'])
def test_extra_expressions_are_distinct_and_leave_jaw_articulation_alone(emotion):
    from avatar_kiosk.expressions import resolve_emotion, DITTO_EMOTIONS
    assert resolve_emotion(emotion) == emotion
    assert emotion in DITTO_EMOTIONS
    controls = expression_controls(emotion, 1).reshape(21, 3)
    assert controls.any()
    assert not controls[[6, 12, 17, 19]].any()
    assert np.max(np.abs(controls)) < .015
