"""Subtle 2D movement for this full-body portrait, applied after facial compositing.

The head region includes the hat. Ditto must use expression-only motion so its
face does not independently rotate inside this shared head/hat transform.
"""
import math

import cv2
import numpy as np
from PIL import Image


def smoothstep(start, end, value):
    value = np.clip((value - start) / (end - start), 0, 1)
    return value * value * (3 - 2 * value)


class AmbientMotion:
    def __init__(self):
        self.size = None
        self.last_time = None
        self.speaking_amount = 0.0
        self.expression_tilt = 0.0
        self.expression_nod = 0.0
        self.charm_angle = 0.0
        self.charm_velocity = 0.0

    def apply(self, image, seconds, speaking=False, emotion="neutral"):
        width, height = image.size
        if self.size != image.size:
            self.size = image.size
            self.y, self.x = np.mgrid[:height, :width].astype(np.float32)
            self.ny = self.y / height
            # Head, face, hair and hat share exactly the same rigid transform.
            # A soft transition across the neck avoids a cutout seam.
            self.head_weight = 1 - smoothstep(0.165, 0.235, self.ny)
            self.upper_weight = 1 - smoothstep(0.65, 0.94, self.ny)
            self.chest_weight = np.exp(-((self.ny - 0.285) / 0.12) ** 2)

        dt = 0 if self.last_time is None else max(0, min(0.1, seconds - self.last_time))
        self.last_time = seconds
        self.speaking_amount += (float(speaking) - self.speaking_amount) * (1 - math.exp(-dt / 0.7))
        activity = self.speaking_amount
        # Thinking: attentive tilt. Suggestion: soft affirmative nod.
        tilt = {"thinking": -2.2, "sad": 0.8, "happy": 0.7, "suggestion": 0.45}.get(emotion, 0) if speaking else 0
        nod = (0.0013 * math.sin(seconds * 2.4)) if speaking and emotion == "suggestion" else 0
        ease = 1 - math.exp(-dt / 0.45)
        self.expression_tilt += (tilt - self.expression_tilt) * ease
        self.expression_nod += (nod - self.expression_nod) * ease
        breath = math.sin(2 * math.pi * seconds / 4.8)
        sway = 0.75 * math.sin(2 * math.pi * seconds / 8.7) + 0.25 * math.sin(2 * math.pi * seconds / 13.1)

        # Small weight shift around the feet. The lower hem and feet remain anchored.
        lean = math.radians(0.32) * sway
        map_x = self.x + lean * (self.y - height * 0.91) * self.upper_weight
        map_y = self.y - lean * (self.x - width * 0.5) * self.upper_weight

        # Breathing is a restrained chest expansion, not whole-image zooming.
        map_x = map_x - (self.x - width * 0.5) * (0.003 * breath) * self.chest_weight
        map_y = map_y + height * 0.0011 * breath * self.upper_weight

        angle = math.radians(0.65 + 0.35 * activity) * math.sin(2 * math.pi * seconds / 6.3)
        angle += math.radians(self.expression_tilt)
        px, py = width * 0.49, height * 0.19
        dx, dy = map_x - px, map_y - py
        head_x = px + math.cos(angle) * dx + math.sin(angle) * dy
        head_y = py - math.sin(angle) * dx + math.cos(angle) * dy
        # Tiny shared vertical movement during speech, eased in/out above.
        head_y += height * 0.0008 * activity * math.sin(2 * math.pi * seconds / 2.9)
        head_y += height * self.expression_nod
        map_x += (head_x - map_x) * self.head_weight
        map_y += (head_y - map_y) * self.head_weight

        # The chain/tassel inherits the head+hat transform, then swings around
        # its own attachment point. Gravity seeks vertical; damping creates a
        # delayed counter-swing when the head changes direction.
        self.advance_charm(angle, dt)
        cx, cy = width * (1118 / 1882), height * (345 / 3344)
        local_x, local_y = map_x - cx, map_y - cy
        horizontal = 1 - smoothstep(width * 35/1882, width * 72/1882, np.abs(local_x))
        vertical = smoothstep(height * 2/3344, height * 25/3344, local_y)
        vertical *= 1 - smoothstep(height * 195/3344, height * 225/3344, local_y)
        weight = horizontal * vertical
        cosine, sine = math.cos(self.charm_angle), math.sin(self.charm_angle)
        charm_x = cx + cosine * local_x + sine * local_y
        charm_y = cy - sine * local_x + cosine * local_y
        map_x += (charm_x - map_x) * weight
        map_y += (charm_y - map_y) * weight

        frame = cv2.remap(np.asarray(image), map_x.astype(np.float32), map_y.astype(np.float32),
                          cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                          borderValue=(255, 255, 255))
        return Image.fromarray(frame)

    def advance_charm(self, head_angle, dt):
        """Bounded damped pendulum, integrated independently of display cadence."""
        remaining = max(0.0, min(.1, dt))
        while remaining > 1e-9:
            step = min(.01, remaining)
            acceleration = 42 * (-head_angle - self.charm_angle) - 5.5 * self.charm_velocity
            self.charm_velocity += acceleration * step
            self.charm_angle += self.charm_velocity * step
            limit = math.radians(8)
            if abs(self.charm_angle) > limit:
                self.charm_angle = max(-limit, min(limit, self.charm_angle))
                self.charm_velocity = 0.0
            remaining -= step
