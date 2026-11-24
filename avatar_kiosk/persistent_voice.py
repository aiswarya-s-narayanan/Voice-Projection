"""One reusable Piper subprocess per application, isolated from Ditto's runtime."""
import atexit
import base64
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time

from .config import ROOT


class PersistentVoice:
    def __init__(self, command=None, timeout=60):
        self.command = command  # Optional protocol-compatible worker for tests.
        self.timeout = timeout
        self.lock = threading.Lock()
        self.process = None
        self.errors = None
        self.responses = None
        self.reader = None
        self.key = None

    def _command(self):
        if self.command is not None:
            return self.command
        python = Path(os.environ.get('PIPER_PYTHON', ROOT / '.venv-piper/bin/python'))
        model = Path(os.environ.get('PIPER_MODEL', ROOT / 'models/piper/en_US-lessac-medium.onnx'))
        if not python.exists() or not model.exists():
            raise RuntimeError('Demo voice is not installed. See the Text-to-speech demo section in README.md.')
        return [str(python), '-u', str(Path(__file__).with_name('piper_worker.py')), str(model)]

    def _stop(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            if self.reader:
                self.reader.join(timeout=2)
            self.process.stdin.close()
            self.process.stdout.close()
        if self.errors:
            self.errors.close()
        self.process = self.errors = self.reader = self.responses = self.key = None

    def close(self):
        with self.lock:
            self._stop()

    def _receive(self, cancel):
        deadline = time.monotonic() + self.timeout
        while not cancel.is_set():
            try:
                line = self.responses.get(timeout=.05)
            except queue.Empty:
                if time.monotonic() > deadline:
                    raise RuntimeError('Piper voice timed out. Try a shorter sentence.')
                continue
            if line is None:
                self.errors.seek(0)
                detail = self.errors.read().decode('utf-8', errors='replace')[-1500:]
                raise RuntimeError('Piper worker exited unexpectedly: ' + detail)
            try:
                message = json.loads(line)
            except ValueError as exc:
                raise RuntimeError('Invalid response from Piper worker') from exc
            if 'error' in message:
                raise RuntimeError('Piper could not create speech: ' + message['error'])
            return message
        return None

    def _start(self, cancel):
        command = self._command()
        if self.process and self.process.poll() is None and self.key == command:
            return True
        self._stop()
        self.errors = tempfile.TemporaryFile(mode='w+b')
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.errors, text=True, bufsize=1)
        self.key = list(command)
        responses = self.responses = queue.Queue()
        output = self.process.stdout

        def read():
            try:
                for line in output:
                    responses.put(line)
            finally:
                responses.put(None)

        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()
        message = self._receive(cancel)
        if message is None:
            return False
        if message.get('ready') is not True:
            raise RuntimeError('Piper worker did not become ready')
        return True

    def run(self, text, cancel):
        """Return WAV bytes; text=None loads the model only. None means cancelled.

        A cancelled active request kills that worker so it cannot return stale
        audio or write into a deleted temporary directory. The next call restarts
        it. Ordinary sentences and replies keep the same loaded worker.
        """
        while not cancel.is_set():
            if self.lock.acquire(timeout=.05):
                break
        else:
            return None
        try:
            if cancel.is_set():
                return None
            if not self._start(cancel):
                self._stop()
                return None
            if text is None:
                return b''
            self.process.stdin.write(json.dumps({'text': text}) + '\n')
            self.process.stdin.flush()
            response = self._receive(cancel)
            if response is None or cancel.is_set():
                self._stop()
                return None
            try:
                return base64.b64decode(response['wav'], validate=True)
            except (KeyError, ValueError) as exc:
                raise RuntimeError('Invalid audio from Piper worker') from exc
        except Exception as exc:
            self._stop()
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError('Piper voice failed: ' + str(exc)) from exc
        finally:
            self.lock.release()


voice = PersistentVoice()
atexit.register(voice.close)
