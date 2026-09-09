"""容错：单只失败沿用旧值并标记 stale；整体成功率过低则拒绝写入。

宁可展示带明确标记的旧数据，也不能把 latest.json 覆盖成空白。
"""

DEFAULT_THRESHOLD = 0.8


def merge_with_previous(fresh, previous, codes=None):
    """fresh 中为 None 的项用 previous 同代码记录补齐并标记 stale。

    codes 给出 fresh 每个位置对应的基金代码（fresh 项为 None 时无从得知代码）。
    既抓不到又无历史记录的直接丢弃，不凭空造数据。
    """
    prev_by_code = {p.get("code"): p for p in (previous or []) if p.get("code")}
    out = []
    for i, item in enumerate(fresh):
        if item is not None:
            merged = dict(item)
            merged["stale"] = False
            out.append(merged)
            continue
        code = codes[i] if codes and i < len(codes) else None
        old = prev_by_code.get(code)
        if old is None:
            continue
        merged = dict(old)
        merged["stale"] = True
        out.append(merged)
    return out


def success_rate(fresh):
    if not fresh:
        return 0.0
    return sum(1 for x in fresh if x is not None) / len(fresh)


def should_write(fresh, threshold=DEFAULT_THRESHOLD):
    """成功率达标才允许覆盖 latest.json。"""
    if not fresh:
        return False
    return success_rate(fresh) >= threshold
