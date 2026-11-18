"""Audio-clock-driven paired packet playback, independent of the UI toolkit."""
from collections import deque
import threading
import math
import time

from .audio import SAMPLES_PER_FRAME, FPS, MAX_SECONDS


class Playback:
    def __init__(self, mode="complete", clock=time.monotonic):
        if mode not in ("complete", "adaptive"):
            raise ValueError("Playback mode must be complete or adaptive")
        self.mode = mode
        self.clock = clock
        self.adaptive_failed = False
        self.underruns = 0
        self.lock = threading.Lock()
        self.pending = deque()
        self.visible = deque()
        self.turn = None
        self.finished = False
        self.started = False
        self.last_audio_end = 0
        self.received_frames = 0
        self.buffered_bytes = 0
        self._reset_measurements()

    def _reset_measurements(self):
        self.rates = deque(maxlen=3)
        self.gaps = deque(maxlen=100)
        self.window_start = None
        self.last_arrival = None
        self.window_frames = 0
        self.early_ready = False
        self.rebuffering = False

    def reset(self, turn=None):
        with self.lock:
            self.pending.clear()
            self.visible.clear()
            self.turn = turn
            self.finished = False
            self.started = False
            self.last_audio_end = 0
            self.received_frames = 0
            self.buffered_bytes = 0
            self._reset_measurements()

    def finish(self, turn):
        with self.lock:
            if self.turn == turn:
                self.finished = True

    def add(self, turn, pcm, image, emotion=None):
        if len(pcm) != SAMPLES_PER_FRAME * 2:
            raise ValueError("Invalid output audio frame")
        with self.lock:
            if turn != self.turn or self.finished:
                return
            # Keep compressed JPEGs until the UI needs a frame. Full decoded
            # 90-second video would otherwise consume several GB of memory.
            size = len(pcm) + (len(image) if isinstance(image, bytes) else 0)
            if self.received_frames >= FPS * MAX_SECONDS or self.buffered_bytes + size > 256 * 1024 * 1024:
                raise RuntimeError("Reply exceeds the playback buffer limit (90 seconds / 256 MiB)")
            self.received_frames += 1
            self.buffered_bytes += size
            self.pending.append((pcm, (image, emotion) if emotion is not None else image))
            if self.mode == "adaptive" and not self.adaptive_failed:
                now = self.clock()
                if self.last_arrival is not None:
                    self.gaps.append(max(0, now-self.last_arrival))
                self.last_arrival = now
                if self.window_start is None:
                    self.window_start = now
                elapsed = now-self.window_start
                if elapsed >= .5:
                    self.rates.append(self.window_frames/elapsed)
                    self.window_start, self.window_frames = now, 0
                self.window_frames += 1
                reserve = max(.8, 2*max(self.gaps, default=0)+.2)
                self.early_ready = (len(self.rates) == 3 and min(self.rates) >= FPS*1.2
                                    and len(self.pending) >= math.ceil(reserve*FPS))

    def next(self, dac_time):
        with self.lock:
            # Start early only after three sustained rate measurements with 20%
            # headroom. Arrival time is monotonic; DAC time is only for sync.
            eligible = self.early_ready and self.mode == "adaptive" and not self.adaptive_failed
            if not self.finished and (self.rebuffering or (not self.started and not eligible)):
                return bytes(SAMPLES_PER_FRAME * 2)
            if not self.pending:
                if self.started and not self.finished and not self.rebuffering:
                    # A future GPU/network stall cannot be predicted. Pause once,
                    # buffer the remainder, and disable early starts this session.
                    self.underruns += 1
                    self.adaptive_failed = True
                    self.rebuffering = True
                return bytes(SAMPLES_PER_FRAME * 2)
            if self.finished:
                self.rebuffering = False
            self.started = True
            pcm, image = self.pending.popleft()
            self.visible.append((dac_time, image))
            self.last_audio_end = dac_time + 0.04
            return pcm

    def image_at(self, now):
        latest = None
        with self.lock:
            while self.visible and self.visible[0][0] <= now:
                _, latest = self.visible.popleft()
                self.buffered_bytes -= SAMPLES_PER_FRAME * 2 + (len(latest) if isinstance(latest, bytes) else 0)
            if self.finished and not self.pending and not self.visible and now >= self.last_audio_end:
                self.turn = None
        return latest
