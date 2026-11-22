"""Byte-exact tests against traffic captured from the Windows AG Controller and a real AG06MK2."""
import math

from agctl import protocol as p


def hx(s):
    return [int(x, 16) for x in s.split()]


# Sent by the Windows AG Controller under Wine (seq 0, get model name).
CAPTURED_MODEL_QUERY = hx("F0 43 30 3E 1C 78 00 00 00 00 2F 10 00 00 00 00 F7")
# The mixer's reply to the same query.
CAPTURED_MODEL_REPLY = hx(
    "F0 43 10 3E 1C 78 00 00 00 00 6F 10 00 64 0A 56 2D 18 34 61 40 04 3A 04 46 4D 26 4B 64 00 00 00 F7")


def test_model_query_matches_windows_app():
    assert p.build(p.CMD_GET_INFO, 0, p.info_payload(p.INFO_MODEL_NAME)) == CAPTURED_MODEL_QUERY


def test_model_reply_parses():
    m = p.parse(CAPTURED_MODEL_REPLY)
    assert m.cmd == p.CMD_GET_INFO | p.REPLY_FLAG and m.is_reply and m.seq == 0
    assert p.parse_info_reply(m.data) == "Yamaha AG06MK2"


def test_switch_messages_match_live_test():
    # Verified live: these toggled CH1 FX and were acked with cmd 0x5030.
    assert p.build(p.CMD_SWITCH, 101, p.switch_payload("ch1_fx", False)) == hx(
        "F0 43 10 3E 1C 78 00 65 00 30 10 00 00 00 F7")
    assert p.build(p.CMD_METER, 5, [1]) == hx("F0 43 10 3E 1C 78 00 05 00 40 10 01 00 F7")


def test_seq_split_and_wrap():
    m = p.build(p.CMD_METER, 0x1FFF + 1 + 200, [0])
    assert m[7:9] == [200 & 0x7F, 200 >> 7]


def test_pack_roundtrip():
    data = bytes(range(256))
    assert p.unpack7(p.pack7(data)) == data
    assert all(b < 0x80 for b in p.pack7(data))


def test_status_parse():
    payload = bytes([0x0A, 0x01] + [0, 0, 0, 0, 0x29, 0x14, 0x6D, 0x19] + [0] * 12 + [0x10, 0x6E, 0x00, 0x01])
    st = p.parse_status(payload)
    assert st.switches == {"ch1_fx": False, "ch2_fx": True, "ch1_compeq": True, "ch2_ampsim": True}
    assert st.footswitch == 1
    assert st.meters_db["ch1_in"] == -math.inf
    assert round(st.meters_db["ch1_comp"], 1) == round(20 * math.log10(0x1429 / 32767), 1)


def test_parse_rejects_foreign_sysex():
    assert p.parse(hx("F0 7E 7F 06 01 F7")) is None
    built = p.build(0x6041, 3, bytes([0x0A, 0x01] + [0] * 24))
    m = p.parse(built)
    assert m.cmd == p.CMD_METER_STATUS and m.data[:2] == bytes([0x0A, 0x01])


def test_footswitch_payload():
    assert p.footswitch_payload(1) == [0x10, 1]
    try:
        p.footswitch_payload(5)
    except ValueError:
        pass
    else:
        raise AssertionError


def test_safety_accepts_verified_and_rejects_unknown():
    from agctl import safety
    from agctl.dsp import DspWrite
    safety.check(DspWrite(0x209, (3667,)))
    for bad in (DspWrite(0x257, (1, 2)), DspWrite(0x209, (1, 2)), DspWrite(0x28E, (0xFFFF, 0))):
        try:
            safety.check(bad)
        except safety.SafetyError:
            continue
        raise AssertionError(bad)
