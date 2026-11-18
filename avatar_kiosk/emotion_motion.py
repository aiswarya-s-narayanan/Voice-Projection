"""Preserve sustained neural emotion through Ditto's relative-motion adapter."""
import math
import numpy as np

# Ditto's expression channels for phonetic mouth movement.
LIP_POINTS = (6, 12, 14, 17, 19, 20)


def restore_emotion(motion, first, neutral, seconds, emotion):
    """Keep neutral-relative upper-face emotion without changing lip articulation.

The upstream online SDK always sets d0 to the first prediction, even when
relative_d=False. Adding its emotion offset back before stitching prevents that
reference from cancelling sustained upper-face expression. The original objects
are shared with upstream threads and must never be mutated.
    """
    if first is None or neutral is None or emotion == "neutral":
        return motion
    offset = np.clip(first['exp'] - neutral['exp'], -.025, .025).copy().reshape(-1, 21, 3)
    offset[:, LIP_POINTS, :] = 0
    onset = 1 - math.exp(-max(0, seconds) / .3)
    emphasis = .88 + .12 * math.cos(seconds * 1.7)
    result = dict(motion)
    result['exp'] = motion['exp'] + (onset * emphasis * offset).reshape(motion['exp'].shape)
    return result

# Sparse portrait-specific expression controls. Keypoint semantics were checked
# against AdvancedLivePortrait's public expression editor (calc_fe):
# https://github.com/PowerHouseMan/ComfyUI-AdvancedLivePortrait/blob/main/nodes.py
# These are tuned offsets, not a copied editor or an additional model dependency.
# (point, axis, delta): brows 1/2, lids 11/13/15/16, mouth corners 14/20.
PRESETS = {
    'neutral': (),
    'curious': ((1, 1, .004), (2, 1, -.002), (11, 1, -.0015), (15, 1, -.0015)),
    'concerned': ((1, 1, .004), (2, 1, -.004), (14, 1, .003), (20, 1, .002)),
    'happy': ((14, 1, -.006), (20, 1, -.0035), (13, 1, -.0008), (16, 1, -.0008)),
    'sad': ((1, 1, .005), (2, 1, -.005), (14, 1, .010), (20, 1, .006),
            (11, 1, .0018), (15, 1, .0018)),
    'surprise': ((1, 1, .007), (2, 1, -.007), (11, 1, -.004), (15, 1, -.004),
                 (13, 1, .0012), (16, 1, .0012)),
    'thinking': ((1, 1, .0045), (2, 1, -.001), (11, 0, .0018), (15, 0, .0018),
                 (14, 1, .003), (20, 1, .002)),
    'suggestion': ((1, 1, .003), (2, 1, -.002), (14, 1, -.003), (20, 1, -.0015)),
}


def expression_controls(emotion, seconds, energy=0.0):
    """Smooth onset and phrase emphasis, added after relative-motion stitching.

Only mouth corners are biased; jaw/open-close phonetic channels are not driven
by this layer. Energy is a bounded RMS cue, not an emotion classifier.
    """
    delta = np.zeros((1, 21, 3), dtype=np.float32)
    onset = 1 - math.exp(-max(0, seconds) / .22)
    intensity = onset * (.88 + .12 * math.cos(seconds * 1.6))
    intensity *= 1 + .12 * max(0, min(1, energy))
    for point, axis, amount in PRESETS.get(emotion, ()):
        delta[0, point, axis] = amount * intensity
    return delta.reshape(1, 63)


class SentenceExpression:
    """Blend changing presets on the audio clock, including short sentences."""
    def __init__(self, cues):
        self.cues = cues
        self.value = np.zeros((1, 63), dtype=np.float32)
        self.last_seconds = 0.0

    def sample(self, seconds, energy=0.0):
        from .expression_timeline import cue_at
        cue = cue_at(self.cues, seconds)
        # The stateful blend handles onset; keep target emphasis within each phrase.
        target = expression_controls(cue['emotion'], seconds - cue['start'] + 1, energy)
        dt = max(0, seconds - self.last_seconds)
        self.value += (target - self.value) * (1 - math.exp(-dt / .18))
        self.last_seconds = seconds
        return self.value.copy()
