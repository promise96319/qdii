"""基金池匹配与过滤。

只保留纳指100 / 标普500 的人民币场外份额。
"""
import re

# 纯场内 ETF 代码前缀。16 开头是 LOF，场外可申购，不在此列。
_ONEXCHANGE_PREFIX = ("15", "51", "52", "56", "58")

_USD_RE = re.compile(r"美元|美汇|美钞|现汇|现钞")

_NDX_RE = re.compile(r"纳斯达克\s*100|纳指\s*100")
_SP500_RE = re.compile(r"标普\s*500")

# 尾部币种后缀，可能带括号，可能连续出现：如「A人民币」「A(人民币)」
_CURRENCY_TAIL_RE = re.compile(
    r"[（(]?(?:人民币|美元现汇|美元现钞|美元|美汇|美钞|现汇|现钞)[）)]?\s*$"
)
_CLASS_RE = re.compile(r"([ACDEFI])\s*(?:类)?\s*(?:份额)?\s*$")


def match_index(name):
    """按名称判断跟踪哪个指数，非目标返回 None。"""
    if not name:
        return None
    if _NDX_RE.search(name):
        return "NDX100"
    if _SP500_RE.search(name):
        return "SP500"
    return None


def is_onexchange_etf(code):
    """纯场内 ETF（不可场外申购）。16 开头的 LOF 返回 False。"""
    return str(code).startswith(_ONEXCHANGE_PREFIX)


def is_usd_share(name):
    return bool(_USD_RE.search(name or ""))


def share_class(name):
    """从名称提取份额类别，取不到返回 '-'。

    份额字母可能在末尾（"(QDII)A"），也可能后跟币种后缀
    （"(QDII)A人民币"、"(QDII-LOF)A(人民币)"），故先剥离尾部币种再取字母。
    """
    text = (name or "").strip()
    while True:
        stripped = _CURRENCY_TAIL_RE.sub("", text).strip()
        if stripped == text:
            break
        text = stripped
    m = _CLASS_RE.search(text)
    return m.group(1) if m else "-"


def build_pool(rows):
    """fundcode_search 原始行 → 候选基金池。

    rows 每项形如 [代码, 拼音, 名称, 类型, 全拼]。
    """
    pool = []
    for row in rows:
        if len(row) < 3:
            continue
        code, name = row[0], row[2]
        idx = match_index(name)
        if idx is None:
            continue
        if is_onexchange_etf(code):
            continue
        if is_usd_share(name):
            continue
        pool.append({
            "code": code,
            "name": name,
            "index": idx,
            "share_class": share_class(name),
        })
    return pool
