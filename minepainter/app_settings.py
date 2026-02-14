from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path


CONFIG_PATH = Path("~/.config/minepainter.conf").expanduser()
SECTION_UI = "ui"
KEY_THEME = "theme"
THEME_DARK = "dark"
THEME_LIGHT = "light"


def _read_config() -> ConfigParser:
    cfg = ConfigParser()
    if CONFIG_PATH.exists():
        cfg.read(CONFIG_PATH)
    return cfg


def load_theme() -> str:
    cfg = _read_config()
    value = cfg.get(SECTION_UI, KEY_THEME, fallback=THEME_DARK).strip().lower()
    return value if value in (THEME_DARK, THEME_LIGHT) else THEME_DARK


def save_theme(theme: str) -> None:
    theme_value = theme.strip().lower()
    if theme_value not in (THEME_DARK, THEME_LIGHT):
        theme_value = THEME_DARK

    cfg = _read_config()
    if not cfg.has_section(SECTION_UI):
        cfg.add_section(SECTION_UI)
    cfg.set(SECTION_UI, KEY_THEME, theme_value)

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        cfg.write(f)
