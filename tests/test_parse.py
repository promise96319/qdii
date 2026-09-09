import json
import pathlib
import pytest
from scripts.qdii.parse import (
    parse_percent, parse_amount, parse_redeem_tiers,
    free_redeem_days, parse_buy_fee, parse_rate_info,
)

FIX = pathlib.Path(__file__).parent / "fixtures"


def load(code):
    with open(FIX / f"rate_{code}.json", encoding="utf-8") as f:
        return json.load(f)["Datas"]


@pytest.mark.parametrize("raw,expected", [
    ("0.80%", 0.8), ("0.20%", 0.2), ("1.50%", 1.5),
    ("0.00%", 0.0), ("", 0.0), ("--", 0.0), (None, 0.0),
])
def test_parse_percent(raw, expected):
    assert parse_percent(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("100", 100.0), ("5", 5.0), ("0.1", 0.1),
    ("", None), ("--", None), (None, None),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


def test_parse_redeem_tiers_270042():
    tiers = parse_redeem_tiers(load("270042")["sh"])
    assert tiers == [
        {"min_days": 0, "max_days": 7, "rate": 1.5},
        {"min_days": 7, "max_days": 365, "rate": 0.5},
        {"min_days": 365, "max_days": 730, "rate": 0.3},
        {"min_days": 730, "max_days": None, "rate": 0.0},
    ]


def test_free_redeem_days_270042():
    assert free_redeem_days(parse_redeem_tiers(load("270042")["sh"])) == 730


def test_free_redeem_days_returns_none_when_no_free_tier():
    assert free_redeem_days([{"min_days": 0, "max_days": None, "rate": 1.5}]) is None


def test_parse_buy_fee_returns_discounted_and_original():
    discounted, original = parse_buy_fee(load("270042")["sg"])
    assert discounted == 0.13
    assert original == 1.3


def test_parse_buy_fee_handles_empty():
    assert parse_buy_fee([]) == (None, None)


def test_sales_fee_empty_string_counts_as_zero():
    """160213 的 SALESEXP 为空字符串，年费求和时按 0 计。"""
    rec = parse_rate_info(load("160213"))
    assert rec["fee_sales"] == 0.0
    assert rec["fee_annual"] == pytest.approx(
        rec["fee_mgmt"] + rec["fee_trustee"] + rec["fee_sales"]
    )


def test_missing_max_buy_is_none_not_zero():
    """022525 的 MAXSG 为空，必须是 None，不能是 0（0 会被误读为不能买）。"""
    rec = parse_rate_info(load("022525"))
    assert rec["max_buy"] is None


def test_confirm_days_uses_subscription_field():
    """确认日取申购确认日 SSBCFMDATA，不是赎回确认日。"""
    raw = load("270042")
    rec = parse_rate_info(raw)
    assert rec["confirm_days"] == int(float(raw["SSBCFMDATA"]))


def test_suspended_fund_has_no_max_buy_even_if_field_present():
    """050025 状态为暂停申购但 MAXSG 仍有残值，以状态为准，不输出限额。"""
    raw = load("050025")
    assert raw["SGZT"] == "暂停申购"
    assert raw["MAXSG"] == "100"
    rec = parse_rate_info(raw)
    assert rec["status"] == "暂停申购"
    assert rec["max_buy"] is None
