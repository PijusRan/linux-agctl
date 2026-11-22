# agctl: native Linux control for Yamaha AG06MK2 / AG03MK2

[![Reverse-engineered with REA](https://img.shields.io/badge/reverse--engineered%20with-REA-6f42c1)](https://github.com/morluto/rea)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Yamaha's AG Controller app only runs on Windows and macOS. **agctl** is an independent,
open-source controller for Linux. It talks to the mixer directly over its class-compliant USB-MIDI
port, so no driver is needed.

| Feature | Status |
|---|---|
| CH1 / CH2 effect (reverb) send on/off | ✅ stays in sync with the hardware buttons |
| CH1 COMP/EQ, CH2 AMP SIM on/off | ✅ stays in sync with the hardware buttons |
| Assignable foot switch (reverb / CH1 mute) | ⚠️ implemented, not yet tested on hardware |
| Live level meters (inputs, outputs, effect, main) | ✅ |
| EQ / compressor / reverb / amp-sim parameters, pan, levels | ❌ not yet; see [docs/protocol.md](docs/protocol.md) |

Tested with an AG06MK2 on Debian 13 (trixie). The AG03MK2 uses the same protocol, but it hasn't been tested yet.

## Install

### From a release `.deb` (Debian / Ubuntu)
```
sudo apt install ./agctl_0.1.0_all.deb
```

### Build the `.deb` yourself
```
sudo apt install debhelper dh-python pybuild-plugin-pyproject python3-all python3-setuptools \
                 python3-pytest python3-rtmidi python3-pyside6.qtwidgets
dpkg-buildpackage -us -uc -b        # -> ../agctl_0.1.0_all.deb
```

### Run from source
```
sudo apt install python3-rtmidi python3-pyside6.qtwidgets
python3 -m agctl.cli status
python3 -m agctl.gui.app
```

## Use
```
agctl info                  # model name
agctl status                # switch states + foot switch
agctl set fx1 off           # fx1 | fx2 | compeq | ampsim   on|off
agctl footswitch ch1-mute   # reverb | ch1-mute
agctl meters                # live meters (Ctrl+C)
agctl-gui                   # desktop app ("AG Mixer Control" in the menu)
```
Your user needs access to the ALSA sequencer. On desktop Debian/Ubuntu it already has this.

## Full EQ / compressor / reverb editing (optional, via Wine)
Until the DSP parameters are implemented natively, you can run Yamaha's own Windows editor under
Wine. Download **AG Controller for Windows** from Yamaha's website, then:
```
sudo apt install wine wine64
contrib/wine/install-ag-controller.sh ~/Downloads/Install_AG_Controller.exe
```
This installs it into its own Wine prefix under `~/.local/share/yamaha-ag-controller/` and adds an
"AG Controller" menu entry. agctl-gui shows a button that opens it. Both apps can run at the same time.

## How it works
The mixer is controlled with Yamaha SysEx messages over USB-MIDI. The framing, commands and the
meter/status stream are documented in [docs/protocol.md](docs/protocol.md). Run the tests with `pytest`.

The protocol was recovered with [REA](https://github.com/morluto/rea), using Ghidra as its decompiler,
and then verified against a real AG06MK2.

## Disclaimer
This project is not affiliated with, endorsed by or supported by Yamaha Corporation. "Yamaha",
"AG06" and "AG03" are trademarks of Yamaha Corporation. They're used here only to identify the
compatible hardware. The repository contains no Yamaha code, firmware or artwork. It sends only the
commands described in `docs/protocol.md`, and it is provided without warranty (see [LICENSE](LICENSE)).

## License
MIT. See [LICENSE](LICENSE).
