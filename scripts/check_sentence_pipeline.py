"""Verify sentence pipelining against the actual GPU worker, without a display.

Close the running avatar service first to avoid a second GPU model instance.
"""
import base64
import json
import multiprocessing as mp
from pathlib import Path
import queue
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from avatar_kiosk.config import Settings, prepare_gpu_environment
from avatar_kiosk.demo_tts import prepare_voice, close_voice, synthesize_sentence_pcm
from avatar_kiosk.expression_timeline import split_sentences, cue_at
from avatar_kiosk.expressions import resolve_emotion
from avatar_kiosk.worker import run_worker


def main():
    text = 'Hello! I am here to help. What would you like to order?'
    prepare_gpu_environment()
    context = mp.get_context('spawn')
    commands, events = context.Queue(512), context.Queue(50)
    cancel = context.Event()
    process = context.Process(target=run_worker, args=(Settings.from_env(), commands, events, cancel), daemon=True)
    voice_cancel = threading.Event()
    producer = None
    results = []
    process.start()
    try:
        prepare_voice(voice_cancel)
        ready = events.get(timeout=180)
        if ready['type'] != 'ready':
            raise RuntimeError(ready)
        for mode in ('sequential', 'pipelined'):
            start = time.perf_counter()
            pieces, cues, failures, feed_times, synthesis_times = [], [], [], [], []
            def produce():
                try:
                    for sentence in split_sentences(text):
                        began = time.perf_counter() - start
                        pcm = synthesize_sentence_pcm(sentence, voice_cancel)
                        if pcm is None:
                            return
                        synthesis_times.append([began, time.perf_counter() - start])
                        cues.append({'start': sum(map(len, pieces)) / 32000,
                                     'emotion': resolve_emotion('auto', sentence)})
                        pieces.append(pcm)
                        if mode == 'pipelined':
                            if len(pieces) == 1:
                                commands.put(('begin', mode, cues[0]['emotion'], [cues[0]]))
                            commands.put(('sentence', pcm, cues[-1]['emotion']))
                            feed_times.append(time.perf_counter() - start)
                    if mode == 'sequential':
                        commands.put(('begin', mode, cues[0]['emotion'], list(cues)))
                        for pcm in pieces:
                            commands.put(('audio', pcm))
                            feed_times.append(time.perf_counter() - start)
                    commands.put(('end',))
                except BaseException as exc:
                    failures.append(str(exc))
            producer = threading.Thread(target=produce)
            producer.start()
            returned = bytearray()
            labels = []
            first_frame = None
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if failures:
                    raise RuntimeError(failures)
                try:
                    event = events.get(timeout=.2)
                except queue.Empty:
                    continue
                if event['type'] == 'error':
                    raise RuntimeError(event['message'])
                if event['type'] == 'done':
                    break
                if event['type'] == 'frame':
                    if first_frame is None:
                        first_frame = time.perf_counter() - start
                    returned.extend(base64.b64decode(event['pcm']))
                    labels.append((event['index'], event['emotion']))
            else:
                raise RuntimeError('GPU pipeline timed out')
            producer.join(timeout=5)
            expected = b''.join(pieces)
            assert bytes(returned[:len(expected)]) == expected
            assert not any(returned[len(expected):])
            assert all(label == cue_at(cues, index / 25)['emotion'] for index, label in labels)
            if mode == 'pipelined':
                assert feed_times[0] <= synthesis_times[1][0]
            results.append({'mode': mode, 'first_audio_queued_seconds': feed_times[0],
                            'voice_finished_seconds': synthesis_times[-1][1],
                            'first_frame_seconds': first_frame,
                            'complete_seconds': time.perf_counter() - start,
                            'audio_seconds': len(expected)/32000, 'frames':len(labels),
                            'audio_preserved':True, 'expression_timing_verified':True})
        print(json.dumps({'text':text,'runs':results,
                          'note':'Single runs with stochastic voice durations; not a controlled latency benchmark.'}, indent=2))
    finally:
        voice_cancel.set()
        cancel.set()
        if producer:
            producer.join(timeout=3)
        close_voice()
        process.terminate()
        process.join(timeout=3)
        if process.is_alive():
            process.kill()
            process.join()
        for q in (commands,events):
            q.cancel_join_thread()
            q.close()


if __name__ == '__main__':
    main()
