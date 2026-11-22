"""Compressor (DRC) words for AG06MK2 / AG03MK2 channel 1/2.

Verified bit-exactly against Yamaha AG Controller output (tests/test_dsp_comp.py).
"""
from __future__ import annotations

import math

from . import DspWrite

BASE = {1: 0x2D, 2: 0x3C}
RATIOS = (1.0, 1.1, 1.3, 1.5, 1.7, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0, 10.0, 20.0, 1.7976931348623157e308)
# Release times (ms) offered by the controller.
RELEASES = (
    0.241, 5, 11, 16, 21, 27, 32, 37, 43, 48, 53, 59, 64, 69, 75, 80, 85, 91, 96, 101, 107, 112, 117,
    123, 128, 133, 139, 144, 149, 155, 160, 165, 171, 176, 187, 197, 208, 219, 229, 240, 251, 261, 272,
    283, 293, 304, 315, 325, 336, 347, 368, 389, 411, 432, 453, 475, 496, 517, 539, 560, 581, 603, 624,
    645, 667, 688, 730, 773, 816, 858, 901, 944, 986, 1030, 1070, 1110, 1160, 1200, 1240, 1290, 1330,
    1370, 1460, 1540, 1630, 1710, 1800, 1880, 1970, 2050, 2140, 2220, 2310, 2390, 2480, 2570, 2650,
    2740, 2910, 3080, 3250, 3420, 3590, 3760, 3930, 4100, 4270, 4440, 4610, 4780, 4950, 5120, 5300,
    5470, 5810, 6150, 6490, 6830, 7170, 7510, 7850, 8200, 8540, 8880, 9220, 9560, 9900, 10200, 10600,
    10900, 11600, 12300, 13000, 13700, 14300, 15000, 15800,
)
THR_RANGE, THR_STEP = (-90.0, 0.0), 1.0
GAIN_RANGE, GAIN_STEP = (-74.7, 18.0), 0.1
ATK_RANGE, ATK_STEP = (0.0, 100.0), 1.0
HOLD = 1          # fixed DRC field [7]
INPUT_SHIFT = 0   # fixed DRC field [0]


def _fix(x: float) -> float:
    return float(math.trunc(x))


def _round(x: float) -> float:
    return float(round(x))  # half to even, like the original


def _fix16(x: float) -> int:
    v = math.floor(x * 32768.0 + 0.5)
    if v >= 32768.0:
        return 0x7FFF
    if v < -32768.0:
        return 0x8000
    return int(v) & 0xFFFF


def _fix16e(x: float) -> int:
    v = math.floor(x * 32768.0 + 0.5)
    if v == 0.0:
        return 0
    if v == 32768.0:
        return 0x7FFF
    if v < -32768.0 or v > 32768.0:
        return 0x0000  # (int)0x80000000 truncated to 16 bits
    return int(v) & 0xFFFF


def _fix28(x: float) -> int:
    v = math.floor(x * 134217728.0 + 0.5)
    if v >= 134217728.0:
        return 0x7FFFFFF
    if v < -134217728.0:
        return 0x8000000
    return int(v) & 0xFFFFFFFF


def _half_away(x: float) -> int:
    return int(x + (0.5 if x >= 0 else -0.5))


def _snap_step(v: float, rng: tuple[float, float], step: float) -> float:
    lo, hi = rng
    if v < lo or v > hi:
        return lo if v < lo else hi
    i = _half_away(v * 100.0)
    s = _half_away(step * 100.0)
    if i % s == 0 if i >= 0 else (-i) % s == 0:
        return v
    a = abs(i)
    r = s if (a % s) - (s >> 1) >= 0 else 0
    a = (r - a % s) + a
    return (a if i >= 0 else -a) / 100.0


def _snap_table(v: float, table) -> float:
    n = len(table)
    if v <= table[0]:
        return float(table[0])
    i = 0
    while i < n and table[i] < v:
        i += 1
    if i == n:
        return float(table[-1])
    if table[i] == v:
        return float(table[i])
    return float(table[i - 1]) if (v - table[i - 1]) < (table[i] - v) else float(table[i])


def coef_words(threshold: float, ratio: float, gain: float, attack: float, release: float) -> list[int]:
    """Return the 11 DRC words (indices 0..10) for scene values."""
    thr = _half_away(threshold)
    ratio = 1.7976931348623157e308 if ratio > 20.0 else ratio
    atk = _half_away(attack)
    # FUN_100076b20 snapping
    thr = int(_snap_step(float(thr), THR_RANGE, THR_STEP))
    gain = _snap_step(gain, GAIN_RANGE, GAIN_STEP)
    atk = int(_snap_step(float(atk), ATK_RANGE, ATK_STEP))
    ratio = _snap_table(ratio, RATIOS)
    release = min(_snap_table(release, RELEASES), 15800.0)
    if gain != 0.0 and ratio == 1.0:
        gain = 0.0
    atk = min(atk, 100)
    # _DRC_CoefMaker
    r = 1.0 / ratio
    r = _fix(r * 10000.0) / 10000.0
    w2 = _fix16(r * 0.5)
    gain = _fix(gain * 100.0) / 100.0
    t = (r + -1.0) * float(thr)
    d13 = _fix(float(INPUT_SHIFT) * 6.02 * (1.0 - r) + t)
    w0 = _fix16e(10.0 ** (d13 / -20.0))
    if r == 1.0 and gain != 0.0:
        gain = 0.0
    t = (r + -1.0) * float(thr) - gain
    d11 = _fix((1.0 - r) * float(INPUT_SHIFT) * 6.02 + t)
    w1 = _fix16e(10.0 ** (d11 / -20.0))
    rel = _fix(release * 1000.0) / 1000.0
    c = 65535.0 if rel == 0.241 else 15.812174479166666 / (rel * 0.001)
    w3 = int(_round(c)) & 0xFFFF
    w4 = int(_round((float(HOLD) * 1000.0) / 167.0)) & 0xFFFF
    if atk == 0:
        w5, w6, w7, w8, w9, w10 = 0x4000, 0, 0, 0, 0, 0
    else:
        fc = _fix(1.0 / ((float(atk) / 1000.0) * 6.28318530717958))
        k = math.tan(fc * 6.28318530717958 * 2.0833333333333333e-05 * 0.5)
        u6 = _fix28((k / (k + 1.0)) * 0.5)
        u7 = _fix28(((1.0 - k) / (k + 1.0)) * 0.5)
        w5 = (u6 >> 12) & 0xFFFF
        w6 = u6 & 0xFFF
        w7, w8 = w5, w6
        w9 = (u7 >> 12) & 0xFFFF
        w10 = u7 & 0xFFF
    return [w0, w1, w2, w3, w4, w5, w6, w7, w8, w9, w10]


def writes(ch: int, threshold, ratio, gain, attack, release) -> list[DspWrite]:
    w = coef_words(threshold, ratio, gain, attack, release)
    b = BASE[ch]
    return [DspWrite(b, tuple(w[0:3])), DspWrite(b + 5, tuple(w[5:11])), DspWrite(b + 3, (w[3],))]


def scene_writes(scene, ch: int) -> list[DspWrite]:
    """From scene (CSV) values. Attack and release are whole milliseconds in the scene model
    (the controller truncates fractional values when it loads a scene)."""
    p = f"Comp{ch}."
    return writes(ch, scene[p + "Threshold"], scene[p + "Ratio"], scene[p + "Gain"],
                  float(math.trunc(scene[p + "Attack"])), float(math.trunc(scene[p + "Release"])))
