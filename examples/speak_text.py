"""Optional standalone demo: text -> local Piper -> running avatar."""
import argparse
from pathlib import Path
import threading

from avatar_kiosk.client import KioskAvatar
from avatar_kiosk.demo_tts import synthesize
from avatar_kiosk.expressions import EMOTIONS

parser = argparse.ArgumentParser()
parser.add_argument("text")
parser.add_argument("--emotion", choices=("auto",) + EMOTIONS, default="auto")
parser.add_argument("--wav-only", type=Path, help="Save generated speech without playing it")
args = parser.parse_args()
if args.wav_only:
    synthesize(args.text, args.wav_only, threading.Event())
    print(args.wav_only)
else:
    print(KioskAvatar().speak_text(args.text, emotion=args.emotion))
