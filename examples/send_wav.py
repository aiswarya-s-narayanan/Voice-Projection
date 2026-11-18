"""Send an existing Piper WAV to the running avatar sidecar and native display."""
import argparse
from avatar_kiosk.client import KioskAvatar

parser = argparse.ArgumentParser()
parser.add_argument("wav")
parser.add_argument("--url", default="http://127.0.0.1:8765")
args = parser.parse_args()
print(KioskAvatar(args.url).speak_wav(args.wav))
