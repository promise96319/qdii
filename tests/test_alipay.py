import pathlib
from scripts.qdii.alipay import parse_alipay_status

FIX = pathlib.Path(__file__).parent / "fixtures"


def read(code):
    return (FIX / f"ant_{code}.html").read_text(encoding="utf-8")


def test_parse_normal():
    assert parse_alipay_status(read("270042")) == "正常申购"


def test_parse_not_for_sale():
    """I 类机构份额支付宝不代销。"""
    assert parse_alipay_status(read("021000")) == "不可售"


def test_returns_none_when_context_missing():
    """页面结构变化时降级为 None，不能抛异常。"""
    assert parse_alipay_status("<html><body>nothing here</body></html>") is None


def test_returns_none_on_malformed_json():
    assert parse_alipay_status("window.context = {broken json;</script>") is None


def test_returns_none_on_empty_input():
    assert parse_alipay_status("") is None
