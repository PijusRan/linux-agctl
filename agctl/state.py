"""agctl's own copy of the mixer scene (the mixer cannot report its DSP settings)."""
from __future__ import annotations

import glob
import os
from pathlib import Path

from .scene import Scene

STATE = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "agctl" / "scene.csv"
WINE_GLOB = str(Path.home() / ".local/share/yamaha-ag-controller/wine/drive_c/users/*/AppData/Roaming/"
                "Yamaha/AGController/scene_user_00.csv")


def yamaha_scene_path() -> Path | None:
    hits = sorted(glob.glob(WINE_GLOB))
    return Path(hits[0]) if hits else None


def load() -> Scene | None:
    return Scene.load(STATE) if STATE.exists() else None


def save(scene: Scene) -> None:
    scene.save(STATE)


def import_scene(path: Path | None = None) -> Scene:
    src = path or yamaha_scene_path()
    if src is None or not Path(src).exists():
        raise FileNotFoundError("no scene to import (Yamaha AG Controller scene_user_00.csv not found)")
    sc = Scene.load(src)
    save(sc)
    return sc
