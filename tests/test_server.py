import asyncio
from fastapi.testclient import TestClient
from avatar_kiosk.server import create_app
from avatar_kiosk.runtime import Runtime
from avatar_kiosk.config import Settings
from test_audio import wav_bytes
import numpy as np
import queue
import threading


class FakeRuntime(Runtime):
    """Exercise real validation/lifecycle logic without pretending to render Ditto."""
    def start(self):
        self.state = "ready"
        self.commands = queue.Queue(512)
        self.cancel = threading.Event()
        self.turn = None
        self.ending = False

    def stop(self):
        pass

    async def pump(self):
        await asyncio.Event().wait()


def test_wav_speech_requires_display_and_queues_audio_then_end():
    runtime = FakeRuntime(Settings())
    with TestClient(create_app(runtime)) as client:
        wav = wav_bytes(np.ones(22050, dtype=np.int16))
        assert client.post("/speak", content=wav).status_code == 409
        with client.websocket_connect("/events") as ws:
            assert ws.receive_json()["type"] == "status"
            response = client.post("/speak", content=wav)
            assert response.status_code == 200
            commands = list(runtime.commands.queue)
            assert commands[0][0] == "begin"
            assert commands[-1] == ("end",)
            assert sum(len(c[1]) for c in commands if c[0] == "audio") == 32000
            assert client.post("/speak", content=wav).status_code == 409


def test_interrupt_rejects_old_audio_and_notifies_display():
    runtime = FakeRuntime(Settings())
    with TestClient(create_app(runtime)) as client:
        with client.websocket_connect("/events") as ws:
            ws.receive_json()
            turn = client.post("/turns").json()["turn"]
            assert client.post(f"/turns/{turn}/audio", content=b"\0").status_code == 409
            assert client.post(f"/turns/{turn}/audio", content=bytes(32002)).status_code == 413
            assert client.post("/interrupt").status_code == 200
            assert ws.receive_json()["type"] == "interrupted"
            assert client.post(f"/turns/{turn}/audio", content=bytes(640)).status_code == 409


def test_invalid_wav_does_not_start_turn():
    runtime = FakeRuntime(Settings())
    with TestClient(create_app(runtime)) as client:
        assert client.post("/speak", content=b"invalid").status_code == 422
        assert runtime.turn is None
