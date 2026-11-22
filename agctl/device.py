"""MIDI transport for the AG06MK2 / AG03MK2 via ALSA (python-rtmidi)."""
from __future__ import annotations

import threading
import time
from typing import Callable

import rtmidi

from . import protocol as p

PORT_HINTS = p.SUPPORTED_MODELS


class DeviceError(RuntimeError):
    pass


def find_port(names: list[str]) -> int | None:
    for i, name in enumerate(names):
        if any(h in name for h in PORT_HINTS):
            return i
    return None


def is_present() -> bool:
    try:
        return find_port(rtmidi.MidiOut(rtmidi.API_LINUX_ALSA).get_ports()) is not None
    except rtmidi.SystemError:
        return False


class Device:
    """One connection to the mixer. Thread-safe; replies are matched by sequence number."""

    def __init__(self, client_name: str = "agctl"):
        self._client_name = client_name
        self._out: rtmidi.MidiOut | None = None
        self._in: rtmidi.MidiIn | None = None
        self._seq = 0
        self._lock = threading.Lock()
        self._pending: dict[int, tuple[threading.Event, list]] = {}
        self.port_name: str | None = None
        self.model: str | None = None
        self.on_status: Callable[[p.Status], None] | None = None
        self.last_status: p.Status | None = None
        self._last_rx = 0.0

    # -- connection ---------------------------------------------------------
    @property
    def connected(self) -> bool:
        return self._out is not None

    def open(self) -> str:
        out = rtmidi.MidiOut(rtmidi.API_LINUX_ALSA, name=self._client_name)
        inp = rtmidi.MidiIn(rtmidi.API_LINUX_ALSA, name=self._client_name)
        oi, ii = find_port(out.get_ports()), find_port(inp.get_ports())
        if oi is None or ii is None:
            raise DeviceError("AG06MK2/AG03MK2 not found. Is it plugged in and switched on?")
        self.port_name = out.get_ports()[oi]
        out.open_port(oi, "control out")
        inp.open_port(ii, "control in")
        inp.ignore_types(sysex=False, timing=True, active_sense=False)
        inp.set_callback(self._on_midi)
        self._out, self._in = out, inp
        self._last_rx = time.monotonic()
        try:
            self.model = self.query_info(p.INFO_MODEL_NAME)
        except DeviceError:
            self.close()
            raise
        if not any(m in self.model for m in p.SUPPORTED_MODELS):
            name = self.model
            self.close()
            raise DeviceError(f"Unsupported device: {name}")
        return self.model

    def close(self) -> None:
        for port in (self._in, self._out):
            if port is not None:
                try:
                    port.close_port()
                except Exception:
                    pass
        self._in = self._out = None
        with self._lock:
            for ev, _ in self._pending.values():
                ev.set()
            self._pending.clear()

    def alive(self, timeout: float = 2.0) -> bool:
        """The mixer sends Active Sensing every ~300 ms; silence means it went away."""
        return self.connected and (time.monotonic() - self._last_rx) < timeout and is_present()

    # -- I/O ----------------------------------------------------------------
    def _on_midi(self, event, _data=None) -> None:
        raw, _delta = event
        self._last_rx = time.monotonic()
        msg = p.parse(raw)
        if msg is None:
            return
        if msg.cmd == p.CMD_METER_STATUS:
            try:
                st = p.parse_status(msg.data)
            except ValueError:
                return
            self.last_status = st
            if self.on_status:
                self.on_status(st)
            return
        if msg.is_reply:
            with self._lock:
                waiter = self._pending.pop(msg.seq, None)
            if waiter:
                waiter[1].append(msg)
                waiter[0].set()

    def request(self, cmd: int, payload=b"", timeout: float = 1.0) -> p.Message:
        if self._out is None:
            raise DeviceError("not connected")
        ev, box = threading.Event(), []
        with self._lock:
            seq = self._seq
            self._seq = (self._seq + 1) & 0x1FFF
            self._pending[seq] = (ev, box)
        self._out.send_message(p.build(cmd, seq, payload))
        if not ev.wait(timeout) or not box:
            with self._lock:
                self._pending.pop(seq, None)
            raise DeviceError(f"no reply to command 0x{cmd:04X}")
        reply = box[0]
        if reply.cmd != cmd | p.REPLY_FLAG:
            raise DeviceError(f"unexpected reply 0x{reply.cmd:04X} to 0x{cmd:04X}")
        return reply

    def _ack(self, cmd: int, payload) -> None:
        reply = self.request(cmd, payload)
        if reply.data[:1] not in (b"", b"\0"):
            raise DeviceError(f"mixer rejected command 0x{cmd:04X} (code {reply.data[0]})")

    # -- commands -----------------------------------------------------------
    def query_info(self, info_id: int) -> str:
        return p.parse_info_reply(self.request(p.CMD_GET_INFO, p.info_payload(info_id)).data)

    def set_switch(self, name: str, on: bool) -> None:
        self._ack(p.CMD_SWITCH, p.switch_payload(name, on))

    def set_footswitch(self, function: int) -> None:
        self._ack(p.CMD_FOOTSWITCH, p.footswitch_payload(function))

    def start_meters(self) -> None:
        self._ack(p.CMD_METER, [1])

    def stop_meters(self) -> None:
        self._ack(p.CMD_METER, [0])

    def read_status(self, timeout: float = 1.5) -> p.Status:
        """Start metering if needed and return the next status packet."""
        self.last_status = None
        self.start_meters()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.last_status is not None:
                return self.last_status
            time.sleep(0.01)
        raise DeviceError("no status from mixer")
