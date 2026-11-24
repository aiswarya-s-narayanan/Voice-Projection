"""Local sidecar for the existing Chef application; launch with one uvicorn worker."""
import asyncio
from contextlib import asynccontextmanager, suppress
import queue
import json
import threading
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .demo_tts import synthesize_sentence_pcm, prepare_voice, close_voice
import logging
from .expression_timeline import validate_timeline, split_sentences

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
    warm_voice = runtime is None
    runtime = runtime or Runtime(Settings.from_env())

    synthesis_cancel = None

    @asynccontextmanager
    async def lifespan(app):
        runtime.start()
        pump = asyncio.create_task(runtime.pump())
        warm_cancel = threading.Event()
        async def warmup():
            try:
                await asyncio.to_thread(prepare_voice, warm_cancel)
            except RuntimeError as exc:
                # Optional TTS must not prevent external WAV/PCM operation.
                logging.getLogger(__name__).warning("Voice warmup failed: %s", exc)
        warming = asyncio.create_task(warmup()) if warm_voice else None
        yield
        warm_cancel.set()
        if synthesis_cancel is not None:
            synthesis_cancel.set()
        pump.cancel()
        with suppress(asyncio.CancelledError):
            await pump
        runtime.stop()
        if warming:
            await warming
            await asyncio.to_thread(close_voice)

    app = FastAPI(title="Chef Ditto Avatar", lifespan=lifespan)

    web = Path(__file__).with_name('web')
    app.mount('/web', StaticFiles(directory=web), name='web')

    @app.get('/')
    async def browser():
        return FileResponse(web / 'index.html')

    @app.get('/portrait')
    async def portrait():
        return FileResponse(runtime.settings.image)

    def available():
        if synthesis_cancel is not None:
            raise HTTPException(409, 'Voice is being created; wait or press Stop')

    def announce(event):
        # Send a small message to the connected browser; skip it if the queue is full.
        for listener in list(runtime.listeners):
            try:
                listener.put_nowait(event)
            except asyncio.QueueFull:
                pass

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
        available()
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
        available()
        selected = expression(emotion, text)
        cues = timeline_value(timeline)
        raw = await read_limited(request, MAX_SECONDS * 96000 * 4 + 65536)
        try:
            pcm = await asyncio.to_thread(wav_to_pcm, raw)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if cues and cues[-1]["start"] >= len(pcm) / (RATE * 2):
            raise HTTPException(422, "Expression cue starts beyond the audio")
        available()
        turn = call(runtime.begin, selected, cues)
        announce({'type': 'audio_length', 'turn': turn, 'frames': -(-len(pcm) // 1280)})
        try:
            for start in range(0, len(pcm), 6400):
                call(runtime.feed, turn, pcm[start:start + 6400])
            call(runtime.end, turn)
        except Exception:
            runtime.interrupt()
            raise
        return {"turn": turn}

    @app.post('/speak-text')
    async def speak_text(request: Request):
        nonlocal synthesis_cancel
        try:
            body = json.loads(await read_limited(request, 8192))
            text = body.get('text', '')
            emotion = body.get('emotion', 'auto')
            if not isinstance(text, str) or not text.strip() or len(text) > 800:
                raise ValueError('Enter between 1 and 800 characters')
            if not isinstance(emotion, str):
                raise ValueError('Invalid emotion')
        except (ValueError, AttributeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        expression(emotion, text)  # Validate overrides before starting anything.
        sentences = split_sentences(text)
        if not 1 <= len(sentences) <= 100:
            raise HTTPException(422, 'Use between 1 and 100 sentences')
        available()
        if runtime.state != 'ready' or runtime.turn or not runtime.listeners:
            raise HTTPException(409, 'Connect the browser display and wait until Ready')
        cancellation = threading.Event()
        synthesis_cancel = cancellation
        turn = None
        ended = False
        total_bytes = 0
        try:
            for sentence in sentences:
                # CPU voice work releases the event loop; the separate GPU process
                # consumes already-enqueued sentences while this one synthesizes.
                pcm = await asyncio.to_thread(synthesize_sentence_pcm, sentence, cancellation)
                if cancellation.is_set() or pcm is None:
                    return {'cancelled': True}
                total_bytes += len(pcm)
                label = resolve_emotion(emotion, sentence)
                if turn is None:
                    turn = call(runtime.begin, label, [{'start': 0, 'emotion': label}])
                call(runtime.feed_sentence, turn, pcm, label)
                # Give outgoing frames and Stop/disconnect events a chance to run.
                await asyncio.sleep(0)
            if cancellation.is_set():
                return {'cancelled': True}
            announce({'type': 'audio_length', 'turn': turn, 'frames': -(-total_bytes // 1280)})
            call(runtime.end, turn)
            ended = True
            return {'turn': turn}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        finally:
            cancellation.set()
            if not ended and turn is not None and runtime.turn == turn:
                runtime.interrupt()
            synthesis_cancel = None

    @app.post("/interrupt")
    async def interrupt():
        if synthesis_cancel is not None:
            synthesis_cancel.set()
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
            if synthesis_cancel is not None:
                synthesis_cancel.set()
            runtime.listeners.discard(listener)
            if runtime.turn:
                runtime.interrupt()

    return app


app = create_app()
