"""Command-line control: agctl info | status | set <switch> on|off | footswitch <fn> | meters."""
from __future__ import annotations

import argparse
import math
import sys
import time

from . import __version__
from . import protocol as p
from . import state
from .device import Device, DeviceError
from .dsp import mixer
from .safety import SafetyError

SWITCH_ALIASES = {
    "fx1": "ch1_fx", "fx2": "ch2_fx", "compeq": "ch1_compeq", "ampsim": "ch2_ampsim",
    **{k: k for k in p.SWITCHES},
}
FOOT_ALIASES = {"reverb": 0, "ch1-mute": 1, "mute": 1, "0": 0, "1": 1}


def _fmt_db(v: float) -> str:
    return "  -inf" if v == -math.inf else f"{v:6.1f}"


def _print_status(st: p.Status) -> None:
    for name, (_, _, label) in p.SWITCHES.items():
        print(f"{label:28s} {'ON' if st.switches[name] else 'off'}")
    print(f"{'Foot switch function':28s} {p.FOOTSWITCH_FUNCTIONS.get(st.footswitch, st.footswitch)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agctl", description="Control a Yamaha AG06MK2/AG03MK2 from Linux.")
    ap.add_argument("--version", action="version", version=f"agctl {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info", help="show the connected model")
    sub.add_parser("status", help="show switch states and foot switch function")
    s = sub.add_parser("set", help="turn a switch on or off")
    s.add_argument("switch", choices=sorted(SWITCH_ALIASES))
    s.add_argument("state", choices=["on", "off"])
    f = sub.add_parser("footswitch", help="assign the foot switch")
    f.add_argument("function", choices=sorted(FOOT_ALIASES))
    m = sub.add_parser("meters", help="print live level meters (Ctrl+C to stop)")
    m.add_argument("--seconds", type=float, default=0, help="stop after N seconds (0 = until Ctrl+C)")
    d = sub.add_parser("dsp", help="DSP parameters (levels, pan, EQ, HPF, compressor)")
    dsub = d.add_subparsers(dest="dcmd", required=True)
    di = dsub.add_parser("import", help="import a scene (default: Yamaha AG Controller's saved scene)")
    di.add_argument("path", nargs="?")
    dg = dsub.add_parser("get", help="show scene values")
    dg.add_argument("column", nargs="?")
    ds = dsub.add_parser("set", help="change one value and send it to the mixer")
    ds.add_argument("column")
    ds.add_argument("value", type=float)
    dsub.add_parser("push", help="send all verified DSP values of the scene to the mixer")
    args = ap.parse_args(argv)

    if args.cmd == "dsp" and args.dcmd in ("import", "get"):
        return _dsp_offline(args)

    dev = Device("agctl-cli")
    try:
        model = dev.open()
        if args.cmd == "info":
            print(f"{model} on {dev.port_name}")
        elif args.cmd == "status":
            _print_status(dev.read_status())
        elif args.cmd == "set":
            dev.set_switch(SWITCH_ALIASES[args.switch], args.state == "on")
            _print_status(dev.read_status())
        elif args.cmd == "footswitch":
            dev.set_footswitch(FOOT_ALIASES[args.function])
            _print_status(dev.read_status())
        elif args.cmd == "dsp":
            sc = state.load()
            if sc is None:
                print("agctl: no scene yet; run 'agctl dsp import' first", file=sys.stderr)
                return 1
            if args.dcmd == "set":
                if args.column not in sc or args.column in ("Category", "ModelBitmap", ";Name"):
                    print(f"agctl: unknown parameter {args.column}", file=sys.stderr)
                    return 1
                sc[args.column] = args.value
                writes = mixer.writes_for(sc, args.column)
                if not writes:
                    print(f"agctl: {args.column} is not supported natively yet", file=sys.stderr)
                    return 1
            else:
                writes = mixer.all_verified_writes(sc)
            for w in writes:
                dev.write_dsp(w)
            state.save(sc)
            print(f"sent {len(writes)} DSP block(s)")
        elif args.cmd == "meters":
            dev.start_meters()
            names = ("ch1_in", "ch2_in", "ch1_out", "ch2_out", "fx_l", "fx_r", "master_l", "master_r")
            print(" ".join(f"{n:>8s}" for n in names))
            end = time.monotonic() + args.seconds if args.seconds else math.inf
            while time.monotonic() < end:
                st = dev.last_status
                if st:
                    print(" ".join(f"{_fmt_db(st.meters_db.get(n, -math.inf)):>8s}" for n in names), end="\r", flush=True)
                time.sleep(0.1)
            print()
    except (DeviceError, SafetyError) as e:
        print(f"agctl: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print()
    finally:
        dev.close()
    return 0


def _dsp_offline(args) -> int:
    try:
        if args.dcmd == "import":
            sc = state.import_scene(args.path)
            print(f"imported scene '{sc[';Name']}' -> {state.STATE}")
        else:
            sc = state.load()
            if sc is None:
                print("agctl: no scene yet; run 'agctl dsp import' first", file=sys.stderr)
                return 1
            for k, v in sc.items():
                if args.column is None or k == args.column:
                    print(f"{k:22s} {v}")
    except (FileNotFoundError, ValueError) as e:
        print(f"agctl: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
