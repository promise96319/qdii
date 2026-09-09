"""HTTP 网络层。薄封装，失败返回 None 由调用方决定降级策略。"""
import json
import re
import ssl
import urllib.error
import urllib.request

UA_MOBILE = "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/120 Mobile"
UA_DESKTOP = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"

_EM_BASE = "deviceid=1&plat=Android&product=EFund&version=6.5.5"
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

_ROWS_RE = re.compile(r"=\s*(\[.*\]);?\s*$", re.S)


def http_get(url, referer=None, ua=UA_DESKTOP, timeout=25):
    headers = {"User-Agent": ua}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            return resp.read().decode("utf-8", "ignore")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def fetch_fund_rows():
    """全市场基金列表，失败返回空列表。"""
    body = http_get("https://fund.eastmoney.com/js/fundcode_search.js")
    if not body:
        return []
    m = _ROWS_RE.search(body)
    if not m:
        return []
    try:
        return json.loads(m.group(1))
    except ValueError:
        return []


def _em_api(path, code):
    url = f"https://fundmobapi.eastmoney.com/{path}?FCODE={code}&{_EM_BASE}"
    body = http_get(url, ua=UA_MOBILE)
    if not body:
        return None
    try:
        payload = json.loads(body)
    except ValueError:
        return None
    return payload.get("Datas") or None


def fetch_rate_info(code):
    return _em_api("FundMApi/FundRateInfo.ashx", code)


def fetch_base_info(code):
    return _em_api("FundMApi/FundBaseTypeInformation.ashx", code)


def fetch_alipay_html(code):
    return http_get(f"https://www.fund123.cn/matiaria?fundCode={code}")
