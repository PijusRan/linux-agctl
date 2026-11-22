"""Yamaha AG06MK2 / AG03MK2 control protocol ("Rascal" SysEx), safe subset.

Message layout (both directions)::

    F0 43 <dev> 3E 1C 78 00 | seq_lo seq_hi | cmd_lo cmd_hi | packed payload | F7

* ``dev`` is 0x10 for commands with bit 0x1000 set and 0x30 otherwise
  (the mixer replies with the other value; receivers ignore it).
* ``seq`` is a 13-bit counter split into 7-bit halves; replies echo it.
* ``cmd`` is sent as two raw bytes, low byte first; both bytes must be 7-bit
  (e.g. 0x2F00 -> ``00 2F``). A reply carries ``cmd | 0x4000``.
* The payload is 8-bit data packed LSB-first into 7-bit bytes.

Only commands that need no DSP-coefficient maths are implemented here:
model name, level meters / switch status, the four hardware switches and the
foot switch function. See docs/protocol.md.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

HEADER = (0xF0, 0x43, 0x00, 0x3E, 0x1C, 0x78, 0x00)
HEADER_LEN = len(HEADER)

CMD_GET_INFO = 0x2F00      # payload u16 info id + 2 pad bytes; reply carries id + string
CMD_GET_HASH = 0x2006      # reply: 32-byte hash of the mixer's parameter memory
CMD_SWITCH = 0x1030        # payload [index, on]
CMD_METER = 0x1040         # payload [1] start / [0] stop streaming
CMD_FOOTSWITCH = 0x1050    # payload [0x10, function]
CMD_DSP_WRITE = 0x1000     # payload [addr u16][n-1 u16][n x u16] (see agctl.dsp)
CMD_SET_HASH = 0x1006      # payload: 32-byte scene hash (sent by the controller after a full sync)
CMD_METER_STATUS = 0x6041  # unsolicited: meters + switch status (~every 50 ms)
REPLY_FLAG = 0x4000

INFO_MODEL_NAME = 0x0010

SWITCHES = {
    # name: (index for CMD_SWITCH, bit in status byte, label)
    "ch1_fx": (0, 0, "CH1 effect (reverb) send"),
    "ch2_fx": (1, 1, "CH2 effect (reverb) send"),
    "ch1_compeq": (2, 2, "CH1 COMP/EQ"),
    "ch2_ampsim": (3, 3, "CH2 AMP SIM"),
}

FOOTSWITCH_FUNCTIONS = {0: "Reverb on/off", 1: "CH1 mute on/off"}

METER_NAMES = (
    "ch1_in", "ch2_in", "ch1_comp", "ch2_comp", "ch1_out", "ch2_out",
    "fx_l", "fx_r", "master_l", "master_r", "ch1_out_ag01",
)
SUPPORTED_MODELS = ("AG06MK2", "AG03MK2")


def pack7(data: bytes | list[int]) -> list[int]:
    """Pack 8-bit bytes into 7-bit MIDI data bytes, LSB first."""
    out: list[int] = []
    acc = bits = 0
    for b in data:
        acc |= (b & 0xFF) << bits
        bits += 8
        while bits >= 7:
            out.append(acc & 0x7F)
            acc >>= 7
            bits -= 7
    if bits:
        out.append(acc & 0x7F)
    return out


def unpack7(data: bytes | list[int]) -> bytes:
    """Inverse of :func:`pack7` (trailing partial bits are dropped)."""
    out = bytearray()
    acc = bits = 0
    for b in data:
        acc |= (b & 0x7F) << bits
        bits += 7
        while bits >= 8:
            out.append(acc & 0xFF)
            acc >>= 8
            bits -= 8
    return bytes(out)


def build(cmd: int, seq: int, payload: bytes | list[int] = b"") -> list[int]:
    if cmd & ~0x7F7F:
        raise ValueError("cmd bytes must be 7-bit")
    msg = list(HEADER)
    msg[2] = 0x10 if cmd & 0x1000 else 0x30
    seq &= 0x1FFF
    msg += [seq & 0x7F, seq >> 7, cmd & 0xFF, cmd >> 8]
    msg += pack7(payload)
    msg.append(0xF7)
    return msg


@dataclass
class Message:
    seq: int
    cmd: int
    data: bytes

    @property
    def is_reply(self) -> bool:
        return bool(self.cmd & REPLY_FLAG)


def parse(raw: bytes | list[int]) -> Message | None:
    """Parse a received SysEx; returns None for anything that is not ours."""
    raw = list(raw)
    if len(raw) < HEADER_LEN + 5 or raw[0] != 0xF0 or raw[-1] != 0xF7:
        return None
    if raw[1] != 0x43 or raw[3:HEADER_LEN] != list(HEADER[3:]):
        return None
    seq = raw[7] | (raw[8] << 7)
    cmd = raw[9] | (raw[10] << 8)
    return Message(seq, cmd, unpack7(raw[11:-1]))


# ---- command payloads -------------------------------------------------------

def switch_payload(name: str, on: bool) -> list[int]:
    return [SWITCHES[name][0], 1 if on else 0]


def footswitch_payload(function: int) -> list[int]:
    if function not in FOOTSWITCH_FUNCTIONS:
        raise ValueError(f"foot switch function must be one of {sorted(FOOTSWITCH_FUNCTIONS)}")
    return [0x10, function]


def info_payload(info_id: int) -> list[int]:
    return [info_id & 0xFF, info_id >> 8, 0, 0]


def parse_info_reply(data: bytes) -> str:
    return data[2:].split(b"\0", 1)[0].decode("ascii", "replace")


# ---- meters / status --------------------------------------------------------

def level_to_db(word: int) -> float:
    """Meter word (0..32767, negative = clip) to dBFS."""
    if word == 0:
        return -math.inf
    if word >= 0x8000:
        return 0.0
    return 20.0 * math.log10(word / 32767.0)


@dataclass
class Status:
    meters_db: dict[str, float] = field(default_factory=dict)
    switches: dict[str, bool] = field(default_factory=dict)
    footswitch: int = 0
    raw: bytes = b""


def parse_status(data: bytes) -> Status:
    """Decode a CMD_METER_STATUS payload.

    Layout: [count][?][count x u16 LE meter words][?][status bits][?][foot switch].
    """
    if len(data) < 2:
        raise ValueError("status payload too short")
    count = data[0]
    words = [int.from_bytes(data[2 + 2 * i: 4 + 2 * i], "little") for i in range(count)]
    tail = data[2 + 2 * count:]
    bits = tail[1] if len(tail) > 1 else 0
    foot = tail[3] if len(tail) > 3 else 0
    meters = {METER_NAMES[i]: level_to_db(w) for i, w in enumerate(words) if i < len(METER_NAMES)}
    switches = {name: bool(bits >> bit & 1) for name, (_, bit, _) in SWITCHES.items()}
    return Status(meters, switches, foot, bytes(data))
