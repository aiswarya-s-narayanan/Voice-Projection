import asyncio
import queue
import threading

from avatar_kiosk.config import Settings
from avatar_kiosk.runtime import Runtime
from avatar_kiosk.playback import Playback


def test_interrupt_keeps_worker_and_clears_queued_speech():
    runtime = Runtime(Settings())
    runtime.commands = queue.Queue()
    runtime.cancel = threading.Event()
    runtime.state = "speaking"
    runtime.turn = "old"
    listener = asyncio.Queue()
    listener.put_nowait({"type": "frame", "turn": "old"})
    runtime.listeners.add(listener)
    runtime.interrupt()
    assert runtime.cancel.is_set()
    assert runtime.state == "interrupting"
    assert runtime.turn is None
    assert runtime.commands.get_nowait() == ("end",)
    assert listener.get_nowait()["type"] == "interrupted"
    assert listener.empty()


def test_playback_ack_is_required_and_old_ack_cannot_release_new_turn():
    runtime = Runtime(Settings())
    runtime.state, runtime.turn = "playing", "new"
    runtime.played("old")
    assert runtime.state == "playing"
    runtime.played("new")
    assert runtime.state == "ready" and runtime.turn is None


def test_short_audio_finishes_only_after_last_dac_sample():
    player = Playback()
    player.reset("short")
    player.add("short", b"\1\0" * 640, "face")
    assert player.next(1) == bytes(1280)  # waiting for the complete reply
    player.finish("short")
    assert player.next(2) == b"\1\0" * 640
    player.image_at(2.02)
    assert player.turn == "short"
    player.image_at(2.05)
    assert player.turn is None
