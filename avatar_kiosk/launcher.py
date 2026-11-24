"""Start the local avatar service and native display together."""
from pathlib import Path
import subprocess
import sys
import time
import webbrowser
from urllib.request import urlopen

from .config import ROOT


def main():
    try:
        with urlopen("http://127.0.0.1:8765/health", timeout=1):
            raise SystemExit("Port 8765 already has a service. Close the existing avatar before starting another.")
    except OSError:
        pass
    output = ROOT / "outputs"
    output.mkdir(exist_ok=True)
    service = display = None
    with (output / "server.log").open("a") as log:
        try:
            service = subprocess.Popen([sys.executable, "-m", "uvicorn", "avatar_kiosk.server:app",
                                        "--host", "127.0.0.1", "--port", "8765", "--workers", "1"],
                                       cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            for _ in range(100):
                if service.poll() is not None:
                    raise RuntimeError("Service failed; see outputs/server.log")
                try:
                    with urlopen("http://127.0.0.1:8765/health", timeout=1):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Service did not start; see outputs/server.log")
            if '--browser' in sys.argv[1:]:
                url = 'http://127.0.0.1:8765/'
                print(f'Avatar browser: {url}', flush=True)
                webbrowser.open(url)
                print('Keep this terminal open. Press Ctrl+C to stop the service.', flush=True)
                try:
                    service.wait()
                except KeyboardInterrupt:
                    pass
                return
            display = subprocess.Popen([sys.executable, "-m", "avatar_kiosk.desktop", *sys.argv[1:]], cwd=ROOT)
            display.wait()
        finally:
            for process in (display, service):
                if process and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


if __name__ == "__main__":
    main()
