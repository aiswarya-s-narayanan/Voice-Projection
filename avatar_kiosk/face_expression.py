"""Legacy preview-only module; not used by the expressive-v2 desktop.

Restrained eyebrow accents for the supplied portrait, leaving lips untouched.

Ditto supplies neural facial motion. These calibrated upper-face cues make the
conversational presets visible even on a small full-body desktop display.
"""
import math

import cv2
import numpy as np
from PIL import Image


class FaceExpression:
    # Per eyebrow: vertical lift and inward slope, in source-portrait pixels.
    PRESETS = {
        "neutral": (0, 0, 0, 0),
        "happy": (5, -3, 5, 3),
        "sad": (1, 10, 1, -10),
        "surprise": (13, 0, 13, 0),
        "thinking": (9, -3, -2, 0),
        "suggestion": (6, -2, 3, 0),
    }

    def __init__(self):
        self.values = np.zeros(4, np.float32)
        self.last_time = None

    def apply(self, image, seconds, emotion="neutral", speaking=False):
        dt = 0 if self.last_time is None else max(0, min(.1, seconds-self.last_time))
        self.last_time = seconds
        target = np.asarray(self.PRESETS.get(emotion if speaking else "neutral", self.PRESETS["neutral"]))
        self.values += (target-self.values) * (1-math.exp(-dt/.25))
        if np.max(np.abs(self.values)) < .01:
            return image
        frame = np.asarray(image).copy()
        height, width = frame.shape[:2]
        sx, sy = width/1882, height/3344
        for i, (cx, cy, slope) in enumerate(((844, 320, -.35), (970, 293, -.32))):
            rx, ry = 59, 25
            x0, x1 = max(0, int((cx-rx)*sx)), min(width, math.ceil((cx+rx)*sx))
            y0, y1 = max(0, int((cy-ry-rx*abs(slope))*sy)), min(height, math.ceil((cy+ry+rx*abs(slope))*sy))
            yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
            u = (xx/sx-cx)/rx
            v = (yy/sy-cy-slope*(xx/sx-cx))/ry
            weight = np.clip(1-u*u, 0, 1)**2 * np.clip(1-v*v, 0, 1)**2
            lift, tilt = self.values[2*i:2*i+2]
            map_y = yy + (lift+tilt*u)*weight*sy
            frame[y0:y1, x0:x1] = cv2.remap(np.asarray(image), xx, map_y.astype(np.float32), cv2.INTER_LINEAR)
        return Image.fromarray(frame)
