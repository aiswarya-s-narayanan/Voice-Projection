import numpy as np
from avatar_kiosk.head_alignment import align_face_to_head, STRUCTURAL_POINTS


def test_residual_pose_is_removed_but_local_eye_and_mouth_motion_survives():
    rng = np.random.default_rng(4)
    source = rng.normal(0, .1, (1, 21, 3)).astype(np.float32)
    expressive = source.copy()
    expressive[0, 14, 1] -= .008
    expressive[0, 11, 1] -= .004
    expressive[0, 6, 1] += .02
    angle = .08
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0],
                         [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    driving = (expressive @ rotation * 1.04 + [.02, -.03, .01]).astype(np.float32)
    before = driving.copy()
    corrected = align_face_to_head(source, driving)
    np.testing.assert_allclose(corrected, expressive, atol=1e-7)
    np.testing.assert_array_equal(driving, before)
    np.testing.assert_allclose(corrected[:, STRUCTURAL_POINTS], source[:, STRUCTURAL_POINTS], atol=1e-7)


def test_degenerate_alignment_is_safe():
    source = np.zeros((1, 21, 3), dtype=np.float32)
    np.testing.assert_array_equal(align_face_to_head(source, source), source)
