"""Application paths shared by persistence and the desktop UI."""

from __future__ import annotations

import os
from pathlib import Path
import sys


APP_DIR_NAME = "WIT-Combat-Manager"


def writable_data_dir() -> Path:
    """Return a stable writable directory for user-created application data."""

    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            target = Path(local_app_data) / APP_DIR_NAME
        else:
            target = Path.home() / "AppData" / "Local" / APP_DIR_NAME
    else:
        target = Path.home() / ".local" / "share" / APP_DIR_NAME

    target.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_files(target)
    return target


def _migrate_legacy_files(target: Path) -> None:
    """Copy old beside-executable data once when moving to the app-data folder."""

    legacy_dir = Path(sys.executable).resolve().parent
    if legacy_dir == target:
        return
    for name in (
        "data.json",
        "combat_state.json",
        "settings.json",
        "combat_log.txt",
        "gm_log.txt",
    ):
        source = legacy_dir / name
        destination = target / name
        if destination.exists() or not source.is_file():
            continue
        try:
            destination.write_bytes(source.read_bytes())
        except OSError:
            continue
