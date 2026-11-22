"""Pan and level words (Q2.14 linear gain; 0x4000 = unity)."""
from __future__ import annotations

import math
import struct

from . import DspWrite

ADDR = {
    "Pan1": 0x28E, "Pan2": 0x291,
    "CH1.OutputLevel": 0x290, "CH2.OutputLevel": 0x293,
    "FXSend1": 0x209, "FXSend2": 0x20A,
    "Rev.OutputLevel": 0x294, "Rev.Dry/Wet": 0x28C,
}
UNITY = 0x4000


def _f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def pan_left_gain(pan: int) -> float:
    """Left-channel gain for pan -63..63 (sin/cos law, +3 dB at the edges), as float32."""
    i = int(pan) + 63
    if not 0 <= i <= 126:
        raise ValueError("pan out of range -63..63")
    return 0.0 if i == 126 else _f32(math.sqrt(2.0) * math.cos(math.pi / 2 * i / 126))


def gain_word(lin: float) -> int:
    v = int(lin * 16384.0)
    return v if 0 <= v < 0x8000 else 0xFFFF


# Fader step table: segments of (start, count, step) in 1/100 dB, built exactly like the controller.
_SEGMENTS = ((-1.7976931348623156e306, 1, 0.0), (-13800.0, 14, 300.0), (-9600.0, 18, 100.0),
             (-7800.0, 190, 20.0), (-4000.0, 200, 10.0), (-2000.0, 401, 5.0))


def _build_table() -> tuple[float, ...]:
    out = []
    for start, count, step in _SEGMENTS:
        v = start
        for _ in range(count):
            out.append(v / 100.0)
            v += step
    return tuple(out)


FADER_TABLE = _build_table()          # 824 entries, ascending, first is "-inf"
TRUNCATED = ("FXSend1", "FXSend2", "Rev.Dry/Wet")


def snap_db(db: float) -> float:
    t = FADER_TABLE
    if db <= t[0]:
        return t[0]
    i = 0
    while i < len(t) and t[i] < db:
        i += 1
    if i == len(t):
        return t[-1]
    if t[i] == db:
        return t[i]
    return t[i - 1] if (db - t[i - 1]) < (t[i] - db) else t[i]


def csv_db(value: float, name: str = "") -> float:
    """Scene value -> dB the controller actually uses (scene-load rounding)."""
    if name in TRUNCATED and value <= -1.0:
        value = float(math.trunc(value))
    return min(value, 0.0) if value <= 0.0 else 0.0


def level_word(db: float) -> int:
    if db == -math.inf:
        return 0
    if db > 0.0:
        return 0xFFFF
    lin = 10.0 ** (db / 20.0)
    return int(lin * 16384.0)


def pan_write(name: str, pan: float) -> DspWrite:
    p = int(round(pan))
    return DspWrite(ADDR[name], (gain_word(pan_left_gain(p)), gain_word(pan_left_gain(-p))))


def level_write(name: str, db: float) -> DspWrite:
    w = level_word(snap_db(db))
    words = (w, w) if name == "Rev.Dry/Wet" else (w,)
    return DspWrite(ADDR[name], words)
