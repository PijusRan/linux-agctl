"""Scene (full mixer state) in the same CSV layout the Yamaha AG Controller uses.

A scene file has a header row (first column ``;Name``) and one data row. Numeric values are
written with three decimals. Keeping the exact format lets agctl import/export scenes that the
Yamaha app reads, so both apps can share the mixer's state.
"""
from __future__ import annotations

import csv
import io
from collections import OrderedDict
from pathlib import Path

TEXT_COLUMNS = (";Name", "Category", "ModelBitmap")

# Column order as written by AG Controller v1.0.4.
COLUMNS = (
    ";Name", "Amp.Bass", "Amp.Gain", "Amp.High", "Amp.Master", "Amp.Middle", "Amp.On",
    "Amp.OutputLevel", "Amp.Presence", "Amp.Treble", "Category", "Comp1.Attack", "Comp1.Gain",
    "Comp1.On", "Comp1.Ratio", "Comp1.Release", "Comp1.Threshold", "Comp2.Attack", "Comp2.Gain",
    "Comp2.On", "Comp2.Ratio", "Comp2.Release", "Comp2.Threshold", "CompEQ.On", "EQ1.High.Freq",
    "EQ1.High.Gain", "EQ1.High.Q", "EQ1.High.Type", "EQ1.Low.Freq", "EQ1.Low.Gain", "EQ1.Low.Q",
    "EQ1.Low.Type", "EQ1.MidHigh.Freq", "EQ1.MidHigh.Gain", "EQ1.MidHigh.Q", "EQ1.MidHigh.Type",
    "EQ1.MidLow.Freq", "EQ1.MidLow.Gain", "EQ1.MidLow.Q", "EQ1.MidLow.Type", "EQ1.On",
    "EQ2.High.Freq", "EQ2.High.Gain", "EQ2.High.Q", "EQ2.High.Type", "EQ2.Low.Freq", "EQ2.Low.Gain",
    "EQ2.Low.Q", "EQ2.Low.Type", "EQ2.MidHigh.Freq", "EQ2.MidHigh.Gain", "EQ2.MidHigh.Q",
    "EQ2.MidHigh.Type", "EQ2.MidLow.Freq", "EQ2.MidLow.Gain", "EQ2.MidLow.Q", "EQ2.MidLow.Type",
    "EQ2.On", "Effect1.On", "Effect2.On", "FXSend1", "FXSend2", "HPF1.Frequency", "HPF1.On",
    "HPF2.Frequency", "HPF2.On", "ModelBitmap", "Pan1", "Pan2", "Rev.Density", "Rev.Diffusion",
    "Rev.Dry/Wet", "Rev.E/R balance", "Rev.F/B Level", "Rev.HPF CUT", "Rev.HighDump",
    "Rev.InitialDelay", "Rev.LPF CUT", "Rev.OutputLevel", "Rev.RevDelay", "Rev.RevTime",
)


class Scene(OrderedDict):
    """Mapping column -> float (or str for text columns)."""

    @classmethod
    def from_csv_text(cls, text: str) -> "Scene":
        rows = [r for r in csv.reader(io.StringIO(text)) if r]
        if len(rows) < 2 or not rows[0] or rows[0][0] != ";Name":
            raise ValueError("not an AG Controller scene file")
        sc = cls()
        for k, v in zip(rows[0], rows[1]):
            sc[k] = v if k in TEXT_COLUMNS else float(v)
        return sc

    @classmethod
    def load(cls, path: str | Path) -> "Scene":
        return cls.from_csv_text(Path(path).read_text(encoding="utf-8-sig"))

    def to_csv_text(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(list(self.keys()))
        w.writerow([v if k in TEXT_COLUMNS else f"{float(v):.3f}" for k, v in self.items()])
        return buf.getvalue()

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(self.to_csv_text(), encoding="utf-8")
        tmp.replace(p)

    def copy(self) -> "Scene":
        return Scene(self)
