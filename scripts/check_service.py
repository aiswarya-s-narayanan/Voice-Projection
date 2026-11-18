"""Real GPU service acceptance check without opening a window or playing audio."""
import base64
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from avatar_kiosk.client import KioskAvatar
from avatar_kiosk.audio import wav_to_pcm
from websockets.sync.client import connect


def main():
    client = KioskAvatar()
    deadline = time.monotonic() + 120
    while client.status()["state"] != "ready":
        if client.status()["state"] == "error" or time.monotonic() > deadline:
            raise RuntimeError(client.status())
        time.sleep(0.2)
    pcm = wav_to_pcm(Path("vendor/ditto/example/audio.wav").read_bytes())
    results = []
    with connect("ws://127.0.0.1:8765/events", max_size=4 * 1024 * 1024) as ws:
        ws.recv()
        for seconds in (1, 4):
            started = time.monotonic()
            turn = client.begin()
            audio = pcm[:seconds * 32000]
            for offset in range(0, len(audio), 6400):
                client.feed_pcm16(turn, audio[offset:offset + 6400])
            client.end(turn)
            first = None
            count = 0
            returned_audio = bytearray()
            while True:
                event = json.loads(ws.recv(timeout=60))
                if event["type"] == "error":
                    raise RuntimeError(event)
                if event["type"] == "frame":
                    assert event["turn"] == turn and event["index"] == count
                    assert event["pts_ms"] == count * 40
                    assert base64.b64decode(event["jpeg"]).startswith(b"\xff\xd8")
                    returned_audio.extend(base64.b64decode(event["pcm"]))
                    first = first or time.monotonic()
                    count += 1
                if event["type"] == "done":
                    break
            assert count == seconds * 25
            assert returned_audio == audio, "Speech samples changed or were truncated"
            assert client.status()["state"] == "playing"
            ws.send(json.dumps({"type": "played", "turn": turn}))
            assert json.loads(ws.recv(timeout=10))["type"] == "ready"
            results.append({"seconds": seconds, "frames": count,
                            "first_frame_seconds": first - started,
                            "total_seconds": time.monotonic() - started})

        turn = client.begin()
        client.feed_pcm16(turn, pcm[:32000])
        started = time.monotonic()
        client.interrupt()
        interrupted = False
        while True:
            event = json.loads(ws.recv(timeout=30))
            if event["type"] == "interrupted":
                interrupted = True
            if interrupted:
                assert event["type"] != "frame", "Stale speech after interruption"
            if event["type"] == "ready":
                break
            if event["type"] == "error":
                raise RuntimeError(event)
        assert interrupted
        results.append({"interruption_to_ready_seconds": time.monotonic() - started})
    Path("outputs/service-check.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
