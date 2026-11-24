import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from avatar_kiosk.persistent_voice import PersistentVoice


@pytest.fixture
def worker(tmp_path):
    script = tmp_path / 'voice.py'
    script.write_text('''import sys,json,base64,time,os
print(json.dumps({'ready':True}),flush=True)
for line in sys.stdin:
 text=json.loads(line)['text']
 if text=='crash': sys.exit(2)
 if text=='wait': time.sleep(5)
 print(json.dumps({'wav':base64.b64encode((str(os.getpid())+':'+text).encode()).decode()}),flush=True)
''')
    voice = PersistentVoice([sys.executable, '-u', str(script)], timeout=1)
    yield voice
    voice.close()


def test_reuses_model_process_across_sentences_and_replies(worker):
    cancel = threading.Event()
    assert worker.run(None, cancel) == b''
    pid = worker.process.pid
    assert worker.run('one', cancel) == f'{pid}:one'.encode()
    assert worker.run('two', cancel) == f'{pid}:two'.encode()
    assert worker.process.pid == pid


def test_cancel_stops_active_worker_and_next_reply_is_fresh(worker):
    cancellation = threading.Event()
    worker.run(None, cancellation)
    old = worker.process.pid
    with ThreadPoolExecutor() as pool:
        pending = pool.submit(worker.run, 'wait', cancellation)
        # Acquire-free detection: wait until the request owns the worker lock.
        for _ in range(100):
            if worker.lock.locked(): break
            threading.Event().wait(.01)
        cancellation.set()
        assert pending.result(timeout=3) is None
    assert worker.process is None
    result = worker.run('new', threading.Event())
    assert result.endswith(b':new') and worker.process.pid != old


def test_timeout_and_crash_release_worker_and_allow_retry(worker):
    for text in ('wait', 'crash'):
        with pytest.raises(RuntimeError):
            worker.run(text, threading.Event())
        assert worker.process is None
        assert worker.run('retry', threading.Event()).endswith(b':retry')


def test_serialized_callers_do_not_receive_each_others_audio(worker):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda text: worker.run(text, threading.Event()), ['a','b','c','d']))
    assert [value.split(b':')[1] for value in results] == [b'a',b'b',b'c',b'd']
    assert len({value.split(b':')[0] for value in results}) == 1


def test_pre_cancelled_request_does_not_start_worker(worker):
    cancelled = threading.Event()
    cancelled.set()
    assert worker.run('ignored', cancelled) is None
    assert worker.process is None
