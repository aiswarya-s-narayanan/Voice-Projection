"""Small standard-library client usable from the separate voice-agent project."""
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode


class KioskAvatar:
    def __init__(self, url="http://127.0.0.1:8765", timeout=15):
        self.url, self.timeout = url.rstrip("/"), timeout

    def _post(self, path, body=b"", content_type="application/octet-stream"):
        request = Request(self.url + path, body, {"Content-Type": content_type}, method="POST")
        with urlopen(request, timeout=self.timeout) as response:
            return json.load(response)

    def speak_text(self, text, *, emotion="auto"):
        """Use the service's persistent Piper and sentence rendering pipeline."""
        result = self._post('/speak-text', json.dumps({'text': text, 'emotion': emotion}).encode(),
                            'application/json')
        return result.get('turn')  # None when Stop cancelled preparation.

    def speak_wav(self, path, *, emotion="auto", text="", timeline=None):
        """Replaces direct speaker playback of the generated Piper WAV."""
        params = {"emotion": emotion, "text": text}
        if timeline is not None:
            params["timeline"] = json.dumps(timeline)
        return self._post("/speak?" + urlencode(params),
                          Path(path).read_bytes(), "audio/wav")["turn"]

    def begin(self, *, emotion="auto", text="", timeline=None):
        params = {"emotion": emotion, "text": text}
        if timeline is not None:
            params["timeline"] = json.dumps(timeline)
        return self._post("/turns?" + urlencode(params))["turn"]

    def feed_pcm16(self, turn, pcm):
        """16 kHz mono little-endian signed PCM16; max 1 second per request."""
        return self._post(f"/turns/{turn}/audio", pcm)

    def end(self, turn):
        return self._post(f"/turns/{turn}/end")

    def interrupt(self):
        return self._post("/interrupt")

    def status(self):
        with urlopen(self.url + "/health", timeout=self.timeout) as response:
            return json.load(response)
