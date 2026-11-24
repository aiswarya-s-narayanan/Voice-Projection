"""Private JSON-lines worker, executed only by the isolated Piper interpreter."""
import base64
import io
import json
import sys
import wave
from pathlib import Path


def main():
    # Reserve stdout for the protocol, including during third-party imports.
    protocol = sys.stdout
    sys.stdout = sys.stderr
    from piper import PiperVoice, SynthesisConfig

    model = Path(sys.argv[1])
    voice = PiperVoice.load(model)

    def send(message):
        protocol.write(json.dumps(message) + '\n')
        protocol.flush()

    send({'ready': True})
    for line in sys.stdin:
        try:
            request = json.loads(line)
            # Lightweight config refresh preserves live voice-speed edits while
            # keeping the expensive ONNX model/session resident.
            config = json.loads(Path(str(model) + '.json').read_text())['inference']
            settings = SynthesisConfig(length_scale=config.get('length_scale', 1.0),
                                       noise_scale=config.get('noise_scale', .667),
                                       noise_w_scale=config.get('noise_w', .8))
            output = io.BytesIO()
            with wave.open(output, 'wb') as wav:
                voice.synthesize_wav(request['text'], wav, syn_config=settings)
            send({'wav': base64.b64encode(output.getvalue()).decode('ascii')})
        except Exception as exc:
            send({'error': str(exc)})


if __name__ == '__main__':
    main()
