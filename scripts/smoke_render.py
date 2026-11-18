"""Run the actual streaming worker and save its output for GPU/visual verification."""
import argparse
import base64
import io
import json
import multiprocessing as mp
from pathlib import Path
import queue
import subprocess
import sys
import time
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from avatar_kiosk.audio import wav_to_pcm
from avatar_kiosk.config import Settings, prepare_gpu_environment
from avatar_kiosk.worker import run_worker
from avatar_kiosk.ambient_motion import AmbientMotion
from avatar_kiosk.expressions import EMOTIONS
from avatar_kiosk.expression_timeline import validate_timeline


def main():
    import imageio.v2 as imageio
    import imageio_ffmpeg
    import numpy as np
    from PIL import Image

    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--emotion", choices=EMOTIONS, default="neutral")
    parser.add_argument("--timeline", type=Path, help="JSON sentence cues with audio-relative starts")
    parser.add_argument("--output", default="outputs/avatar-preview.mp4")
    parser.add_argument("--seconds", type=float, default=4)
    parser.add_argument("--ambient", action="store_true", help="Include the desktop's natural body/head movement")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    pcm = wav_to_pcm(Path(args.audio).read_bytes())[:int(args.seconds * 16000) * 2]
    prepare_gpu_environment()
    ctx = mp.get_context("spawn")
    commands, events = ctx.Queue(512), ctx.Queue(50)
    worker = ctx.Process(target=run_worker, args=(Settings.from_env(), commands, events), daemon=True)
    worker.start()
    video = output.with_suffix(".silent.mp4")
    wav_path = output.with_suffix(".wav")
    first = None
    ambient = AmbientMotion()
    frames = 0
    returned_audio = bytearray()
    started = time.monotonic()
    try:
        event = events.get(timeout=180)
        if event["type"] != "ready":
            raise RuntimeError(event)
        loaded = time.monotonic()
        timeline = validate_timeline(json.loads(args.timeline.read_text())) if args.timeline else None
        commands.put(("begin", "smoke", args.emotion, timeline))
        for start in range(0, len(pcm), 6400):
            commands.put(("audio", pcm[start:start + 6400]))
        commands.put(("end",))
        with imageio.get_writer(str(video), fps=25, macro_block_size=2) as writer:
            while True:
                event = events.get(timeout=180)
                if event["type"] == "error":
                    raise RuntimeError(event["message"])
                if event["type"] == "done":
                    break
                if event["type"] != "frame":
                    continue
                returned_audio.extend(base64.b64decode(event["pcm"]))
                first = first or time.monotonic()
                image = Image.open(io.BytesIO(base64.b64decode(event["jpeg"]))).convert("RGB")
                if args.ambient:
                    image = ambient.apply(image, frames / 25, speaking=True, emotion=event.get("emotion", args.emotion))
                if frames == 0:
                    image.save(output.with_suffix(".jpg"))
                writer.append_data(np.asarray(image))
                frames += 1
        finished = time.monotonic()
        if bytes(returned_audio[:len(pcm)]) != pcm or any(returned_audio[len(pcm):]):
            raise RuntimeError("Rendered audio does not match input PCM")
        with wave.open(str(wav_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(pcm)
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
                        "-i", str(video), "-i", str(wav_path), "-c:v", "copy", "-c:a", "aac",
                        "-shortest", str(output)], check=True)
        metrics = {"frames": frames, "model_load_seconds": loaded - started,
                   "ambient_movement": args.ambient, "emotion": args.emotion, "timeline": timeline,
                   "animation_revision": "expressive-v2", "audio_preserved": True,
                   "first_frame_seconds": first - loaded,
                   "render_seconds": finished - loaded,
                   "effective_fps_including_setup": frames / (finished - loaded),
                   "audio_seconds": len(pcm) / 32000,
                   "note": "All input queued immediately; includes image setup and video encoding; not a microphone round-trip benchmark."}
        output.with_suffix(".json").write_text(json.dumps(metrics, indent=2))
        print(json.dumps(metrics, indent=2))
        print(output)
    finally:
        worker.terminate()
        worker.join(timeout=3)
        if worker.is_alive():
            worker.kill()
            worker.join()
        for q in (commands, events):
            q.cancel_join_thread()
            q.close()


if __name__ == "__main__":
    main()
