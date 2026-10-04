"""W71-09 ADIF 解析/生成测试。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from adif import generate_adif, parse_adif


def test_round_trip():
    recs = [
        {"CALL": "BG5GXO", "BAND": "20m", "MODE": "SSB", "QSO_DATE": "20260902", "RST_SENT": "59"},
        {"CALL": "BG8LNG", "BAND": "40m", "MODE": "CW", "FREQ": "7.023"},
    ]
    text = generate_adif(recs)
    parsed = parse_adif(text)
    assert parsed == recs


def test_parse_empty_and_partial():
    assert parse_adif("") == []
    # 无 EOR 结尾的尾部字段也应保留（容错）
    assert parse_adif("<CALL:6>BG5GXO") == [{"CALL": "BG5GXO"}]


def test_field_name_uppercased():
    text = "<call:6>BG5GXO<EOR>"
    assert parse_adif(text)[0] == {"CALL": "BG5GXO"}


def test_generate_has_eor_and_length():
    text = generate_adif([{"CALL": "BG5GXO"}])
    assert "<CALL:6>BG5GXO" in text
    assert "<EOR>" in text
