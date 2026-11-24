import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from fastapi.testclient import TestClient

from avatar_kiosk.config import Settings
from avatar_kiosk.server import create_app
from test_audio import wav_bytes
from test_server import FakeRuntime


def test_browser_assets_and_portrait_are_served():
    runtime = FakeRuntime(Settings())
    with TestClient(create_app(runtime)) as client:
        assert 'Connect avatar' in client.get('/').text
        assert client.get('/web/app.js').status_code == 200
        assert client.get('/web/style.css').status_code == 200
        assert client.get('/portrait').headers['content-type'].startswith('image/')


def test_text_requires_display_and_rejects_bad_input():
    runtime = FakeRuntime(Settings())
    with TestClient(create_app(runtime)) as client:
        for body in ({'text': ''}, {'text': 'a'*801}, {'text': []}, [],
                     {'text': 'Hello', 'emotion': 'bad'}):
            assert client.post('/speak-text', json=body).status_code == 422
        assert client.post('/speak-text', json={'text': 'Hello!'}).status_code == 409
        assert runtime.commands.empty()


def test_browser_sends_first_sentence_before_synthesizing_second(monkeypatch):
    runtime = FakeRuntime(Settings())
    first_pcm, second_pcm = bytes(16000), bytes(32000)
    def synthesize(text, cancel):
        if text == 'Hello!':
            return first_pcm
        # This runs in the Piper thread: the first audio is already available to
        # the independent GPU process even though sentence two has not finished.
        commands = list(runtime.commands.queue)
        assert commands[0][0] == 'begin'
        assert commands[1] == ('sentence', first_pcm, 'happy')
        assert not runtime.ending
        return second_pcm
    monkeypatch.setattr('avatar_kiosk.server.synthesize_sentence_pcm', synthesize)
    with TestClient(create_app(runtime)) as client:
        with client.websocket_connect('/events') as ws:
            ws.receive_json()
            response = client.post('/speak-text', json={'text':'Hello! How are you?'})
            assert response.status_code == 200
            commands = list(runtime.commands.queue)
            assert commands[0][3] == [{'start': 0, 'emotion': 'happy'}]
            assert commands[2] == ('sentence', second_pcm, 'curious')
            assert commands[-1] == ('end',)
            assert runtime.samples == 24000


def test_stop_cancels_synthesis_and_prevents_late_playback(monkeypatch):
    entered = threading.Event()
    def synthesize(text, cancel):
        entered.set()
        assert cancel.wait(5)
        return None
    monkeypatch.setattr('avatar_kiosk.server.synthesize_sentence_pcm', synthesize)
    runtime = FakeRuntime(Settings())
    with TestClient(create_app(runtime)) as client:
        with client.websocket_connect('/events') as ws:
            ws.receive_json()
            with ThreadPoolExecutor() as pool:
                pending = pool.submit(client.post, '/speak-text', json={'text':'Hello!'})
                assert entered.wait(5)
                assert client.post('/speak-text', json={'text':'Again'}).status_code == 409
                assert client.post('/turns').status_code == 409
                assert client.post('/interrupt').status_code == 200
                assert pending.result(timeout=5).json() == {'cancelled': True}
            assert runtime.turn is None and runtime.commands.empty()


def test_production_lifespan_preloads_and_closes_voice(monkeypatch):
    from avatar_kiosk import server
    loaded = threading.Event()
    closed = threading.Event()
    monkeypatch.setattr(server, 'Runtime', FakeRuntime)
    monkeypatch.setattr(server, 'prepare_voice', lambda cancel: loaded.set())
    monkeypatch.setattr(server, 'close_voice', closed.set)
    with TestClient(server.create_app()) as client:
        assert loaded.wait(2)
        assert client.get('/health').status_code == 200
    assert closed.is_set()


def test_optional_voice_warmup_failure_keeps_audio_service_available(monkeypatch):
    from avatar_kiosk import server
    attempted = threading.Event()
    def fail(cancel):
        attempted.set()
        raise RuntimeError('missing voice')
    monkeypatch.setattr(server, 'Runtime', FakeRuntime)
    monkeypatch.setattr(server, 'prepare_voice', fail)
    monkeypatch.setattr(server, 'close_voice', lambda: None)
    with TestClient(server.create_app()) as client:
        assert attempted.wait(2)
        assert client.get('/health').json()['state'] == 'ready'


def test_stop_during_second_sentence_aborts_partial_render(monkeypatch):
    entered = threading.Event()
    def synthesize(text, cancel):
        if text == 'Hello!':
            return bytes(16000)
        entered.set()
        assert cancel.wait(5)
        return None
    monkeypatch.setattr('avatar_kiosk.server.synthesize_sentence_pcm', synthesize)
    runtime = FakeRuntime(Settings())
    with TestClient(create_app(runtime)) as client:
        with client.websocket_connect('/events') as ws:
            ws.receive_json()
            with ThreadPoolExecutor() as pool:
                pending = pool.submit(client.post, '/speak-text', json={'text':'Hello! Another sentence.'})
                assert entered.wait(5)
                old_turn = runtime.turn
                assert old_turn and runtime.samples == 8000
                assert client.get('/health').status_code == 200
                assert client.post('/interrupt').status_code == 200
                assert pending.result(timeout=5).json() == {'cancelled': True}
            assert runtime.turn is None and runtime.cancel.is_set()
            commands = list(runtime.commands.queue)
            assert len([c for c in commands if c[0] == 'sentence']) == 1
            assert commands[-1] == ('end',)
            assert ws.receive_json() == {'type':'interrupted','turn':old_turn}


def test_later_synthesis_failure_interrupts_partial_turn(monkeypatch):
    def synthesize(text, cancel):
        if text == 'Hello!':
            return bytes(16000)
        raise RuntimeError('Voice worker failed')
    monkeypatch.setattr('avatar_kiosk.server.synthesize_sentence_pcm', synthesize)
    runtime = FakeRuntime(Settings())
    with TestClient(create_app(runtime)) as client:
        with client.websocket_connect('/events') as ws:
            ws.receive_json()
            response = client.post('/speak-text', json={'text':'Hello! Next.'})
            assert response.status_code == 503
            assert runtime.turn is None and runtime.cancel.is_set()
            assert ws.receive_json()['type'] == 'interrupted'


def test_manual_expression_applies_to_each_pipelined_sentence(monkeypatch):
    monkeypatch.setattr('avatar_kiosk.server.synthesize_sentence_pcm', lambda *args: bytes(16000))
    runtime = FakeRuntime(Settings())
    with TestClient(create_app(runtime)) as client:
        with client.websocket_connect('/events') as ws:
            ws.receive_json()
            assert client.post('/speak-text', json={'text':'Hello! Sorry.', 'emotion':'thinking'}).status_code == 200
            sentences = [c for c in runtime.commands.queue if c[0] == 'sentence']
            assert [c[2] for c in sentences] == ['thinking', 'thinking']


def test_too_many_sentences_rejected_before_synthesis(monkeypatch):
    def unexpected(*args):
        raise AssertionError('Should validate first')
    monkeypatch.setattr('avatar_kiosk.server.synthesize_sentence_pcm', unexpected)
    runtime = FakeRuntime(Settings())
    with TestClient(create_app(runtime)) as client:
        assert client.post('/speak-text', json={'text':'Hi! '*101}).status_code == 422
        assert runtime.commands.empty()


def test_duration_limit_aborts_pipeline_before_queueing_oversize_sentence(monkeypatch):
    from avatar_kiosk.audio import RATE
    monkeypatch.setattr('avatar_kiosk.server.synthesize_sentence_pcm', lambda *args: bytes(RATE*2*46))
    runtime = FakeRuntime(Settings())
    with TestClient(create_app(runtime)) as client:
        with client.websocket_connect('/events') as ws:
            ws.receive_json()
            result = client.post('/speak-text', json={'text':'First sentence. Second sentence.'})
            assert result.status_code == 409
            assert len([c for c in runtime.commands.queue if c[0] == 'sentence']) == 1
            assert runtime.turn is None and runtime.cancel.is_set()
