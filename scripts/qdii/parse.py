"""东方财富 FundRateInfo 响应 → 结构化基金记录。"""
from .duration import parse_time_range

SUSPENDED = "暂停申购"


def parse_percent(s):
    """'0.80%' → 0.8；空值/'--' → 0.0"""
    if not s:
        return 0.0
    t = str(s).strip().rstrip("%").strip()
    if not t or t == "--":
        return 0.0
    try:
        return float(t)
    except ValueError:
        return 0.0


def parse_amount(s):
    """'100' → 100.0；空值/'--' → None

    None 与 0 语义不同：0 会被误读为「不能买」，未披露必须是 None。
    """
    if s is None:
        return None
    t = str(s).strip()
    if not t or t == "--":
        return None
    try:
        return float(t)
    except ValueError:
        return None


def parse_redeem_tiers(sh):
    """赎回费阶梯 → [{'min_days','max_days','rate'}]"""
    tiers = []
    for item in sh or []:
        lo, hi = parse_time_range(item.get("time", ""))
        tiers.append({
            "min_days": lo,
            "max_days": hi,
            "rate": parse_percent(item.get("rate")),
        })
    return tiers


def free_redeem_days(tiers):
    """首个 0 费率档位的 min_days；没有免费档返回 None。"""
    for t in tiers:
        if t["rate"] == 0.0:
            return t["min_days"]
    return None


def parse_buy_fee(sg):
    """申购费首档 → (折后价, 原价)。rate 是折后，source 是原价。

    最高档常为「1000元/笔」这类非百分比文案，只取首档（小额区间）即可。
    """
    if not sg:
        return (None, None)
    first = sg[0]
    rate_raw = str(first.get("rate") or "")
    src_raw = str(first.get("source") or "")
    discounted = parse_percent(rate_raw) if "%" in rate_raw else None
    original = parse_percent(src_raw) if "%" in src_raw else None
    return (discounted, original)


def parse_rate_info(datas):
    """FundRateInfo 的 Datas → 记录片段。"""
    status = (datas.get("SGZT") or "").strip()
    max_buy = parse_amount(datas.get("MAXSG"))
    # 状态优先于限额字段：暂停时残留的 MAXSG 不可信
    if status == SUSPENDED:
        max_buy = None

    fee_mgmt = parse_percent(datas.get("MGREXP"))
    fee_trustee = parse_percent(datas.get("TRUSTEXP"))
    fee_sales = parse_percent(datas.get("SALESEXP"))
    tiers = parse_redeem_tiers(datas.get("sh"))
    buy, buy_original = parse_buy_fee(datas.get("sg"))

    return {
        "status": status,
        "max_buy": max_buy,
        "min_buy": parse_amount(datas.get("MINSG")),
        "fee_mgmt": fee_mgmt,
        "fee_trustee": fee_trustee,
        "fee_sales": fee_sales,
        "fee_annual": round(fee_mgmt + fee_trustee + fee_sales, 4),
        "fee_buy": buy,
        "fee_buy_original": buy_original,
        "redeem_tiers": tiers,
        "redeem_free_days": free_redeem_days(tiers),
        # 申购确认日：定投关心买入何时确认份额
        "confirm_days": int(parse_amount(datas.get("SSBCFMDATA")) or 0) or None,
    }
