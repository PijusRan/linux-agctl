"""EQ / HPF / compressor on-off blocks: [bypass gain, effect gain] in Q2.14.

Hypothesis from captures (to be confirmed by tests/vectors): on -> (0, 0x4000), off -> (0x4000, 0).
CH1 blocks may additionally depend on the hardware COMP/EQ switch (CompEQ.On).
"""
from __future__ import annotations

from . import DspWrite

ADDR = {("HPF", 1): 0x1F, ("Comp", 1): 0x39, ("EQ", 1): 0x64,
        ("HPF", 2): 0x2B, ("Comp", 2): 0x48, ("EQ", 2): 0x7F}
ON, OFF = (0, 0x4000), (0x4000, 0)


def scene_writes(scene, ch: int, compeq_gate: bool = False) -> list[DspWrite]:
    out = []
    for kind in ("HPF", "Comp", "EQ"):
        on = bool(round(scene[f"{kind}{ch}.On"]))
        if compeq_gate and ch == 1 and kind in ("Comp", "EQ"):
            on = on and bool(round(scene["CompEQ.On"]))
        out.append(DspWrite(ADDR[(kind, ch)], ON if on else OFF))
    return out
