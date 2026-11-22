"""EQ/HPF and compressor words must equal Yamaha AG Controller output for the same scene."""
import json
from pathlib import Path

import pytest

from agctl.dsp import comp, eq

VEC = Path(__file__).parent / "vectors"


def _check(vectors, compute):
    bad = []
    for v in vectors:
        mine = {f"{w.address:#06x}": list(w.words) for w in compute(v["scene"])}
        for addr, words in v["writes"].items():
            if mine.get(addr) != words:
                bad.append((addr, words, mine.get(addr)))
    assert not bad, f"{len(bad)} mismatches, first: {bad[:3]}"


@pytest.mark.parametrize("group", ["eq", "comp"])
def test_vectors_bit_exact(group):
    vectors = json.loads((VEC / f"{group}.json").read_text())
    assert vectors
    mod = eq if group == "eq" else comp
    _check(vectors, lambda sc: [w for ch in (1, 2) for w in mod.scene_writes(sc, ch)])


def test_hpf_is_butterworth():
    assert abs(eq.HPF_Q - 0.7071067811865476) < 1e-15
