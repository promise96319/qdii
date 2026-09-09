"""排序：可买优先 → 限额从高到低 → 年费从低到高 → 代码升序。"""

SUSPENDED = "暂停申购"


def is_buyable(fund):
    return (fund.get("status") or "") != SUSPENDED


def sort_key(fund):
    buyable = is_buyable(fund)
    max_buy = fund.get("max_buy")
    # 限额未披露排在有限额之后：单独一个档位键，不与数值混用
    has_limit = max_buy is not None
    limit_desc = -(max_buy if has_limit else 0.0)
    fee = fund.get("fee_annual")
    fee = fee if fee is not None else 999.0
    return (
        0 if buyable else 1,
        0 if has_limit else 1,
        limit_desc,
        fee,
        str(fund.get("code") or ""),
    )


def sort_funds(funds):
    """返回排序后的新列表，不修改入参。"""
    return sorted(funds, key=sort_key)
