from scripts.qdii.sort import is_buyable, sort_funds


def f(code, status="限大额", max_buy=100.0, fee=0.6):
    return {"code": code, "status": status, "max_buy": max_buy, "fee_annual": fee}


def test_is_buyable():
    assert is_buyable(f("1", status="开放申购")) is True
    assert is_buyable(f("2", status="限大额")) is True
    assert is_buyable(f("3", status="暂停申购", max_buy=None)) is False


def test_buyable_funds_come_first():
    funds = [f("a", status="暂停申购", max_buy=None), f("b", status="限大额")]
    assert [x["code"] for x in sort_funds(funds)] == ["b", "a"]


def test_higher_limit_first():
    funds = [f("a", max_buy=5.0), f("b", max_buy=100.0), f("c", max_buy=10.0)]
    assert [x["code"] for x in sort_funds(funds)] == ["b", "c", "a"]


def test_same_limit_lower_fee_first():
    funds = [f("a", max_buy=100.0, fee=1.2), f("b", max_buy=100.0, fee=0.6)]
    assert [x["code"] for x in sort_funds(funds)] == ["b", "a"]


def test_null_limit_sorts_after_known_limits_among_buyable():
    """限额未披露的排在有限额的之后，但仍在暂停的之前。"""
    funds = [
        f("a", max_buy=None),
        f("b", max_buy=5.0),
        f("c", status="暂停申购", max_buy=None),
    ]
    assert [x["code"] for x in sort_funds(funds)] == ["b", "a", "c"]


def test_sort_is_stable_by_code():
    funds = [f("z", max_buy=10.0, fee=0.6), f("a", max_buy=10.0, fee=0.6)]
    assert [x["code"] for x in sort_funds(funds)] == ["a", "z"]


def test_sort_does_not_mutate_input():
    funds = [f("b", max_buy=5.0), f("a", max_buy=100.0)]
    original = list(funds)
    sort_funds(funds)
    assert funds == original
