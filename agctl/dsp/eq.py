"""Parametric EQ / HPF coefficients (bilinear biquads, fixed-point) for AG06MK2 / AG03MK2.

Pipeline (matches the Yamaha controller bit-exactly, see tests/test_dsp_eq.py):
snap freq/gain/Q to the value series -> design biquad (K = tan(pi f / fs)) ->
quantise (16-bit with DC-gain compensation, or 28-bit split hi/lo) -> DSP words.

Coefficient convention: y = b0 x + b1 x1 + b2 x2 + a1 y1 + a2 y2 (a1/a2 stored negated).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import DspWrite

FS = 48000
SCALE = 0.5
P15 = 32768.0
P27 = 134217728.0

# ISO 1/12-octave preferred frequencies 20 Hz .. 20 kHz (121 values).
FREQS = (
    20, 21.2, 22.4, 23.6, 25, 26.5, 28, 30, 31.5, 33.5, 35.5, 37.5, 40, 42.5, 45, 47.5, 50, 53, 56, 60,
    63, 67, 71, 75, 80, 85, 90, 95, 100, 106, 112, 118, 125, 132, 140, 150, 160, 170, 180, 190,
    200, 212, 224, 236, 250, 265, 280, 300, 315, 335, 355, 375, 400, 425, 450, 475, 500, 530, 560, 600,
    630, 670, 710, 750, 800, 850, 900, 950, 1000, 1060, 1120, 1180, 1250, 1320, 1400, 1500, 1600, 1700,
    1800, 1900, 2000, 2120, 2240, 2360, 2500, 2650, 2800, 3000, 3150, 3350, 3550, 3750, 4000, 4250,
    4500, 4750, 5000, 5300, 5600, 6000, 6300, 6700, 7100, 7500, 8000, 8500, 9000, 9500, 10000, 10600,
    11200, 11800, 12500, 13200, 14000, 15000, 16000, 17000, 18000, 19000, 20000,
)
QS = (
    0.1, 0.11, 0.12, 0.14, 0.16, 0.18, 0.2, 0.22, 0.25, 0.28, 0.32, 0.35, 0.4, 0.45, 0.5, 0.56, 0.63,
    0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.5, 2.8, 3.2, 3.5, 4.0, 4.5, 5.0, 5.6, 6.3,
    7.0, 8.0, 9.0, 10.0,
)
GAINS = tuple(-18.0 + 0.5 * i for i in range(73))
HPF_MAX_INDEX = 59          # 600 Hz
HPF_Q = 1.0 / math.sqrt(2.0)   # Butterworth

# filter type codes
PEAK, LOW_SHELF, HIGH_SHELF, HPF2 = 0x0F, 0x10, 0x11, 0x0C
CSV_TYPE = {0: PEAK, 1: LOW_SHELF, 2: HIGH_SHELF, 3: HPF2}

BANDS = ("Low", "MidLow", "MidHigh", "High")
ADDR = {1: (0x4B, 0x55, 0x5A, 0x5F, 0x15), 2: (0x66, 0x70, 0x75, 0x7A, 0x21)}
PRECISION_28 = {"Low": True, "MidLow": False, "MidHigh": False, "High": False, "HPF": True}


def snap(value: float, table) -> tuple[float, int]:
    """RascalConv::SearchValue: nearest table entry (ties go to the higher entry)."""
    n = len(table)
    if value <= table[0]:
        return float(table[0]), 0
    i = 0
    while i < n and table[i] < value:
        i += 1
    if i == n:
        return float(table[-1]), n - 1
    if table[i] == value:
        return float(table[i]), i
    lo, hi = value - table[i - 1], table[i] - value
    return (float(table[i - 1]), i - 1) if lo < hi else (float(table[i]), i)


@dataclass
class Biquad:
    b0: float
    b1: float
    b2: float
    a1: float  # negated convention
    a2: float


def design(ftype: int, f: float, gain_db: float, q: float) -> Biquad:
    K = math.tan(f * 6.283185307179586 * (1.0 / FS) * 0.5)
    K2 = K * K
    V = 10.0 ** (abs(gain_db) * 0.05)
    if ftype == PEAK:
        if gain_db >= 0.0:
            kq = K / q
            norm = kq + 1.0 + K2
            vkq = (V * K) / q
            b0 = (vkq + 1.0 + K2) / norm
            b1 = ((1.0 - K2) * -2.0) / norm
            b2 = ((1.0 - vkq) + K2) / norm
            a2 = -((1.0 - kq) + K2) / norm
        else:
            vkq = (V * K) / q
            norm = vkq + 1.0 + K2
            b0 = (K / q + 1.0 + K2) / norm
            b1 = ((1.0 - K2) * -2.0) / norm
            b2 = ((1.0 - K / q) + K2) / norm
            a2 = -((1.0 - vkq) + K2) / norm
        return Biquad(b0, b1, b2, -b1, a2)
    if ftype == LOW_SHELF:
        if gain_db < 0.0:
            kq = K / q
            norm = kq + 1.0 + K2
            ks = K / (math.sqrt(V) * q)
            k2v = K2 / V
            b0 = (ks + 1.0 + k2v) / norm
            b1 = ((1.0 - k2v) * -2.0) / norm
            t = 1.0 - ks
            b2 = (k2v + t) / norm
            a1 = ((1.0 - K2) * 2.0) / norm
            a2 = -((1.0 - kq) + K2) / norm
        else:
            ks = K / (math.sqrt(V) * q)
            kq = K / q
            k2v = K2 / V
            norm = ks + 1.0 + k2v
            b0 = (kq + 1.0 + K2) / norm
            b1 = ((1.0 - K2) * -2.0) / norm
            t = 1.0 - kq
            b2 = (K2 + t) / norm
            a1 = ((1.0 - k2v) * 2.0) / norm
            a2 = -((1.0 - ks) + k2v) / norm
        return Biquad(b0, b1, b2, a1, a2)
    if ftype == HIGH_SHELF:
        if gain_db >= 0.0:
            iv = 1.0 / V
            ks = K / (math.sqrt(V) * q)
            norm = iv + ks + K2
            b0 = (K / q + 1.0 + K2) / norm
            b1 = ((1.0 - K2) * -2.0) / norm
            t = 1.0 - K / q
            b2 = (K2 + t) / norm
            a1 = ((iv - K2) * 2.0) / norm
            a2 = -((iv - ks) + K2) / norm
        else:
            kq = K / q
            norm = kq + 1.0 + K2
            iv = 1.0 / V
            ks = K / (math.sqrt(V) * q)
            b0 = (iv + ks + K2) / norm
            b1 = ((iv - K2) * -2.0) / norm
            t = iv - ks
            b2 = (K2 + t) / norm
            a1 = ((1.0 - K2) * 2.0) / norm
            a2 = -((1.0 - kq) + K2) / norm
        return Biquad(b0, b1, b2, a1, a2)
    if ftype == HPF2:
        norm = K / q + 1.0 + K2
        g = 10.0 ** (gain_db / 20.0)
        b0 = g / norm
        a1 = ((1.0 - K2) + (1.0 - K2)) / norm
        a2 = -((1.0 - K / q) + K2) / norm
        return Biquad(b0, b0 * -2.0, b0, a1, a2)
    raise ValueError(f"unsupported filter type {ftype:#x}")


def _q16(c: float) -> float:
    """Round to the 16-bit grid (floor(x + 0.5)) and return the value as a double."""
    return (float(math.floor(c * P15 * SCALE + 0.5)) / P15) / SCALE


def compensate(ftype: int, bq: Biquad) -> Biquad:
    """Cdd_1iirdgn::CompFilter for 16-bit mode: quantise, then nudge b1 to fix DC gain."""
    b0, b1, b2, a1, a2 = (_q16(x) for x in (bq.b0, bq.b1, bq.b2, bq.a1, bq.a2))
    if ftype in (PEAK, HIGH_SHELF, 0x04, 0x0B, 0x0E):
        target, rest = 1.0, b0 + a1 + b2 + a2
    elif ftype in (HPF2, 0x02, 0x0D):
        target, rest = 0.0, b0 + b2
    else:  # LOW_SHELF etc: plain quantisation
        return Biquad(b0, b1, b2, a1, a2)
    if ftype in (HPF2, 0x02, 0x0D):
        best, best_sum = b1, b1 + rest
        k = int(math.floor(P15 * b1 * SCALE))
        for i in range(1, 10):
            for cand_i in (k + i, k - i):
                c = (float(cand_i) / P15) / SCALE
                if -P15 <= c < P15 and abs(rest + c) < abs(best_sum):
                    best, best_sum = c, rest + c
        return Biquad(b0, best, b2, a1, a2)
    best, best_sum = b1, b1 + rest
    k = int(math.floor(P15 * b1 * SCALE))
    for i in range(1, 10):
        for cand_i in (k + i, k - i):
            c = (float(cand_i) / P15) / SCALE
            if -P15 <= c < P15 and abs(rest + c + -1.0) < abs(best_sum + -1.0):
                best, best_sum = c, rest + c
    return Biquad(b0, best, b2, a1, a2)


def _w16(c: float) -> int:
    if c == 0.0:
        return 0
    v = math.floor(c * SCALE * P15)
    return int(v) & 0xFFFF if -P15 <= v < P15 else 0xFFFF


def _w28(c: float) -> tuple[int, int]:
    if c == 0.0:
        return 0, 0
    v = math.floor(c * SCALE * P27 + 0.5)
    if not -P27 <= v < P27:
        return 0xFFFF, 0xFFFF
    v = int(v) & 0xFFFFFFFF
    return (v >> 12) & 0xFFFF, v & 0xFFF


def words(ftype: int, bq: Biquad, precision28: bool) -> tuple[int, ...]:
    coefs = (bq.b0, bq.b1, bq.b2, bq.a1, bq.a2)
    if precision28:
        out: list[int] = []
        for c in coefs:
            out.extend(_w28(c))
        return tuple(out)
    bq = compensate(ftype, bq)
    return tuple(_w16(c) for c in (bq.b0, bq.b1, bq.b2, bq.a1, bq.a2))


def band_write(ch: int, band: str, ftype: int, freq: float, gain: float, q: float) -> DspWrite:
    f, _ = snap(freq, FREQS)
    g, _ = snap(gain, GAINS)
    qq, _ = snap(q, QS)
    bq = design(ftype, f, g, qq)
    addr = ADDR[ch][BANDS.index(band)]
    return DspWrite(addr, words(ftype, bq, PRECISION_28[band]))


def band_write_csv(ch: int, band: str, csv_type: float, freq: float, gain: float, q: float) -> DspWrite:
    """Band from scene values. Non-peaking types use a fixed Butterworth Q (the Q value is ignored)."""
    ftype = CSV_TYPE.get(int(round(csv_type)), PEAK)
    if ftype == PEAK:
        return band_write(ch, band, ftype, freq, gain, q)
    f, _ = snap(freq, FREQS)
    g, _ = snap(gain, GAINS)
    bq = design(ftype, f, g, HPF_Q)
    return DspWrite(ADDR[ch][BANDS.index(band)], words(ftype, bq, PRECISION_28[band]))


def hpf_write(ch: int, freq: float) -> DspWrite:
    f, i = snap(freq, FREQS)
    if i > HPF_MAX_INDEX:
        f = float(FREQS[HPF_MAX_INDEX])
    bq = design(HPF2, f, 0.0, HPF_Q)
    return DspWrite(ADDR[ch][4], words(HPF2, bq, PRECISION_28["HPF"]))


def scene_writes(scene, ch: int) -> list[DspWrite]:
    out = []
    for band in BANDS:
        p = f"EQ{ch}.{band}."
        out.append(band_write_csv(ch, band, scene[p + "Type"], scene[p + "Freq"], scene[p + "Gain"],
                                  scene[p + "Q"]))
    out.append(hpf_write(ch, scene[f"HPF{ch}.Frequency"]))
    return out
