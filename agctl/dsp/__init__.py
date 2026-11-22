"""Host-side DSP value computation for AG06MK2 / AG03MK2 (cmd 0x1000 writes).

Every group here is checked bit-exactly against what Yamaha's own AG Controller sends for the
same settings (see tests/vectors). A write is ``DspWrite(address, words)``.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DspWrite:
    address: int
    words: tuple[int, ...]

    def payload(self) -> bytes:
        out = bytearray(self.address.to_bytes(2, "little"))
        out += (len(self.words) - 1).to_bytes(2, "little")
        for w in self.words:
            out += (w & 0xFFFF).to_bytes(2, "little")
        return bytes(out)

    @classmethod
    def from_payload(cls, data: bytes) -> "DspWrite":
        addr = int.from_bytes(data[0:2], "little")
        n = int.from_bytes(data[2:4], "little") + 1
        return cls(addr, tuple(int.from_bytes(data[4 + 2 * i:6 + 2 * i], "little") for i in range(n)))
