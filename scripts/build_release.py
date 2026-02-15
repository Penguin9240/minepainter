#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


APP_NAME = "MinePainter"
ENTRYPOINT = "minepainter/main.py"
ICON_SOURCE = Path("MinepainterLogo.png")


def _ensure_icon() -> Path:
    if not ICON_SOURCE.exists():
        raise FileNotFoundError(f"Missing icon source image: {ICON_SOURCE}")

    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required to generate app icon files") from exc

    out_dir = Path("build") / "icons"
    out_dir.mkdir(parents=True, exist_ok=True)

    if sys.platform == "darwin":
        icns_path = out_dir / "MinePainter.icns"
        image = Image.open(ICON_SOURCE).convert("RGBA")
        image.save(icns_path, format="ICNS")
        return icns_path

    if sys.platform.startswith("win"):
        ico_path = out_dir / "MinePainter.ico"
        image = Image.open(ICON_SOURCE).convert("RGBA")
        image.save(
            ico_path,
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
        return ico_path

    raise RuntimeError(f"Unsupported platform for icon generation: {sys.platform}")


def run_pyinstaller() -> None:
    icon_path = _ensure_icon()
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--windowed",
        "--name",
        APP_NAME,
        "--icon",
        str(icon_path),
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
        zip_path = release_dir / "MinePainter.app.zip"
        if zip_path.exists():
            zip_path.unlink()
        # Use `ditto` for macOS app bundles so symlinks/metadata are preserved.
        subprocess.run(
            [
                "ditto",
                "-c",
                "-k",
                "--sequesterRsrc",
                "--keepParent",
                str(app_bundle),
                str(zip_path),
            ],
            check=True,
        )
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
