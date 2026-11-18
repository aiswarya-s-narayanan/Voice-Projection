"""Read-only deployment diagnostics; nonzero exit means inference is not ready."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import json
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from avatar_kiosk.config import Settings

settings = Settings.from_env()
ok = True
print("Python:", sys.version.split()[0])
for label, path in (("Ditto source", settings.ditto), ("Avatar image", settings.image),
                    ("Model configuration", settings.config), ("Model weights", settings.data_root)):
    exists = Path(path).exists()
    print(f"{'OK' if exists else 'MISSING'} {label}: {path}")
    ok &= exists
for module in ("torch", "onnxruntime", "cv2", "mediapipe", "sounddevice", "tkinter"):
    found = importlib.util.find_spec(module) is not None
    print(f"{'OK' if found else 'MISSING'} Python module: {module}")
    ok &= found
try:
    result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
                            capture_output=True, text=True, timeout=10)
    print("GPU:", (result.stdout + result.stderr).strip())
    ok &= result.returncode == 0
except (OSError, subprocess.TimeoutExpired) as exc:
    print("GPU:", exc)
    ok = False
if importlib.util.find_spec("torch"):
    import torch
    print("CUDA usable:", torch.cuda.is_available())
    ok &= torch.cuda.is_available()
if "--service" in sys.argv:
    try:
        with urlopen("http://127.0.0.1:8765/health", timeout=5) as response:
            status = json.load(response)
        print("Live service:", json.dumps(status))
        ok &= status["state"] == "ready" and status["display_connected"]
    except OSError as exc:
        print("Live service:", exc)
        ok = False
print("READY FOR GPU SMOKE TEST" if ok else "NOT READY: resolve the missing items above")
sys.exit(0 if ok else 1)
