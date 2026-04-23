#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
DIST_ROOT = REPO_ROOT / "dist" / "windows"
BUILD_ROOT = REPO_ROOT / "build" / "windows"
ENTRY_SCRIPT = BACKEND_DIR / "desktop_app.py"
FRONTEND_DIR = REPO_ROOT / "frontend"
BUILD_REQUIREMENTS = Path(__file__).with_name("requirements-build.txt")
INSTALLER_SCRIPT = Path(__file__).with_name("installer.iss")

sys.path.insert(0, str(BACKEND_DIR))
from version import APP_NAME, APP_PUBLISHER, APP_SLUG, APP_VERSION  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Windows desktop bundle and installer.")
    parser.add_argument("--version", default=os.environ.get("KIDSNOTE_APP_VERSION", APP_VERSION))
    parser.add_argument("--clean", action="store_true", help="Delete previous build/dist output first.")
    parser.add_argument("--skip-installer", action="store_true", help="Build the app bundle only.")
    parser.add_argument(
        "--bundle-only",
        action="store_true",
        help="Alias for --skip-installer.",
    )
    parser.add_argument(
        "--install-build-deps",
        action="store_true",
        help="Install PyInstaller into the selected Python environment before building.",
    )
    parser.add_argument(
        "--python",
        default=os.environ.get("KIDSNOTE_BUILD_PYTHON", ""),
        help="Python executable to use for PyInstaller. Defaults to backend/.venv on Windows.",
    )
    parser.add_argument(
        "--iscc",
        default=os.environ.get("ISCC_EXE", ""),
        help="Path to Inno Setup's ISCC.exe. Required when building the installer.",
    )
    parser.add_argument(
        "--allow-non-windows",
        action="store_true",
        help="Allow bundle-only validation on non-Windows hosts.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    skip_installer = args.skip_installer or args.bundle_only
    if sys.platform != "win32" and not args.allow_non_windows:
        print("[kidsnote] Windows build must be executed on Windows. Use --allow-non-windows for bundle validation.", file=sys.stderr)
        return 1
    if sys.platform != "win32":
        skip_installer = True

    python_path = resolve_python(args.python)
    if not python_path.exists():
        print(f"[kidsnote] build Python not found: {python_path}", file=sys.stderr)
        return 1

    if args.clean:
        shutil.rmtree(DIST_ROOT, ignore_errors=True)
        shutil.rmtree(BUILD_ROOT, ignore_errors=True)

    DIST_ROOT.mkdir(parents=True, exist_ok=True)
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)

    if args.install_build_deps:
        install_build_dependencies(python_path)

    build_bundle(python_path)

    if skip_installer:
        print(f"[kidsnote] bundle ready: {bundle_dir()}")
        return 0

    iscc_path = resolve_iscc(args.iscc)
    if not iscc_path:
        print("[kidsnote] ISCC.exe not found. Install Inno Setup 6 or pass --iscc.", file=sys.stderr)
        return 1

    build_installer(iscc_path, args.version)
    print(f"[kidsnote] installer ready: {installer_output_dir()}")
    return 0


def resolve_python(cli_value: str) -> Path:
    if cli_value:
        return Path(cli_value).expanduser()
    if os.name == "nt":
        candidate = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
        if candidate.exists():
            return candidate
    else:
        candidate = BACKEND_DIR / ".venv" / "bin" / "python"
        if candidate.exists():
            return candidate
    return Path(sys.executable)


def install_build_dependencies(python_path: Path) -> None:
    run_checked([str(python_path), "-m", "pip", "install", "-r", str(BUILD_REQUIREMENTS)], cwd=REPO_ROOT)


def build_bundle(python_path: Path) -> None:
    add_data_sep = ";" if os.name == "nt" else ":"
    dist_dir = DIST_ROOT / "app"
    work_dir = BUILD_ROOT / "pyinstaller"
    spec_dir = BUILD_ROOT / "spec"
    dist_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    spec_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(python_path),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_SLUG,
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
        "--paths",
        str(BACKEND_DIR),
        "--collect-submodules",
        "webview",
        "--collect-submodules",
        "uvicorn",
        "--add-data",
        f"{FRONTEND_DIR}{add_data_sep}frontend",
        str(ENTRY_SCRIPT),
    ]
    run_checked(cmd, cwd=REPO_ROOT)


def resolve_iscc(cli_value: str) -> Path | None:
    candidates = []
    if cli_value:
        candidates.append(Path(cli_value).expanduser())
    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        candidates.extend([
            Path(program_files_x86) / "Inno Setup 6" / "ISCC.exe",
            Path(program_files) / "Inno Setup 6" / "ISCC.exe",
        ])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def build_installer(iscc_path: Path, version: str) -> None:
    output_dir = installer_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(iscc_path),
        f"/DAppVersion={version}",
        f"/DAppPublisher={APP_PUBLISHER}",
        f"/DSourceDir={bundle_dir()}",
        f"/DOutputDir={output_dir}",
        str(INSTALLER_SCRIPT),
    ]
    run_checked(cmd, cwd=REPO_ROOT)


def bundle_dir() -> Path:
    return DIST_ROOT / "app" / APP_SLUG


def installer_output_dir() -> Path:
    return DIST_ROOT / "installer"


def run_checked(cmd: list[str], cwd: Path) -> None:
    print(f"[kidsnote] {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(cwd), check=True)


if __name__ == "__main__":
    raise SystemExit(main())
