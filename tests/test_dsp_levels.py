"""Pan/level words must equal what Yamaha AG Controller sends for the same scene (oracle vectors)."""
import json
from pathlib import Path

from agctl.dsp import levels as L

VEC = json.loads((Path(__file__).parent / "vectors" / "levels.json").read_text())


def expected_for(scene):
    out = {}
    for name in ("Pan1", "Pan2"):
        w = L.pan_write(name, scene[name]); out[f"{w.address:#06x}"] = list(w.words)
    for name in ("FXSend1", "FXSend2", "Rev.OutputLevel", "Rev.Dry/Wet"):
        w = L.level_write(name, L.csv_db(scene[name], name)); out[f"{w.address:#06x}"] = list(w.words)
    for name in ("CH1.OutputLevel", "CH2.OutputLevel"):
        w = L.level_write(name, 0.0); out[f"{w.address:#06x}"] = list(w.words)
    return out


def test_vectors_present():
    assert len(VEC) >= 40


def test_levels_match_yamaha_app_bit_exact():
    bad = []
    for v in VEC:
        mine = expected_for(v["scene"])
        for addr, words in v["writes"].items():
            if mine.get(addr) != words:
                bad.append((v["scene"], addr, words, mine.get(addr)))
    assert not bad, f"{len(bad)} mismatches, first: {bad[:3]}"
