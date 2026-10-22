"""Run the local FastAPI + Vite workspace; stop both children with Ctrl+C."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
UI_URL = "http://127.0.0.1:5173"
API_URL = "http://127.0.0.1:8000/api/health"


def listening(port: int) -> bool:
    with socket.socket() as client:
        client.settimeout(0.3)
        return client.connect_ex(("127.0.0.1", port)) == 0


def healthy() -> bool:
    try:
        with urlopen(API_URL, timeout=2) as response:
            return json.load(response).get("service") == "cancercare-ai-ehr"
    except (URLError, OSError, ValueError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
    if not vite.is_file():
        print("Frontend dependencies are missing. Run npm ci in frontend/; see EHR_SETUP.md.")
        return 1
    if listening(8000) or listening(5173):
        if healthy() and listening(5173):
            print(f"CancerCare AI is already running at {UI_URL}")
            if not args.no_browser:
                webbrowser.open(UI_URL)
            return 0
        print("Port 8000 or 5173 is in use. Stop the conflicting local service before starting CancerCare AI.")
        return 1
    log_dir = ROOT / ".cache/ehr"
    log_dir.mkdir(parents=True, exist_ok=True)
    children: list[subprocess.Popen] = []
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    with ExitStack() as stack:
        try:
            commands = [
                ([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"], ROOT, "api.log"),
                (["node", str(vite), "--host", "127.0.0.1", "--port", "5173", "--strictPort"], ROOT / "frontend", "frontend.log"),
            ]
            for command, cwd, filename in commands:
                log = stack.enter_context((log_dir / filename).open("a", encoding="utf-8"))
                children.append(subprocess.Popen(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                                 creationflags=flags))
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if any(child.poll() is not None for child in children):
                    raise RuntimeError("A service exited during startup.")
                if healthy() and listening(5173):
                    break
                time.sleep(0.3)
            else:
                raise RuntimeError("The local services did not become ready within 45 seconds.")
            print(f"CancerCare AI: {UI_URL}\nAPI documentation: http://127.0.0.1:8000/docs\nPress Ctrl+C to stop both services.", flush=True)
            if not args.no_browser:
                webbrowser.open(UI_URL)
            while all(child.poll() is None for child in children):
                time.sleep(0.5)
            raise RuntimeError("A service exited. Restart the launcher after checking .cache/ehr/ logs.")
        except KeyboardInterrupt:
            print("Stopping CancerCare AI.")
            return 0
        except (OSError, RuntimeError) as error:
            print(f"{error} Check the local logs in {log_dir}.")
            return 1
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
            for child in children:
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
