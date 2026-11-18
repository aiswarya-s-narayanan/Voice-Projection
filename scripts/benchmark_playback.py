"""Compare complete/adaptive scheduling on live GPU output without speaker audio."""
import argparse
import base64
from dataclasses import replace
import json
import multiprocessing as mp
from pathlib import Path
import queue
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from avatar_kiosk.audio import wav_to_pcm
from avatar_kiosk.config import Settings, prepare_gpu_environment
from avatar_kiosk.playback import Playback
from avatar_kiosk.worker import run_worker


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('audio', type=Path)
    parser.add_argument('--stride', type=int, choices=range(1, 6), default=5)
    parser.add_argument('--output', type=Path, default=Path('outputs/adaptive-playback-check.json'))
    args = parser.parse_args()
    pcm = wav_to_pcm(args.audio.read_bytes())
    prepare_gpu_environment()
    ctx = mp.get_context('spawn')
    commands, events = ctx.Queue(512), ctx.Queue(50)
    worker = ctx.Process(target=run_worker, args=(replace(Settings.from_env(), render_stride=args.stride), commands, events), daemon=True)
    players = {mode: Playback(mode) for mode in ('complete', 'adaptive')}
    results = {mode: {'first_audio_seconds': None, 'underruns': 0} for mode in players}
    audio = {mode: bytearray() for mode in players}
    worker.start()
    try:
        event = events.get(timeout=180)
        if event['type'] != 'ready':
            raise RuntimeError(event)
        started = time.monotonic()
        for p in players.values():
            p.reset('benchmark')
        commands.put(('begin', 'benchmark', 'neutral'))
        for start in range(0, len(pcm), 6400):
            commands.put(('audio', pcm[start:start+6400]))
        commands.put(('end',))
        first_frame = completed = None
        callback = started
        deadline = started + 300
        while time.monotonic() < deadline:
            try:
                event = events.get_nowait()
            except queue.Empty:
                event = None
            if event:
                if event['type'] == 'error':
                    raise RuntimeError(event['message'])
                if event['type'] == 'frame':
                    first_frame = first_frame or time.monotonic()-started
                    for p in players.values():
                        p.add('benchmark', base64.b64decode(event['pcm']), base64.b64decode(event['jpeg']))
                elif event['type'] == 'done':
                    completed = time.monotonic()-started
                    for p in players.values():
                        p.finish('benchmark')
            now = time.monotonic()
            while callback <= now:
                for mode, p in players.items():
                    before = len(p.pending)
                    packet = p.next(callback)
                    if len(p.pending) < before:
                        if results[mode]['first_audio_seconds'] is None:
                            results[mode]['first_audio_seconds'] = callback-started
                        audio[mode].extend(packet)
                    p.image_at(callback)
                callback += .04
            if completed is not None and all(p.turn is None for p in players.values()):
                break
            time.sleep(.001)
        else:
            raise RuntimeError('Playback benchmark timed out')
        for mode, p in players.items():
            results[mode]['underruns'] = p.underruns
            results[mode]['audio_preserved'] = bytes(audio[mode][:len(pcm)]) == pcm and not any(audio[mode][len(pcm):])
            results[mode]['started_before_render_done'] = results[mode]['first_audio_seconds'] < completed
            if not results[mode]['audio_preserved']:
                raise RuntimeError('PCM mismatch: ' + mode)
        report = {'stride': args.stride, 'audio_seconds': len(pcm)/32000,
                  'first_frame_seconds': first_frame, 'render_done_seconds': completed,
                  'playback': results,
                  'note': 'Live GPU events with simulated DAC callbacks; no speaker or network test. Concurrent GPU load affects results.'}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2))
    finally:
        worker.terminate()
        worker.join(timeout=3)
        if worker.is_alive():
            worker.kill()
            worker.join()
        for q in (commands, events):
            q.cancel_join_thread()
            q.close()


if __name__ == '__main__':
    main()
