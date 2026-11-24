"""Compare per-sentence Piper CLI startup with the persistent isolated worker."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from avatar_kiosk.config import ROOT
from avatar_kiosk.demo_tts import prepare_voice, close_voice, synthesize_sentences
from avatar_kiosk.expression_timeline import split_sentences
from avatar_kiosk.persistent_voice import voice


def main():
    text = 'Hello! I am here to help. What would you like to order?'
    python = os.environ.get('PIPER_PYTHON', str(ROOT / '.venv-piper/bin/python'))
    model = os.environ.get('PIPER_MODEL', str(ROOT / 'models/piper/en_US-lessac-medium.onnx'))
    with tempfile.TemporaryDirectory(prefix='voice-benchmark-') as temp:
        start = time.perf_counter()
        for i, sentence in enumerate(split_sentences(text)):
            subprocess.run([python, '-m', 'piper', '--model', model, '--output_file', f'{temp}/{i}.wav'],
                           input=sentence, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        old = time.perf_counter() - start
        try:
            start = time.perf_counter()
            prepare_voice(threading.Event())
            load = time.perf_counter() - start
            pid = voice.process.pid
            timings = []
            for i in range(3):
                output = Path(temp) / f'persistent-{i}.wav'
                start = time.perf_counter()
                cues = synthesize_sentences(text, output, threading.Event())
                timings.append(time.perf_counter() - start)
                assert voice.process.pid == pid
                with wave.open(str(output)) as wav:
                    duration = wav.getnframes() / wav.getframerate()
                assert len(cues) == 3 and 0 == cues[0]['start'] < cues[1]['start'] < cues[2]['start'] < duration
            result = {'text': text, 'old_per_sentence_process_seconds': old,
                      'persistent_model_load_seconds': load, 'persistent_reply_seconds': timings,
                      'same_worker_for_all_9_sentences': True,
                      'note': 'Voice preparation only; excludes Ditto rendering and playback buffering.'}
            print(json.dumps(result, indent=2))
        finally:
            close_voice()


if __name__ == '__main__':
    main()
