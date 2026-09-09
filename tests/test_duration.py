import pytest
from scripts.qdii.duration import parse_duration_to_days, parse_time_range


@pytest.mark.parametrize("text,expected", [
    ("7天", 7),
    ("30天", 30),
    ("365天", 365),
    ("730天", 730),
    ("1095天", 1095),
    ("1年", 365),
    ("2年", 730),
    ("3年", 1095),
    ("6个月", 180),
    ("1个月", 30),
])
def test_parse_duration_to_days(text, expected):
    assert parse_duration_to_days(text) == expected


def test_parse_duration_returns_none_for_unparseable():
    assert parse_duration_to_days("--") is None
    assert parse_duration_to_days("") is None


@pytest.mark.parametrize("text,expected", [
    ("持有期限 < 7天", (0, 7)),
    ("7天 ≤ 持有期限 < 1年", (7, 365)),
    ("1年 ≤ 持有期限 < 2年", (365, 730)),
    ("持有期限 ≥ 2年", (730, None)),
    ("持有期限 ≥ 730天", (730, None)),
    ("持有期限 ≥ 7天", (7, None)),
    ("持有期限 ≥ 1095天", (1095, None)),
])
def test_parse_time_range(text, expected):
    assert parse_time_range(text) == expected
