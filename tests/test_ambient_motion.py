import math
import numpy as np
from PIL import Image
from avatar_kiosk.ambient_motion import AmbientMotion


def test_charm_lags_tilt_then_settles_and_returns():
    motion = AmbientMotion()
    tilt = math.radians(2)
    motion.advance_charm(tilt, .04)
    assert -tilt < motion.charm_angle < 0
    for _ in range(200):
        motion.advance_charm(tilt, .04)
    assert abs(motion.charm_angle + tilt) < 1e-6
    for _ in range(200):
        motion.advance_charm(0, .04)
    assert abs(motion.charm_angle) < 1e-6


def test_charm_bounded_and_head_hat_share_rigid_region():
    motion = AmbientMotion()
    for _ in range(100):
        motion.advance_charm(math.pi, .1)
        assert abs(motion.charm_angle) <= math.radians(8)
    im = Image.new('RGB', (360,640), 'white')
    result = motion.apply(im, 0)
    # Entire hat, face, and tassel above the neck share full head rotation.
    assert np.all(motion.head_weight[:int(.16*640)] == 1)
    assert result.size == im.size
