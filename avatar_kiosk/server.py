"""Local sidecar for the existing Chef application; launch with one uvicorn worker."""
import asyncio
from contextlib import asynccontextmanager, suppress
import queue
import json
from .expression_timeline import validate_timeline

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect

from .audio import MAX_SECONDS, RATE, wav_to_pcm
from .config import Settings
from .runtime import Runtime
from .expressions import resolve_emotion


async def read_limited(request, limit):
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > limit:
            raise HTTPException(413, "Audio payload too large")
        data.extend(chunk)
    return bytes(data)


def create_app(runtime=None):
    runtime = runtime or Runtime(Settings.from_env())

    @asynccontextmanager
    async def lifespan(app):
        runtime.start()
        pump = asyncio.create_task(runtime.pump())
        yield
        pump.cancel()
        with suppress(asyncio.CancelledError):
            await pump
        runtime.stop()

    app = FastAPI(title="Chef Ditto Avatar", lifespan=lifespan)

    def call(fn, *args):
        try:
            return fn(*args)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except queue.Full as exc:
            raise HTTPException(429, "Audio queue full; retry this chunk") from exc

    @app.get("/health")
    async def health():
        return runtime.status()

    def expression(emotion, text):
        if len(text) > 800:
            raise HTTPException(422, "Expression text must be at most 800 characters")
        try:
            return resolve_emotion(emotion, text)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    def timeline_value(raw):
        if raw is None:
            return None
        try:
            if len(raw) > 12000:
                raise ValueError('Expression timeline is too large')
            return validate_timeline(json.loads(raw))
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/turns")
    async def begin(emotion: str = "auto", text: str = "", timeline: str | None = None):
        return {"turn": call(runtime.begin, expression(emotion, text), timeline_value(timeline)), "sample_rate": RATE, "format": "s16le", "channels": 1}

    @app.post("/turns/{turn}/audio")
    async def audio(turn: str, request: Request):
        call(runtime.feed, turn, await read_limited(request, RATE * 2))
        return {"accepted": True}

    @app.post("/turns/{turn}/end")
    async def end(turn: str):
        call(runtime.end, turn)
        return {"accepted": True}

    @app.post("/speak")
    async def speak(request: Request, emotion: str = "auto", text: str = "", timeline: str | None = None):
        selected = expression(emotion, text)
        cues = timeline_value(timeline)
        raw = await read_limited(request, MAX_SECONDS * 96000 * 4 + 65536)
        try:
            pcm = await asyncio.to_thread(wav_to_pcm, raw)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if cues and cues[-1]["start"] >= len(pcm) / (RATE * 2):
            raise HTTPException(422, "Expression cue starts beyond the audio")
        turn = call(runtime.begin, selected, cues)
        try:
            for start in range(0, len(pcm), 6400):
                call(runtime.feed, turn, pcm[start:start + 6400])
            call(runtime.end, turn)
        except Exception:
            runtime.interrupt()
            raise
        return {"turn": turn}

    @app.post("/interrupt")
    async def interrupt():
        runtime.interrupt()
        return {"state": runtime.state}

    @app.websocket("/events")
    async def events(socket: WebSocket):
        await socket.accept()
        if runtime.listeners:
            await socket.send_json({"type": "error", "message": "One display per kiosk is supported"})
            await socket.close(code=1008)
            return
        listener = asyncio.Queue(100)
        runtime.listeners.add(listener)

        async def send():
            await socket.send_json({"type": "status", **runtime.status()})
            while True:
                event = await listener.get()
                await socket.send_json(event)
                if event["type"] == "error":
                    await socket.close(code=1011)
                    return

        async def receive():
            # Detect a closed display even while there are no outgoing frames.
            while True:
                message = await socket.receive_json()
                if isinstance(message, dict) and message.get("type") == "played":
                    runtime.played(message.get("turn"))

        tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                    await task
            runtime.listeners.discard(listener)
            if runtime.turn:
                runtime.interrupt()

    return app


app = create_app()
