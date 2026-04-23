#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from backend.app_paths import app_home, default_download_root, default_runtime_root

REPO_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = REPO_ROOT / "backend"
VENV_DIR = BACKEND_DIR / ".venv"
REQUIREMENTS_FILE = BACKEND_DIR / "requirements.txt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Kidsnote app locally.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind the local web server to.")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8787")),
        help="Port to bind the local web server to.",
    )
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn auto-reload for development.")
    parser.add_argument("--desktop", action="store_true", help="Run the app in a native desktop window.")
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip dependency installation even when the virtual environment already exists.",
    )
    parser.add_argument(
        "--upgrade-deps",
        action="store_true",
        help="Reinstall dependencies in the virtual environment before starting.",
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the browser automatically after the server starts.",
    )
    parser.add_argument(
        "--desktop-smoke-test",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def run_checked(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True)


def ensure_virtualenv(base_python: str) -> tuple[Path, bool]:
    python_path = venv_python()
    if python_path.exists():
        return python_path, False
    print("[kidsnote] creating virtual environment...")
    run_checked([base_python, "-m", "venv", str(VENV_DIR)], cwd=BACKEND_DIR)
    return python_path, True


def install_requirements(python_path: Path) -> None:
    print("[kidsnote] installing dependencies...")
    run_checked([str(python_path), "-m", "ensurepip", "--upgrade"], cwd=BACKEND_DIR)
    run_checked([str(python_path), "-m", "pip", "install", "--upgrade", "pip"], cwd=BACKEND_DIR)
    run_checked([str(python_path), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)], cwd=BACKEND_DIR)


def requirements_fingerprint() -> str:
    return hashlib.sha256(REQUIREMENTS_FILE.read_bytes()).hexdigest()


def requirements_stamp_file() -> Path:
    return VENV_DIR / ".requirements.sha256"


def install_state_matches() -> bool:
    stamp = requirements_stamp_file()
    return stamp.exists() and stamp.read_text(encoding="utf-8").strip() == requirements_fingerprint()


def write_install_state() -> None:
    requirements_stamp_file().write_text(f"{requirements_fingerprint()}\n", encoding="utf-8")


def open_browser_later(url: str) -> None:
    def _open() -> None:
        time.sleep(1.5)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()


def main() -> int:
    args = parse_args()
    if not BACKEND_DIR.exists():
        print(f"[kidsnote] backend directory not found: {BACKEND_DIR}", file=sys.stderr)
        return 1

    python_path, created = ensure_virtualenv(sys.executable)
    needs_install = created or args.upgrade_deps or not install_state_matches()
    if needs_install and not args.skip_install:
        install_requirements(python_path)
        write_install_state()
    elif created:
        install_requirements(python_path)
        write_install_state()

    url = f"http://{args.host if args.host != '0.0.0.0' else '127.0.0.1'}:{args.port}"
    print(f"[kidsnote] app home: {app_home()}")
    print(f"[kidsnote] runtime dir: {default_runtime_root()}")
    print(f"[kidsnote] downloads dir: {default_download_root()}")

    if args.desktop:
        cmd = [
            str(python_path),
            str(BACKEND_DIR / "desktop_app.py"),
            "--host",
            args.host,
            "--port",
            str(args.port),
        ]
        if args.desktop_smoke_test:
            cmd.append("--smoke-test")
        print(f"[kidsnote] starting desktop app at {url}")
        completed = subprocess.run(cmd, cwd=str(BACKEND_DIR))
        return completed.returncode

    if args.open_browser:
        open_browser_later(url)

    cmd = [str(python_path), "-m", "uvicorn", "main:app", "--host", args.host, "--port", str(args.port)]
    if args.reload:
        cmd.append("--reload")

    print(f"[kidsnote] starting server at {url}")
    print("[kidsnote] press Ctrl+C to stop")
    completed = subprocess.run(cmd, cwd=str(BACKEND_DIR))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
