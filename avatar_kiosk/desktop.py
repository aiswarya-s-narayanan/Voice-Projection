"""Native kiosk display. It owns speaker playback so lips and audio share a clock."""
import argparse
import base64
import io
import json
import queue
import threading
import time
import tempfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk
import sounddevice as sd
from websockets.sync.client import connect

from .client import KioskAvatar
from .config import Settings, ROOT
from .playback import Playback
from .demo_tts import synthesize_sentences
from .ambient_motion import AmbientMotion
from .idle_blink import IdleBlink
from .expressions import EMOTIONS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--playback-mode", choices=("complete", "adaptive"), default="complete",
                        help="Adaptive may start early after measuring sustained rendering speed")
    args = parser.parse_args()
    playback = Playback(mode=args.playback_mode)
    messages = queue.Queue()
    done = threading.Event()
    client = KioskAvatar(args.url)
    root = tk.Tk()
    root.title("Chef · Expressive avatar v2")
    root.geometry("600x900")
    root.minsize(400, 500)
    root.configure(bg="white")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)
    root.attributes("-fullscreen", args.fullscreen)
    root.bind("<Escape>", lambda _: root.attributes("-fullscreen", False))
    status = tk.StringVar(value="Connecting to avatar…")
    tk.Label(root, text="Welcome!", font=("Sans", 24), bg="white").grid(row=0, column=0, pady=12)
    canvas = tk.Canvas(root, bg="white", highlightthickness=0, width=400, height=400)
    canvas.grid(row=1, column=0, sticky="nsew")
    image_item = canvas.create_image(0, 0, anchor="center")
    tk.Label(root, textvariable=status, bg="white", wraplength=550).grid(row=2, column=0, pady=10)
    original = Image.open(Settings.from_env().image).convert("RGB")
    current = original
    ambient_motion = AmbientMotion()
    idle_blink = IdleBlink()
    active_emotion = "neutral"
    selected_emotion = tk.StringVar(value="auto")
    blinking = tk.BooleanVar(value=True)
    full_character = tk.BooleanVar(value=False)
    animation_started = time.monotonic()
    natural_motion = tk.BooleanVar(value=True)
    last_speech_image = None
    release_started = None
    demo_busy = False
    demo_cancel = threading.Event()

    def show(image):
        nonlocal last_speech_image, release_started
        resized = image.copy()
        resized.thumbnail((1280, 1280))
        seconds = time.monotonic() - animation_started
        speaking = playback.turn is not None and playback.started
        if speaking:
            last_speech_image = resized.copy()
            release_started = None
        elif last_speech_image is not None:
            if release_started is None:
                release_started = seconds
            alpha = min(1, (seconds-release_started)/.35)
            resized = Image.blend(last_speech_image, resized.resize(last_speech_image.size), alpha)
            if alpha >= 1:
                last_speech_image = None
        if blinking.get():
            resized = idle_blink.apply(resized, seconds, idle=not speaking)
        if natural_motion.get():
            resized = ambient_motion.apply(resized, seconds, speaking=speaking,
                                           emotion=active_emotion)
        if not full_character.get():
            width, height = resized.size
            resized = resized.crop((int(.24*width), 0, int(.74*width), int(.35*height)))
        resized.thumbnail((max(200, canvas.winfo_width()), max(300, canvas.winfo_height())))
        photo = ImageTk.PhotoImage(resized)
        canvas.itemconfigure(image_item, image=photo)
        canvas.coords(image_item, canvas.winfo_width() // 2, canvas.winfo_height() // 2)
        canvas.image = photo

    def bring_forward():
        root.deiconify()
        root.lift()
        root.attributes("-topmost", True)
        root.after(1500, lambda: root.attributes("-topmost", False))

    def audio_callback(outdata, frames, clock, flags):
        outdata[:] = playback.next(clock.outputBufferDacTime)

    stream = sd.RawOutputStream(samplerate=16000, channels=1, dtype="int16",
                                blocksize=640, latency="high", callback=audio_callback)

    def receive():
        ws_url = args.url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        try:
            with connect(ws_url + "/events", max_size=4 * 1024 * 1024) as ws:
                awaiting_playback = None
                while not done.is_set():
                    if awaiting_playback and playback.turn is None:
                        ws.send(json.dumps({"type": "played", "turn": awaiting_playback}))
                        awaiting_playback = None
                    try:
                        message = json.loads(ws.recv(timeout=0.1))
                    except TimeoutError:
                        continue
                    kind = message["type"]
                    if kind == "started":
                        playback.reset(message["turn"])
                        messages.put(("expression", message.get("emotion", "neutral")))
                        messages.put("Preparing speech…")
                    elif kind == "frame":
                        image = base64.b64decode(message["jpeg"])
                        playback.add(message["turn"], base64.b64decode(message["pcm"]), image, message.get("emotion"))
                        if message["index"] == 0:
                            messages.put("Measuring render speed and buffering…" if args.playback_mode == "adaptive" and not playback.adaptive_failed else "Buffering reply for smooth playback…")
                    elif kind == "interrupted":
                        awaiting_playback = None
                        playback.reset()
                        messages.put("Listening")
                    elif kind == "ready":
                        messages.put("Ready · type a message and click Speak text")
                    elif kind == "status":
                        if message.get("animation_revision") != "expressive-v2":
                            raise RuntimeError("Old avatar service: close the service and restart ./start-avatar.sh to load expressive-v2.")
                        messages.put(message.get("error") or (
                            "Ready · type a message and click Speak text"
                            if message["state"] == "ready" else "Avatar: " + message["state"]))
                    elif kind == "done":
                        awaiting_playback = message["turn"]
                        playback.finish(message["turn"])
                    elif kind == "error":
                        raise RuntimeError(message["message"])
        except Exception as exc:
            playback.reset()
            messages.put("Avatar unavailable: " + str(exc))

    def stop_speech():
        demo_cancel.set()
        playback.reset()
        def request_stop():
            try:
                client.interrupt()
            except Exception as exc:
                messages.put(str(exc))
        threading.Thread(target=request_stop, daemon=True).start()

    def test_avatar():
        bring_forward()
        status.set("Sending test audio…")
        def send_test():
            try:
                client.speak_wav(ROOT / "outputs/avatar-final-preview.wav")
            except Exception as exc:
                messages.put("Test failed: " + str(exc))
        threading.Thread(target=send_test, daemon=True).start()

    controls = tk.Frame(root, bg="white")
    controls.grid(row=4, column=0, pady=8)
    editor = tk.Frame(root, bg="white")
    editor.grid(row=3, column=0, sticky="ew", padx=16)
    tk.Label(editor, text="Type what you want the avatar to say · English demo voice",
             bg="white", anchor="w").pack(fill="x")
    text_box = tk.Text(editor, height=3, wrap="word", font=("Sans", 12))
    text_box.pack(fill="x", pady=6)
    text_box.insert("1.0", "Hello! Welcome to our restaurant. What would you like to order today?")

    def speak_text(event=None):
        nonlocal demo_busy, demo_cancel
        if demo_busy:
            status.set("Creating speech. Use Stop speaking to cancel.")
            return "break"
        text = text_box.get("1.0", "end-1c").strip()
        if not text or len(text) > 800:
            status.set("Enter between 1 and 800 characters.")
            return "break"
        emotion = selected_emotion.get()
        demo_busy = True
        demo_cancel = threading.Event()
        cancellation = demo_cancel
        speak_button.configure(state="disabled")
        status.set("Creating voice from your text…")

        def send_text():
            try:
                if client.status()["state"] != "ready":
                    raise RuntimeError("Avatar is busy. Wait for it to finish, or press Stop speaking.")
                with tempfile.TemporaryDirectory(prefix="chef-voice-") as temp:
                    wav = Path(temp) / "speech.wav"
                    timeline = synthesize_sentences(text, wav, cancellation, emotion)
                    if timeline and not done.is_set():
                        if cancellation.is_set():
                            return
                        client.speak_wav(wav, emotion=emotion, text=text, timeline=timeline)
                        if cancellation.is_set():
                            client.interrupt()
            except Exception as exc:
                messages.put("Could not speak: " + str(exc))
            finally:
                messages.put(("demo_finished", cancellation.is_set()))

        threading.Thread(target=send_text, daemon=True).start()
        return "break"

    expression_controls = tk.Frame(editor, bg="white")
    expression_controls.pack(fill="x", pady=4)
    tk.Label(expression_controls, text="Emotion", bg="white").pack(side="left")
    ttk.Combobox(expression_controls, textvariable=selected_emotion,
                 values=("auto",) + EMOTIONS, state="readonly", width=12).pack(side="left", padx=8)
    tk.Checkbutton(expression_controls, text="Idle blinking", variable=blinking,
                   bg="white").pack(side="left", padx=8)

    speak_button = tk.Button(controls, text="Speak text", command=speak_text)
    speak_button.pack(side="left", padx=8)
    text_box.bind("<Control-Return>", speak_text)
    tk.Button(controls, text="Test avatar", command=test_avatar).pack(side="left", padx=8)
    tk.Button(controls, text="Stop speaking", command=stop_speech).pack(side="left", padx=8)
    display_controls = tk.Frame(root, bg="white")
    display_controls.grid(row=5, column=0, pady=(0, 8))
    tk.Checkbutton(display_controls, text="Natural movement", variable=natural_motion, bg="white").pack(side="left")
    tk.Checkbutton(display_controls, text="Full character", variable=full_character, bg="white").pack(side="left")

    def tick():
        nonlocal current, demo_busy, active_emotion
        while not messages.empty():
            message = messages.get_nowait()
            if isinstance(message, tuple) and message[0] == "expression":
                active_emotion = message[1]
                continue
            if isinstance(message, tuple) and message[0] == "demo_finished":
                demo_busy = False
                speak_button.configure(state="normal")
                if message[1]:
                    status.set("Stopped. Enter text to try again.")
                continue
            status.set("Speaking · " + active_emotion if message == "Speaking" else message)
            if message == "Preparing speech…":
                bring_forward()
        image = playback.image_at(stream.time)
        if image is not None:
            # Decode only the frame due at the speaker clock, outside the audio callback.
            if isinstance(image, tuple):
                image, active_emotion = image
            current = Image.open(io.BytesIO(image)).convert("RGB")
        if playback.turn is None:
            current = original
            active_emotion = "neutral"
        if playback.turn is not None and playback.rebuffering:
            status.set("Rendering slowed down · buffering the rest; early playback disabled")
        elif playback.turn is not None and playback.started:
            status.set("Speaking · " + active_emotion)
        show(current)
        root.after(40, tick)

    threading.Thread(target=receive, daemon=True).start()
    try:
        with stream:
            root.after(100, tick)
            root.after(200, bring_forward)
            root.mainloop()
    finally:
        done.set()
        demo_cancel.set()
        playback.reset()


if __name__ == "__main__":
    main()
