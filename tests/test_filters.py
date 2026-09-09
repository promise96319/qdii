import pytest
from scripts.qdii.filters import (
    match_index, is_onexchange_etf, is_usd_share, share_class, build_pool,
)


@pytest.mark.parametrize("name,expected", [
    ("广发纳斯达克100ETF联接人民币(QDII)A", "NDX100"),
    ("广发纳指100ETF联接(QDII)人民币F", "NDX100"),
    ("博时标普500ETF联接A", "SP500"),
    ("大成标普500等权重指数(QDII)A人民币", "SP500"),
    ("易方达标普消费品指数A", None),
    ("华宝标普中国A股红利机会ETF联接A(LOF)", None),
    ("长信标普100等权重指数人民币", None),
    ("华夏中证500ETF联接A", None),
])
def test_match_index(name, expected):
    assert match_index(name) == expected


@pytest.mark.parametrize("code,expected", [
    ("159513", True), ("513500", True), ("159612", True),
    ("161130", False), ("161125", False), ("160213", False),
    ("270042", False), ("050025", False), ("018043", False),
])
def test_is_onexchange_etf_keeps_lof(code, expected):
    """16 开头是 LOF，场外可申购，必须保留——早期规则曾误杀 161130/161125/160213。"""
    assert is_onexchange_etf(code) == expected


@pytest.mark.parametrize("name,expected", [
    ("广发纳斯达克100ETF联接美元(QDII)A", True),
    ("摩根纳斯达克100指数(QDII)美元现汇A", True),
    ("华安纳斯达克100ETF联接(QDII)A美元现钞", True),
    ("易方达标普500指数美元汇A", True),
    ("广发纳斯达克100ETF联接人民币(QDII)A", False),
    ("天弘纳斯达克100指数发起(QDII)A", False),
])
def test_is_usd_share(name, expected):
    assert is_usd_share(name) == expected


@pytest.mark.parametrize("name,expected", [
    # 份额字母在末尾
    ("天弘纳斯达克100指数发起(QDII)A", "A"),
    ("天弘纳斯达克100指数发起(QDII)C", "C"),
    ("天弘纳斯达克100指数发起(QDII)D", "D"),
    ("汇添富纳斯达克100ETF发起式联接(QDII)人民币E", "E"),
    ("华泰柏瑞纳斯达克100ETF发起式联接(QDII)I", "I"),
    # 份额字母后还跟着币种后缀（计划最初的正则漏了这些真实格式）
    ("宝盈纳斯达克100指数发起(QDII)A人民币", "A"),
    ("大成标普500等权重指数(QDII)A人民币", "A"),
    ("建信纳斯达克100指数(QDII)C人民币", "C"),
    ("易方达纳斯达克100ETF联接(QDII-LOF)A(人民币)", "A"),
    ("华夏标普500ETF发起式联接(QDII)A(人民币)", "A"),
    # 无份额分级
    ("国泰纳斯达克100指数", "-"),
])
def test_share_class(name, expected):
    assert share_class(name) == expected


def test_build_pool_filters_and_annotates():
    rows = [
        ["270042", "GFNSDK100", "广发纳斯达克100ETF联接人民币(QDII)A", "指数型-海外股票", "x"],
        ["000055", "GFNSDK100MY", "广发纳斯达克100ETF联接美元(QDII)A", "指数型-海外股票", "x"],
        ["159513", "NSDK100ETFDC", "纳斯达克100ETF大成", "指数型-海外股票", "x"],
        ["161130", "YFDNSDK100", "易方达纳斯达克100ETF联接(QDII-LOF)A(人民币)", "指数型-海外股票", "x"],
        ["050025", "BSBP500", "博时标普500ETF联接A", "指数型-海外股票", "x"],
        ["110022", "YFDXFHY", "易方达消费行业股票", "股票型", "x"],
    ]
    pool = build_pool(rows)
    codes = [p["code"] for p in pool]
    assert "270042" in codes            # 人民币场外，保留
    assert "161130" in codes            # LOF，必须保留
    assert "050025" in codes            # 标普500 场外
    assert "000055" not in codes        # 美元份额，剔除
    assert "159513" not in codes        # 场内 ETF，剔除
    assert "110022" not in codes        # 非目标指数，剔除
    rec = next(p for p in pool if p["code"] == "161130")
    assert rec["index"] == "NDX100"
    assert rec["share_class"] == "A"


def test_build_pool_skips_malformed_rows():
    assert build_pool([["270042"], [], ["x", "y"]]) == []
