"""Guard rails for raw DSP writes (cmd 0x1000).

Only blocks whose host-side maths has been verified bit-exactly against Yamaha's own controller
(tests/vectors) may be written. Every write is checked against the known address and word count
before it is sent; anything unexpected raises SafetyError and nothing is transmitted.
"""
from __future__ import annotations

from .dsp import DspWrite


class SafetyError(RuntimeError):
    pass


# address -> (group, word count)
_BLOCKS: dict[int, tuple[str, int]] = {}


def _add(group: str, count: int, *addrs: int) -> None:
    for a in addrs:
        _BLOCKS[a] = (group, count)


# Levels / pan (verified)
_add("levels", 2, 0x28E, 0x291, 0x28C)
_add("levels", 1, 0x290, 0x293, 0x209, 0x20A, 0x294)
# EQ bands: low band + HPF are 28-bit (10 words), others 16-bit (5 words) (verified)
_add("eq", 10, 0x4B, 0x66, 0x15, 0x21)
_add("eq", 5, 0x55, 0x5A, 0x5F, 0x70, 0x75, 0x7A)
# Compressor (verified)
_add("comp", 3, 0x2D, 0x3C)
_add("comp", 1, 0x30, 0x3F)
_add("comp", 6, 0x32, 0x41)

VERIFIED_GROUPS = frozenset({"levels", "eq", "comp"})


def group_of(address: int) -> str | None:
    b = _BLOCKS.get(address)
    return b[0] if b else None


def check(write: DspWrite) -> None:
    block = _BLOCKS.get(write.address)
    if block is None:
        raise SafetyError(f"DSP address {write.address:#06x} is not on the allow-list")
    group, count = block
    if group not in VERIFIED_GROUPS:
        raise SafetyError(f"DSP group '{group}' is not verified yet")
    if len(write.words) != count:
        raise SafetyError(f"{write.address:#06x}: expected {count} words, got {len(write.words)}")
    for w in write.words:
        if not 0 <= w <= 0xFFFF:
            raise SafetyError(f"{write.address:#06x}: word out of range: {w}")
    if group == "levels" and any(w > 0x5A82 and w != 0xFFFF for w in write.words):
        # gains never exceed +3 dB (pan law max sqrt(2) = 0x5A82)
        raise SafetyError(f"{write.address:#06x}: gain word above +3 dB")
    if group == "levels" and 0xFFFF in write.words:
        raise SafetyError(f"{write.address:#06x}: invalid gain (above 0 dB)")
