"""Windows developer launcher for the local textbook chat application."""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=None, help="Loopback port (default: .env or 8765)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the default browser")
    parser.add_argument("--skip-build", action="store_true", help="Require an existing frontend/dist build")
    return parser.parse_args()


def configured_port(explicit: int | None) -> int:
    port = explicit if explicit is not None else int(
        os.environ.get("TEXTBOOK_CHAT_PORT") or _env_value("TEXTBOOK_CHAT_PORT") or 8765
    )
    if not 1 <= port <= 65535:
        raise RuntimeError("Port must be between 1 and 65535.")
    return port


def _env_value(name: str) -> str | None:
    path = ROOT / ".env"
    if not path.is_file():
        return None
    for raw_line in path.read_text("utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip("\"'")
    return None


def require_free_port(port: int) -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", port))
    except OSError as exc:
        raise RuntimeError(
            f"127.0.0.1:{port} is already in use. Stop it or pass --port with a free port."
        ) from exc
    finally:
        probe.close()


def ensure_frontend(skip_build: bool) -> None:
    if (ROOT / "frontend" / "dist" / "index.html").is_file():
        return
    if skip_build:
        raise RuntimeError("frontend/dist is missing; run npm ci and npm run build first.")
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm is required for the first frontend build but was not found on PATH.")
    print("Building the local React interface…", flush=True)
    if not (ROOT / "frontend" / "node_modules").is_dir():
        subprocess.run([npm, "ci"], cwd=ROOT / "frontend", check=True)
    subprocess.run([npm, "run", "build"], cwd=ROOT / "frontend", check=True)


def can_import(python: Path, modules: str, environment: dict[str, str]) -> bool:
    result = subprocess.run(
        [str(python), "-c", f"import {modules}"],
        cwd=ROOT, env=environment, capture_output=True, text=True,
    )
    return result.returncode == 0


def select_backend_python(environment: dict[str, str]) -> Path:
    current = Path(sys.executable).resolve()
    if can_import(current, "sentence_transformers, torch", environment):
        return current
    bundled = ROOT / "temp" / "python-x64" / "python.exe"
    if bundled.is_file() and can_import(bundled, "sentence_transformers, torch", environment):
        return bundled
    raise RuntimeError(
        "No compatible Python runtime can import Sentence Transformers and Torch. "
        "Use a Windows x64 Python and install this project with .[app,online-generation]."
    )


def require_backend_dependencies(python: Path, environment: dict[str, str]) -> None:
    if not can_import(python, "fastapi, uvicorn, dotenv, multipart, huggingface_hub", environment):
        raise RuntimeError('Backend dependencies are missing. Run: python -m pip install -e ".[app]"')


def wait_until_ready(process: subprocess.Popen[bytes], url: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"The local server exited during startup with code {process.returncode}.")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.15)
    raise RuntimeError("The local server did not become healthy within 60 seconds.")


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def main() -> int:
    if os.name != "nt":
        raise RuntimeError("The first application release supports Windows only.")
    args = parse_args()
    port = configured_port(args.port)
    require_free_port(port)
    ensure_frontend(args.skip_build)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + environment.get("PYTHONPATH", "")
    environment["TEXTBOOK_CHAT_PORT"] = str(port)
    backend_python = select_backend_python(environment)
    require_backend_dependencies(backend_python, environment)
    command = [
        str(backend_python), "-m", "uvicorn", "textbook_chat.app:app",
        "--host", "127.0.0.1", "--port", str(port),
    ]
    print(f"Using backend Python: {backend_python}", flush=True)
    print(f"Starting Local Textbook Chat at http://127.0.0.1:{port}", flush=True)
    process = subprocess.Popen(command, cwd=ROOT, env=environment)
    try:
        wait_until_ready(process, f"http://127.0.0.1:{port}/api/system/status")
        print("Ready. Press Ctrl+C to stop.", flush=True)
        if not args.no_browser:
            webbrowser.open(f"http://127.0.0.1:{port}/")
        return process.wait()
    except KeyboardInterrupt:
        print("\nStopping local services…", flush=True)
        return 0
    finally:
        stop_process(process)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError, ValueError) as error:
        print(f"Startup failed: {error}", file=sys.stderr)
        raise SystemExit(1)
