"""Single-kiosk supervisor with bounded queues and hard interruption."""
import asyncio
import multiprocessing as mp
import queue
import time
import uuid

from .audio import MAX_SECONDS, RATE
from .worker import run_worker
from .expressions import resolve_emotion
from .config import prepare_gpu_environment


class Runtime:
    def __init__(self, settings):
        self.settings = settings
        self.process = None
        self.commands = None
        self.events = None
        self.cancel = None
        self.state = "stopped"
        self.error = None
        self.turn = None
        self.ending = False
        self.samples = 0
        self.changed = time.monotonic()
        self.listeners = set()

    def status(self):
        return {"state": self.state, "error": self.error, "turn": self.turn,
                "animation_revision": "expressive-v2",
                "display_connected": bool(self.listeners), "missing": self.settings.missing()}

    def start(self):
        self.stop()
        self.state, self.error = "loading", None
        self.changed = time.monotonic()
        prepare_gpu_environment()
        ctx = mp.get_context("spawn")
        self.commands, self.events = ctx.Queue(512), ctx.Queue(50)
        self.cancel = ctx.Event()
        self.process = ctx.Process(target=run_worker, args=(self.settings, self.commands, self.events, self.cancel), daemon=True)
        self.process.start()

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process.join(timeout=1)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=1)
            self.process.close()
            self.process = None
        for q in (self.commands, self.events):
            if q:
                q.cancel_join_thread()
                q.close()
        self.commands = self.events = None
        self.turn = None
        self.ending = False

    def begin(self, emotion="neutral", timeline=None):
        emotion = resolve_emotion(emotion)
        if timeline is not None:
            from .expression_timeline import validate_timeline
            timeline = validate_timeline(timeline)
        if self.state != "ready" or self.turn:
            raise ValueError("Avatar is not ready: " + self.state)
        if not self.listeners:
            raise ValueError("Connect the avatar display before speaking")
        self.turn = uuid.uuid4().hex
        self.samples = 0
        self.ending = False
        self.state = "speaking"
        self.changed = time.monotonic()
        self.commands.put_nowait(("begin", self.turn, emotion, timeline) if timeline else ("begin", self.turn, emotion))
        return self.turn

    def feed(self, turn, pcm):
        if turn != self.turn or self.ending:
            raise ValueError("Turn is closed or interrupted")
        if not pcm or len(pcm) % 2 or len(pcm) > RATE * 2:
            raise ValueError("Send whole PCM16 samples in chunks of at most one second")
        if self.samples + len(pcm) // 2 > RATE * MAX_SECONDS:
            raise ValueError("Turn exceeds 90 seconds")
        self.commands.put_nowait(("audio", pcm))
        self.samples += len(pcm) // 2
        self.changed = time.monotonic()

    def end(self, turn):
        if turn != self.turn or self.ending or not self.samples:
            raise ValueError("No open nonempty turn")
        self.commands.put_nowait(("end",))
        self.ending = True
        self.changed = time.monotonic()

    def broadcast(self, event):
        for listener in tuple(self.listeners):
            try:
                listener.put_nowait(event)
            except asyncio.QueueFull:
                # Never discard individual audio frames and silently desynchronize.
                while not listener.empty():
                    listener.get_nowait()
                listener.put_nowait({"type": "error", "message": "Display too slow; reconnect"})
                self.listeners.discard(listener)

    def interrupt(self):
        if self.turn is None:
            return
        for listener in self.listeners:
            while not listener.empty():
                listener.get_nowait()
        self.broadcast({"type": "interrupted", "turn": self.turn})
        self.cancel.set()
        if not self.ending:
            self.commands.put_nowait(("end",))
        self.turn = None
        self.ending = False
        self.state = "interrupting"
        self.changed = time.monotonic()

    def played(self, turn):
        if self.state == "playing" and turn == self.turn:
            self.turn = None
            self.ending = False
            self.state = "ready"
            self.broadcast({"type": "ready"})

    async def pump(self):
        while True:
            if self.events:
                for _ in range(50):
                    try:
                        event = self.events.get_nowait()
                    except queue.Empty:
                        break
                    kind = event["type"]
                    if kind in ("started", "frame", "done") and event.get("turn") != self.turn:
                        continue
                    if kind == "ready":
                        self.state = "ready"
                    elif kind == "done":
                        self.state = "playing"
                    elif kind == "error":
                        self.error = event["message"]
                        self.state = "error"
                        self.stop()
                    self.changed = time.monotonic()
                    self.broadcast(event)
                    if kind == "frame":
                        # Deliver at rendering speed so adaptive clients can measure
                        # headroom and build a reserve. Queues remain bounded; slow
                        # listeners still receive the explicit reconnect error.
                        await asyncio.sleep(0)
                    if kind == "error":
                        break
            if self.process and not self.process.is_alive():
                self.error = "Ditto worker exited unexpectedly"
                self.state = "error"
                self.stop()
                self.broadcast({"type": "error", "message": self.error})
            if self.process and self.state in ("loading", "speaking", "playing", "interrupting") and time.monotonic() - self.changed > 180:
                self.error = "Ditto timed out; check GPU and model configuration"
                self.state = "error"
                self.stop()
                self.broadcast({"type": "error", "message": self.error})
            await asyncio.sleep(0.01)
