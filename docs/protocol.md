# AG06MK2 / AG03MK2 control protocol

How the facts below were established:
- **Static:** [REA](https://github.com/morluto/rea) (reverse-engineering toolkit) with Ghidra 12.2, decompiling the macOS AG Controller v1.0.4 (`MacOS/AGController`,
  sha256 `add42239…a06a`). The binary keeps its C++ symbols (`RASCAL::SyncThread::*`, `_MIDI_*Rascal*`).
- **Captured:** the Windows AG Controller under Wine 10, with an ALSA-seq logging shim.
- **Live:** queries and switch writes sent from Linux to a real AG06MK2 (USB `0499:1757`).

This analysis was done only for interoperability. No Yamaha code or assets are part of this repository.

## Transport
USB-MIDI class interface. On Linux it appears as ALSA port "Yamaha AG06MK2 MIDI 1". The mixer sends
Active Sensing about every 300 ms.

## Framing (verified live)
```
F0 43 <dev> 3E 1C 78 00 | seqL seqH | cmdL cmdH | payload (8→7-bit packed, LSB first) | F7
```
- `dev`: 0x10 when `cmd & 0x1000`, otherwise 0x30. Replies use the other value.
- `seq`: a 13-bit counter split into 7-bit halves. Replies echo it.
- `cmd`: two raw bytes, low byte first. Reply = `cmd | 0x4000`. Ack payload `00` = OK.
- Packing: bits are accumulated LSB-first; each output byte carries 7 bits, and a final partial byte is emitted.

## Commands

| cmd | payload | meaning | status |
|-----|---------|---------|--------|
| 0x2F00 | `10 00 00 00` | get model name → reply `10 00 "Yamaha AG06MK2\0…"` | verified |
| 0x2006 | – | get 32-byte hash of the parameter memory | verified (reply seen) |
| 0x1040 | `01` / `00` | start / stop meter+status stream | verified |
| 0x1030 | `idx on` | hardware switch: 0 CH1 FX, 1 CH2 FX, 2 CH1 COMP/EQ, 3 CH2 AMP SIM | verified (idx 0) |
| 0x1050 | `10 fn` | foot switch function: 0 reverb on/off, 1 CH1 mute (MK2 only) | static only |
| 0x1000 | `addr:u16 n-1:u16 words:u16[n]` | raw DSP memory write (pan, levels, EQ, comp, reverb, amp sim) | **not implemented** |

### Meter/status stream (cmd 0x6041, unsolicited, about every 50 ms)
`[count][?][count × u16 LE meter words][?][status bits][?][foot switch fn]`
- Meter words: 0 CH1 in, 1 CH2 in, 2/3 comp gain-reduction sources, 4 CH1 out, 5 CH2 out, 6/7 FX L/R,
  8/9 master L/R, 10 AG01 only. dBFS = 20·log10(word/32767); negative means clip.
- Status bits: bit 0 CH1 FX, bit 1 CH2 FX, bit 2 CH1 COMP/EQ, bit 3 CH2 AMP SIM. These follow the
  hardware buttons.

## Not implemented: DSP writes (0x1000)
Pan, channel/effect levels, EQ, compressor, reverb and amp sim are written as DSP coefficients. The
original app computes them on the host (`Gain_GetDspValue`, `PanPot_GetLeftChlLevel`,
`Level_GetDspValue`, EQ/comp converter functions `FUN_100076b20`, `FUN_1000771a0`, …). It writes
them to DSP addresses taken from a table at `0x102b8b5f8`. Reimplementing them needs that maths to be
bit-exact. Wrong values can produce loud output, so this is left to Yamaha's editor for now (see the
Wine launcher).

Parameter IDs (from Qt metadata, `YQParamID`): 1 CH1 fxSend, 2 CH1 pan, 5 CH1 COMP on, 11 CH1 EQ on,
28 CH2 fxSend, 29 CH2 pan, 65 Effect out level, 66 CH2 AmpSimOn, 75 CH1 CompEqOn, 76/77 CH1/CH2
EffectSendOn, 78/79 CH1/CH2 OutputLevel, 80 Reverb DryWet, 81 FootSwitchFunction.
