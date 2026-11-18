"""Lightweight eyelid compression calibrated to Avatar/avatar.jpg.

Only used on the original idle portrait. Speech uses Ditto's generated eyes.
The local remap closes the eye along its tilted lid line and stretches adjacent
skin into the vacated space. No GPU inference or painted overlay is needed.
"""
import math
import random

import cv2
import numpy as np
from PIL import Image


class IdleBlink:
    def __init__(self, seed=None):
        self.random = random.Random(seed)
        self.next_blink = None
        self.duration = 0.24

    def amount(self, seconds, idle=True):
        if not idle:
            self.next_blink = None
            return 0.0
        if self.next_blink is None:
            self.next_blink = seconds + self.random.uniform(2.5, 5.5)
        elapsed = seconds - self.next_blink
        if elapsed < 0:
            return 0.0
        if elapsed >= self.duration:
            self.next_blink = seconds + self.random.uniform(2.5, 5.5)
            return 0.0
        # Fast close, short hold, slower reopening.
        if elapsed < 0.08:
            return math.sin(elapsed / 0.08 * math.pi / 2) ** 2
        if elapsed < 0.12:
            return 1.0
        return math.cos((elapsed - 0.12) / 0.12 * math.pi / 2) ** 2

    @staticmethod
    def render(image, amount):
        if amount <= 0:
            return image
        frame = np.asarray(image).copy()
        height, width = frame.shape[:2]
        # Centers, half-widths, eye half-height, surrounding skin extent, lid slope.
        # Coordinates are in the supplied 1882 x 3344 portrait, before ambient motion.
        for cx, cy, rx, ry, outer, slope in (
            (844, 357, 45, 18, 34, -0.10),
            (972, 331, 44, 18, 34, -0.35),
        ):
            sx, sy = width / 1882, height / 3344
            x0, x1 = max(0, int((cx-rx-2)*sx)), min(width, math.ceil((cx+rx+2)*sx))
            y0, y1 = max(0, int((cy-outer-rx*abs(slope)-2)*sy)), min(height, math.ceil((cy+outer+rx*abs(slope)+2)*sy))
            yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
            u = (xx / sx - cx) / rx
            center = (cy + slope * (xx / sx - cx)) * sy
            dy = yy - center
            # Taper to an identity map at each eye corner.
            taper = np.clip((1 - u*u) * 2, 0, 1)
            closure = min(1.0, amount) * taper
            inner = ry * sy
            extent = outer * sy
            compressed = inner * (1 - 0.91 * closure)
            absolute = np.abs(dy)
            source = np.where(absolute <= compressed,
                              absolute * inner / np.maximum(compressed, 0.001),
                              inner + (absolute-compressed) * (extent-inner) / (extent-compressed))
            source = np.where(absolute < extent, source, absolute)
            map_y = center + np.sign(dy) * source
            patch = cv2.remap(np.asarray(image), xx, map_y.astype(np.float32), cv2.INTER_LINEAR)
            frame[y0:y1, x0:x1] = patch
        return Image.fromarray(frame)

    def apply(self, image, seconds, idle=True):
        return self.render(image, self.amount(seconds, idle))
