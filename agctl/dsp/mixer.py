"""Scene -> DSP writes, per parameter or for a whole group."""
from __future__ import annotations

from . import DspWrite, comp, eq, levels


def _level_writes(scene) -> list[DspWrite]:
    out = [levels.pan_write("Pan1", scene["Pan1"]), levels.pan_write("Pan2", scene["Pan2"])]
    for name in ("FXSend1", "FXSend2", "Rev.OutputLevel", "Rev.Dry/Wet"):
        out.append(levels.level_write(name, levels.csv_db(scene[name], name)))
    return out


def writes_for(scene, column: str) -> list[DspWrite]:
    """DSP blocks that depend on one scene column (empty if not a verified DSP parameter)."""
    if column in ("Pan1", "Pan2"):
        return [levels.pan_write(column, scene[column])]
    if column in ("FXSend1", "FXSend2", "Rev.OutputLevel", "Rev.Dry/Wet"):
        return [levels.level_write(column, levels.csv_db(scene[column], column))]
    if column.startswith(("EQ1.", "HPF1.")) and not column.endswith(".On"):
        return eq.scene_writes(scene, 1)
    if column.startswith(("EQ2.", "HPF2.")) and not column.endswith(".On"):
        return eq.scene_writes(scene, 2)
    if column.startswith("Comp1.") and not column.endswith(".On"):
        return comp.scene_writes(scene, 1)
    if column.startswith("Comp2.") and not column.endswith(".On"):
        return comp.scene_writes(scene, 2)
    return []


def all_verified_writes(scene) -> list[DspWrite]:
    return (_level_writes(scene) + eq.scene_writes(scene, 1) + eq.scene_writes(scene, 2)
            + comp.scene_writes(scene, 1) + comp.scene_writes(scene, 2))
