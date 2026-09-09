"""蚂蚁基金页面 → 支付宝在售状态。

fund123.cn 服务端渲染，正文含 window.context = {...}。
注意 titleInfo.fundLimit 恒为 '0--'、fundBrief.purchaseRatio 恒为 '--'，
均为坏字段，不可使用；本模块只取 saleStatus。
"""
import json
import re

_CONTEXT_RE = re.compile(r"window\.context\s*=\s*(\{.*?\});?\s*</script>", re.S)


def parse_alipay_status(html):
    """返回 '正常申购'/'暂停销售'/'不可售'，无法解析返回 None。"""
    if not html:
        return None
    m = _CONTEXT_RE.search(html)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except (ValueError, TypeError):
        return None
    info = data.get("materialInfo") or {}
    brief = info.get("fundBrief") or {}
    status = brief.get("saleStatus")
    return status or None
