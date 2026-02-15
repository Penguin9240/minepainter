#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


APP_NAME = "MinePainter"
ENTRYPOINT = "minepainter/main.py"


def run_pyinstaller() -> None:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--windowed",
        "--name",
        APP_NAME,
        "--collect-all",
        "PySide6",
        "--collect-submodules",
        "OpenGL",
    ]
    if sys.platform.startswith("win"):
        cmd.append("--onefile")
    cmd.append(ENTRYPOINT)
    subprocess.run(cmd, check=True)


def prepare_release_asset() -> Path:
    release_dir = Path("release-assets")
    release_dir.mkdir(exist_ok=True)

    if sys.platform == "darwin":
        app_bundle = Path("dist") / f"{APP_NAME}.app"
        if not app_bundle.exists():
            raise FileNotFoundError(f"Missing expected macOS bundle: {app_bundle}")
        archive_base = release_dir / "MinePainter.app"
        zip_path = Path(shutil.make_archive(str(archive_base), "zip", "dist", f"{APP_NAME}.app"))
        return zip_path

    if sys.platform.startswith("win"):
        exe_path = Path("dist") / f"{APP_NAME}.exe"
        if not exe_path.exists():
            raise FileNotFoundError(f"Missing expected Windows executable: {exe_path}")
        out = release_dir / "MinePainter-windows.exe"
        shutil.copy2(exe_path, out)
        return out

    raise RuntimeError(f"Unsupported platform for release packaging: {sys.platform}")


def main() -> None:
    run_pyinstaller()
    asset = prepare_release_asset()
    print(f"Prepared release asset: {asset}")


if __name__ == "__main__":
    main()
