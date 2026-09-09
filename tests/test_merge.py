from scripts.qdii.merge import merge_with_previous, success_rate, should_write


def rec(code, max_buy=100.0):
    return {"code": code, "max_buy": max_buy, "status": "限大额"}


def test_fresh_records_are_not_stale():
    out = merge_with_previous([rec("a")], [])
    assert out[0]["stale"] is False


def test_failed_record_falls_back_to_previous_and_is_marked_stale():
    fresh = [None]
    previous = [rec("a", max_buy=50.0)]
    out = merge_with_previous(fresh, previous, codes=["a"])
    assert out[0]["max_buy"] == 50.0
    assert out[0]["stale"] is True


def test_failed_record_with_no_previous_is_dropped():
    """既抓不到又没有历史值，不能凭空造记录。"""
    out = merge_with_previous([None], [], codes=["a"])
    assert out == []


def test_success_rate():
    assert success_rate([rec("a"), None, rec("c"), rec("d")]) == 0.75
    assert success_rate([]) == 0.0
    assert success_rate([rec("a")]) == 1.0


def test_should_write_blocks_below_threshold():
    fresh = [rec("a")] + [None] * 4     # 20% 成功率
    assert should_write(fresh) is False


def test_should_write_allows_at_threshold():
    fresh = [rec(str(i)) for i in range(8)] + [None, None]   # 80%
    assert should_write(fresh) is True


def test_should_write_blocks_empty():
    assert should_write([]) is False
