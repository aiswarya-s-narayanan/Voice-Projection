"""Remove residual global face pose before the shared portrait head transform.

Ditto's expression field and stitching network can carry global translation,
rotation, and scale even when pitch/yaw/roll are disabled. Fit only structural
keypoints, excluding the explicit eye, brow, and phonetic mouth controls.
"""
import numpy as np

STRUCTURAL_POINTS = (0, 3, 4, 5, 7, 8, 9, 10, 18)


def align_face_to_head(source, driving):
    """Similarity-register the driving face without mutating shared SDK arrays."""
    result = driving.copy()
    for reference, face, output in zip(source, driving, result):
        anchors = face[list(STRUCTURAL_POINTS)].astype(np.float64)
        target = reference[list(STRUCTURAL_POINTS)].astype(np.float64)
        center, target_center = anchors.mean(0), target.mean(0)
        a, b = anchors - center, target - target_center
        variance = np.sum(a * a)
        if variance < 1e-12 or not np.isfinite(a).all() or not np.isfinite(b).all():
            continue
        u, singular, vt = np.linalg.svd(a.T @ b)
        correction = np.ones(3)
        correction[-1] = np.linalg.det(u @ vt)
        rotation = (u * correction) @ vt
        scale = np.sum(singular * correction) / variance
        output[:] = (face - center) @ rotation * scale + target_center
    return result
