"""中文持有期限文本 → 天数。

赎回费阶梯的 time 字段格式不统一，实测出现过：
「持有期限 < 7天」「7天 ≤ 持有期限 < 1年」「持有期限 ≥ 2年」「持有期限 ≥ 1095天」
"""
import re

_UNIT_DAYS = {"天": 1, "日": 1, "个月": 30, "月": 30, "年": 365}

_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(个月|天|日|月|年)")


def parse_duration_to_days(text):
    """把单个时长文本转成天数，无法解析返回 None。"""
    if not text:
        return None
    m = _DURATION_RE.search(text)
    if not m:
        return None
    value, unit = m.group(1), m.group(2)
    return int(float(value) * _UNIT_DAYS[unit])


def parse_time_range(text):
    """把赎回费档位的 time 文本转成 (min_days, max_days)。

    max_days 为 None 表示无上界。区间语义左闭右开：min_days <= 持有天数 < max_days。
    """
    if not text:
        return (0, None)
    parts = [
        int(float(v) * _UNIT_DAYS[u])
        for v, u in _DURATION_RE.findall(text)
    ]
    has_ge = "≥" in text or ">=" in text

    if not parts:
        return (0, None)

    # 「持有期限 ≥ X」只有一个数字且带 ≥；「持有期限 < X」只有一个数字不带 ≥
    if len(parts) == 1:
        return (parts[0], None) if has_ge else (0, parts[0])

    # 「A ≤ 持有期限 < B」
    return (parts[0], parts[1])
