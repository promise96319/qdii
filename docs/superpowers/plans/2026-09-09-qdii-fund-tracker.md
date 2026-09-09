# QDII 基金限额费率查询页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建每日自动更新的静态网页，展示纳指100/标普500 场外基金当天的申购限额、状态与各项费率。

**Architecture:** GitHub Actions 每日定时运行 Python 脚本，抓取三个公开接口，产出 `data/latest.json` 与每日归档；根目录 `index.html` 为单文件静态页，fetch 该 JSON 渲染。抓取脚本按职责拆成纯函数模块（解析/过滤/排序/合并）与薄网络层，纯函数全部 TDD。

**Tech Stack:** Python 3.14（仅标准库 urllib/json/re）、pytest 9.1、原生 HTML/CSS/JS（无框架无构建）、GitHub Actions、GitHub Pages

**Spec:** `docs/superpowers/specs/2026-09-09-qdii-fund-tracker-design.md`

## Global Constraints

- Python 抓取脚本**只允许标准库**，不得引入任何第三方依赖（Actions 上不装包）
- 前端**无框架、无构建步骤**，单文件 `index.html`，不引外部 JS/CSS
- 所有数字（限额、费率、天数）在页面上必须使用等宽字体并设 `font-variant-numeric: tabular-nums`
- 亮暗双主题，默认跟随系统 `prefers-color-scheme`，手动切换存 localStorage
- 响应式断点 `768px`：以上表格，以下卡片流；移动端禁止横向滚动表格
- 状态不得仅依赖颜色表达，必须同时有文字标签
- 限额为空时展示 `—`，**禁止显示为 0**
- 基金池过滤：排除代码前缀 `15/51/52/56/58`，**16 开头的 LOF 必须保留**
- 暂停申购时不展示限额数字（`SGZT` 优先于 `MAXSG`）
- 提交信息使用中文，结尾附带：
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`

## File Structure

| 路径 | 职责 |
|---|---|
| `scripts/qdii/duration.py` | 中文持有期限文本 → 天数区间（纯函数） |
| `scripts/qdii/parse.py` | 接口响应 → 基金记录（纯函数） |
| `scripts/qdii/filters.py` | 基金池匹配与过滤规则（纯函数） |
| `scripts/qdii/sort.py` | 排序比较器（纯函数） |
| `scripts/qdii/merge.py` | 新旧数据合并、stale 标记、写入闸门（纯函数） |
| `scripts/qdii/fetch.py` | HTTP 网络层（薄，不做单元测试） |
| `scripts/build.py` | 主编排入口 |
| `tests/fixtures/*` | 真实接口响应样本 |
| `tests/test_*.py` | 单元测试 |
| `index.html` | 单文件静态页（根目录，供 Pages 直接托管） |
| `data/latest.json` | 最新快照 |
| `data/history/YYYY-MM-DD.json` | 每日归档 |
| `.github/workflows/update.yml` | 定时抓取工作流 |

---

### Task 1: 项目骨架 + 持有期限解析

**Files:**
- Create: `scripts/qdii/__init__.py`, `scripts/qdii/duration.py`, `tests/test_duration.py`, `pytest.ini`, `.gitignore`

**Interfaces:**
- Consumes: 无
- Produces:
  - `parse_duration_to_days(text: str) -> int | None` — 把「2年」「730天」「6个月」转成天数
  - `parse_time_range(text: str) -> tuple[int, int | None]` — 把赎回费档位的 `time` 文本转成 `(min_days, max_days)`，`max_days=None` 表示无上界

- [ ] **Step 1: 建立骨架文件**

```bash
mkdir -p scripts/qdii tests/fixtures data/history
touch scripts/qdii/__init__.py
printf '[pytest]\ntestpaths = tests\npythonpath = .\n' > pytest.ini
printf '__pycache__/\n*.pyc\n.pytest_cache/\n.DS_Store\n' > .gitignore
```

- [ ] **Step 2: 写失败测试**

创建 `tests/test_duration.py`：

```python
import pytest
from scripts.qdii.duration import parse_duration_to_days, parse_time_range


@pytest.mark.parametrize("text,expected", [
    ("7天", 7),
    ("30天", 30),
    ("365天", 365),
    ("730天", 730),
    ("1095天", 1095),
    ("1年", 365),
    ("2年", 730),
    ("3年", 1095),
    ("6个月", 180),
    ("1个月", 30),
])
def test_parse_duration_to_days(text, expected):
    assert parse_duration_to_days(text) == expected


def test_parse_duration_returns_none_for_unparseable():
    assert parse_duration_to_days("--") is None
    assert parse_duration_to_days("") is None


@pytest.mark.parametrize("text,expected", [
    ("持有期限 < 7天", (0, 7)),
    ("7天 ≤ 持有期限 < 1年", (7, 365)),
    ("1年 ≤ 持有期限 < 2年", (365, 730)),
    ("持有期限 ≥ 2年", (730, None)),
    ("持有期限 ≥ 730天", (730, None)),
    ("持有期限 ≥ 7天", (7, None)),
    ("持有期限 ≥ 1095天", (1095, None)),
])
def test_parse_time_range(text, expected):
    assert parse_time_range(text) == expected
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python3 -m pytest tests/test_duration.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.qdii.duration'`

- [ ] **Step 4: 实现**

创建 `scripts/qdii/duration.py`：

```python
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
    # 找出文本中出现的全部时长，按出现顺序
    parts = [
        int(float(v) * _UNIT_DAYS[u])
        for v, u in _DURATION_RE.findall(text)
    ]
    has_ge = "≥" in text or ">=" in text

    if not parts:
        return (0, None)

    # 「持有期限 ≥ X」形式：只有一个数字且带 ≥
    if len(parts) == 1:
        if has_ge:
            return (parts[0], None)
        # 「持有期限 < X」形式
        return (0, parts[0])

    # 「A ≤ 持有期限 < B」形式
    return (parts[0], parts[1])
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python3 -m pytest tests/test_duration.py -v`
Expected: PASS，19 passed

- [ ] **Step 6: 提交**

```bash
git add scripts tests pytest.ini .gitignore
git commit -m "feat: 添加持有期限文本解析

赎回费阶梯的 time 字段格式不统一（天/年/个月、≥/</≤ 混用），
统一解析为天数区间，为免赎回费天数计算提供基础。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: 费率与限额字段解析

**Files:**
- Create: `scripts/qdii/parse.py`, `tests/test_parse.py`, `tests/fixtures/rate_270042.json`, `tests/fixtures/rate_160213.json`, `tests/fixtures/rate_022525.json`, `tests/fixtures/rate_050025.json`

**Interfaces:**
- Consumes: `scripts.qdii.duration.parse_time_range`
- Produces:
  - `parse_percent(s) -> float` — `"0.80%"` → `0.8`，空/`--` → `0.0`
  - `parse_amount(s) -> float | None` — `"100"` → `100.0`，空/`--` → `None`
  - `parse_redeem_tiers(sh) -> list[dict]` — 每项 `{"min_days","max_days","rate"}`
  - `free_redeem_days(tiers) -> int | None` — 首个 `rate == 0` 档位的 `min_days`
  - `parse_buy_fee(sg) -> tuple[float | None, float | None]` — `(折后价, 原价)`
  - `parse_rate_info(datas) -> dict` — 汇总上述字段的部分记录

`confirm_days` 取 `SSBCFMDATA`（申购确认日）——定投关心买入何时确认份额。

- [ ] **Step 1: 抓取真实响应存为 fixture**

```bash
python3 - <<'EOF'
import urllib.request, json, ssl
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
UA = 'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/120 Mobile'
B = 'deviceid=1&plat=Android&product=EFund&version=6.5.5'
for code in ['270042', '160213', '022525', '050025']:
    u = f'https://fundmobapi.eastmoney.com/FundMApi/FundRateInfo.ashx?FCODE={code}&{B}'
    r = urllib.request.Request(u, headers={'User-Agent': UA})
    d = json.loads(urllib.request.urlopen(r, timeout=25, context=ctx).read().decode('utf-8'))
    with open(f'tests/fixtures/rate_{code}.json', 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print('saved', code, d['Datas']['SGZT'], 'MAXSG=', repr(d['Datas']['MAXSG']))
EOF
```

这四只覆盖关键边界：270042 正常、160213 销售服务费为空、022525 `MAXSG` 为空、050025 暂停但 `MAXSG` 仍有残值。

- [ ] **Step 2: 写失败测试**

创建 `tests/test_parse.py`：

```python
import json
import pathlib
import pytest
from scripts.qdii.parse import (
    parse_percent, parse_amount, parse_redeem_tiers,
    free_redeem_days, parse_buy_fee, parse_rate_info,
)

FIX = pathlib.Path(__file__).parent / "fixtures"


def load(code):
    with open(FIX / f"rate_{code}.json", encoding="utf-8") as f:
        return json.load(f)["Datas"]


@pytest.mark.parametrize("raw,expected", [
    ("0.80%", 0.8), ("0.20%", 0.2), ("1.50%", 1.5),
    ("0.00%", 0.0), ("", 0.0), ("--", 0.0), (None, 0.0),
])
def test_parse_percent(raw, expected):
    assert parse_percent(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("100", 100.0), ("5", 5.0), ("0.1", 0.1),
    ("", None), ("--", None), (None, None),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


def test_parse_redeem_tiers_270042():
    tiers = parse_redeem_tiers(load("270042")["sh"])
    assert tiers == [
        {"min_days": 0, "max_days": 7, "rate": 1.5},
        {"min_days": 7, "max_days": 365, "rate": 0.5},
        {"min_days": 365, "max_days": 730, "rate": 0.3},
        {"min_days": 730, "max_days": None, "rate": 0.0},
    ]


def test_free_redeem_days_270042():
    assert free_redeem_days(parse_redeem_tiers(load("270042")["sh"])) == 730


def test_free_redeem_days_returns_none_when_no_free_tier():
    assert free_redeem_days([{"min_days": 0, "max_days": None, "rate": 1.5}]) is None


def test_parse_buy_fee_returns_discounted_and_original():
    discounted, original = parse_buy_fee(load("270042")["sg"])
    assert discounted == 0.13
    assert original == 1.3


def test_parse_buy_fee_handles_empty():
    assert parse_buy_fee([]) == (None, None)


def test_sales_fee_empty_string_counts_as_zero():
    """160213 的 SALESEXP 为空字符串，年费求和时按 0 计。"""
    rec = parse_rate_info(load("160213"))
    assert rec["fee_sales"] == 0.0
    assert rec["fee_annual"] == pytest.approx(
        rec["fee_mgmt"] + rec["fee_trustee"] + rec["fee_sales"]
    )


def test_missing_max_buy_is_none_not_zero():
    """022525 的 MAXSG 为空，必须是 None，不能是 0（0 会被误读为不能买）。"""
    rec = parse_rate_info(load("022525"))
    assert rec["max_buy"] is None


def test_confirm_days_uses_subscription_field():
    """确认日取申购确认日 SSBCFMDATA，不是赎回确认日。"""
    raw = load("270042")
    rec = parse_rate_info(raw)
    assert rec["confirm_days"] == int(float(raw["SSBCFMDATA"]))


def test_suspended_fund_has_no_max_buy_even_if_field_present():
    """050025 状态为暂停申购但 MAXSG 仍有残值，以状态为准，不输出限额。"""
    raw = load("050025")
    assert raw["SGZT"] == "暂停申购"
    rec = parse_rate_info(raw)
    assert rec["status"] == "暂停申购"
    assert rec["max_buy"] is None
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python3 -m pytest tests/test_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.qdii.parse'`

- [ ] **Step 4: 实现**

创建 `scripts/qdii/parse.py`：

```python
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
    """'100' → 100.0；空值/'--' → None（None 与 0 语义不同，0 会被误读为不可买）"""
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
        "confirm_days": int(parse_amount(datas.get("SSBCFMDATA")) or 0) or None,
    }
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python3 -m pytest tests/test_parse.py -v`
Expected: PASS，全部通过

- [ ] **Step 6: 提交**

```bash
git add scripts/qdii/parse.py tests/test_parse.py tests/fixtures
git commit -m "feat: 添加费率与限额字段解析

处理三个实测数据坑：销售服务费为空字符串按 0 计入年费、
MAXSG 为空时返回 None 而非 0、暂停申购时忽略 MAXSG 残值。
fixture 取自四只覆盖各边界的真实基金响应。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: 基金池匹配与过滤

**Files:**
- Create: `scripts/qdii/filters.py`, `tests/test_filters.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `match_index(name: str) -> str | None` — 返回 `"NDX100"` / `"SP500"` / `None`
  - `is_onexchange_etf(code: str) -> bool`
  - `is_usd_share(name: str) -> bool`
  - `share_class(name: str) -> str` — 返回 `A`/`C`/`D`/`E`/`F`/`I`/`-`
  - `build_pool(rows: list[list[str]]) -> list[dict]` — 输入 fundcode_search 原始行，输出 `[{"code","name","index","share_class"}]`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_filters.py`：

```python
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
    ("天弘纳斯达克100指数发起(QDII)A", "A"),
    ("天弘纳斯达克100指数发起(QDII)C", "C"),
    ("天弘纳斯达克100指数发起(QDII)D", "D"),
    ("汇添富纳斯达克100ETF发起式联接(QDII)人民币E", "E"),
    ("华泰柏瑞纳斯达克100ETF发起式联接(QDII)I", "I"),
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_filters.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.qdii.filters'`

- [ ] **Step 3: 实现**

创建 `scripts/qdii/filters.py`：

```python
"""基金池匹配与过滤。

只保留纳指100 / 标普500 的人民币场外份额。
"""
import re

# 纯场内 ETF 代码前缀。16 开头是 LOF，场外可申购，不在此列。
_ONEXCHANGE_PREFIX = ("15", "51", "52", "56", "58")

_USD_RE = re.compile(r"美元|美汇|美钞|现汇|现钞")

_NDX_RE = re.compile(r"纳斯达克\s*100|纳指\s*100")
_SP500_RE = re.compile(r"标普\s*500")

_CLASS_RE = re.compile(r"([ACDEFI])(?:类)?\s*(?:份额)?\s*$")


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
    """从名称尾部提取份额类别，取不到返回 '-'。"""
    m = _CLASS_RE.search((name or "").strip())
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_filters.py -v`
Expected: PASS

- [ ] **Step 5: 用真实全量数据做一次冒烟校验**

```bash
python3 - <<'EOF'
import urllib.request, json, re, ssl
from scripts.qdii.filters import build_pool
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
UA = 'Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/120 Safari/537.36'
r = urllib.request.Request('https://fund.eastmoney.com/js/fundcode_search.js', headers={'User-Agent': UA})
s = urllib.request.urlopen(r, timeout=30, context=ctx).read().decode('utf-8', 'ignore')
rows = json.loads(re.search(r'=\s*(\[.*\]);?\s*$', s, re.S).group(1))
pool = build_pool(rows)
print('池大小:', len(pool))
for c in ['161130', '161125', '160213']:
    assert any(p['code'] == c for p in pool), f'LOF {c} 被误杀'
print('LOF 保留校验通过')
EOF
```

Expected: 池大小约 57，LOF 保留校验通过

- [ ] **Step 6: 提交**

```bash
git add scripts/qdii/filters.py tests/test_filters.py
git commit -m "feat: 添加基金池匹配与过滤规则

按名称匹配纳指100/标普500，排除纯场内 ETF 与美元份额。
16 开头的 LOF（161130/161125/160213）为场外可申购，
以回归用例锁定其不被误杀。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: 支付宝在售状态解析

**Files:**
- Create: `scripts/qdii/alipay.py`, `tests/test_alipay.py`, `tests/fixtures/ant_270042.html`, `tests/fixtures/ant_021000.html`

**Interfaces:**
- Consumes: 无
- Produces: `parse_alipay_status(html: str) -> str | None` — 返回 `"正常申购"` / `"暂停销售"` / `"不可售"`，解析失败返回 `None`

- [ ] **Step 1: 抓取真实页面存为 fixture**

```bash
python3 - <<'EOF'
import urllib.request, ssl
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36'
for code in ['270042', '021000']:
    r = urllib.request.Request(f'https://www.fund123.cn/matiaria?fundCode={code}', headers={'User-Agent': UA})
    h = urllib.request.urlopen(r, timeout=25, context=ctx).read().decode('utf-8', 'ignore')
    open(f'tests/fixtures/ant_{code}.html', 'w', encoding='utf-8').write(h)
    print('saved', code, len(h))
EOF
```

270042 为「正常申购」，021000（南方纳指100 I 类机构份额）为「不可售」。

- [ ] **Step 2: 写失败测试**

创建 `tests/test_alipay.py`：

```python
import pathlib
from scripts.qdii.alipay import parse_alipay_status

FIX = pathlib.Path(__file__).parent / "fixtures"


def read(code):
    return (FIX / f"ant_{code}.html").read_text(encoding="utf-8")


def test_parse_normal():
    assert parse_alipay_status(read("270042")) == "正常申购"


def test_parse_not_for_sale():
    """I 类机构份额支付宝不代销。"""
    assert parse_alipay_status(read("021000")) == "不可售"


def test_returns_none_when_context_missing():
    """页面结构变化时降级为 None，不能抛异常。"""
    assert parse_alipay_status("<html><body>nothing here</body></html>") is None


def test_returns_none_on_malformed_json():
    assert parse_alipay_status("window.context = {broken json;</script>") is None


def test_returns_none_on_empty_input():
    assert parse_alipay_status("") is None
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python3 -m pytest tests/test_alipay.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.qdii.alipay'`

- [ ] **Step 4: 实现**

创建 `scripts/qdii/alipay.py`：

```python
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
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python3 -m pytest tests/test_alipay.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add scripts/qdii/alipay.py tests/test_alipay.py tests/fixtures/ant_*.html
git commit -m "feat: 添加支付宝在售状态解析

从 fund123.cn 的 window.context 取 saleStatus，
区分正常申购/暂停销售/不可售。页面结构变化时降级为 None 不抛异常。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: 排序比较器

**Files:**
- Create: `scripts/qdii/sort.py`, `tests/test_sort.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `is_buyable(fund: dict) -> bool`
  - `sort_key(fund: dict) -> tuple` — 排序键
  - `sort_funds(funds: list[dict]) -> list[dict]` — 返回新列表，不修改入参

排序规则（spec §8.1）：可买优先 → 限额从高到低 → 同限额年费从低到高 → 代码升序（保证稳定）。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_sort.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_sort.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.qdii.sort'`

- [ ] **Step 3: 实现**

创建 `scripts/qdii/sort.py`：

```python
"""排序：可买优先 → 限额从高到低 → 年费从低到高 → 代码升序。"""

SUSPENDED = "暂停申购"


def is_buyable(fund):
    return (fund.get("status") or "") != SUSPENDED


def sort_key(fund):
    buyable = is_buyable(fund)
    max_buy = fund.get("max_buy")
    # 限额未披露排在有限额之后：给一个哨兵让它落到末尾
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_sort.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scripts/qdii/sort.py tests/test_sort.py
git commit -m "feat: 添加排序比较器

可买优先、限额从高到低、同限额比年费、代码升序保证稳定。
限额未披露的排在有限额之后但仍先于暂停申购的。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: 新旧数据合并与写入闸门

**Files:**
- Create: `scripts/qdii/merge.py`, `tests/test_merge.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `merge_with_previous(fresh: list[dict], previous: list[dict]) -> list[dict]` — `fresh` 中抓取失败的项（`None`）用 `previous` 的值补齐并置 `stale=True`
  - `success_rate(fresh: list) -> float`
  - `should_write(fresh: list, threshold: float = 0.8) -> bool`

容错语义（spec §7）：单只失败沿用旧值并标记；整体成功率低于阈值则拒绝写入。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_merge.py`：

```python
import pytest
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_merge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.qdii.merge'`

- [ ] **Step 3: 实现**

创建 `scripts/qdii/merge.py`：

```python
"""容错：单只失败沿用旧值并标记 stale；整体成功率过低则拒绝写入。

宁可展示带明确标记的旧数据，也不能把 latest.json 覆盖成空白。
"""

DEFAULT_THRESHOLD = 0.8


def merge_with_previous(fresh, previous, codes=None):
    """fresh 中为 None 的项用 previous 同代码记录补齐并标记 stale。

    codes 给出 fresh 每个位置对应的基金代码（fresh 项为 None 时无从得知代码）。
    既抓不到又无历史记录的直接丢弃。
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_merge.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scripts/qdii/merge.py tests/test_merge.py
git commit -m "feat: 添加新旧数据合并与写入闸门

单只抓取失败时沿用上次值并标记 stale，整体成功率低于 80%
拒绝写入以保留旧快照，避免一次网络抖动把页面清空。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: 网络层与主编排脚本

**Files:**
- Create: `scripts/qdii/fetch.py`, `scripts/build.py`

**Interfaces:**
- Consumes: `filters.build_pool`, `parse.parse_rate_info`, `alipay.parse_alipay_status`, `sort.sort_funds`, `merge.merge_with_previous`, `merge.should_write`
- Produces:
  - `fetch.http_get(url, referer=None, timeout=25) -> str | None`
  - `fetch.fetch_fund_rows() -> list[list[str]]`
  - `fetch.fetch_rate_info(code) -> dict | None`
  - `fetch.fetch_base_info(code) -> dict | None`
  - `fetch.fetch_alipay_html(code) -> str | None`
  - `build.main() -> int`（退出码：0 成功，1 成功率不足）

网络层为薄封装，不做单元测试（spec §11）；正确性由前面各任务的纯函数测试覆盖。

- [ ] **Step 1: 实现网络层**

创建 `scripts/qdii/fetch.py`：

```python
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
```

- [ ] **Step 2: 实现主编排脚本**

创建 `scripts/build.py`：

```python
#!/usr/bin/env python3
"""抓取纳指100/标普500 场外基金数据，产出 data/latest.json 与每日归档。

退出码 0 成功，1 表示抓取成功率不足、已保留旧快照。
"""
import datetime
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from scripts.qdii import fetch
from scripts.qdii.alipay import parse_alipay_status
from scripts.qdii.filters import build_pool
from scripts.qdii.merge import merge_with_previous, should_write, success_rate
from scripts.qdii.parse import parse_rate_info
from scripts.qdii.sort import sort_funds

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LATEST = DATA / "latest.json"
HISTORY = DATA / "history"
REQUEST_GAP = 0.2


def load_previous():
    if not LATEST.exists():
        return []
    try:
        with open(LATEST, encoding="utf-8") as f:
            return json.load(f).get("funds", [])
    except (ValueError, OSError):
        return []


def build_record(entry):
    """抓取单只基金的完整记录，失败返回 None。"""
    code = entry["code"]
    rate = fetch.fetch_rate_info(code)
    if not rate:
        return None
    record = {
        "code": code,
        "name": entry["name"],
        "index": entry["index"],
        "share_class": entry["share_class"],
    }
    record.update(parse_rate_info(rate))

    base = fetch.fetch_base_info(code)
    record["company"] = (base or {}).get("JJGS") or ""

    html = fetch.fetch_alipay_html(code)
    record["alipay"] = parse_alipay_status(html) if html else None
    return record


def main():
    rows = fetch.fetch_fund_rows()
    if not rows:
        print("ERROR: 基金列表抓取失败，中止", file=sys.stderr)
        return 1

    pool = build_pool(rows)
    print(f"候选基金池: {len(pool)} 只")

    fresh, codes = [], []
    for i, entry in enumerate(pool, 1):
        codes.append(entry["code"])
        fresh.append(build_record(entry))
        mark = "ok" if fresh[-1] else "FAIL"
        print(f"  [{i}/{len(pool)}] {entry['code']} {mark}")
        time.sleep(REQUEST_GAP)

    rate = success_rate(fresh)
    print(f"抓取成功率: {rate:.1%}")

    if not should_write(fresh):
        print("ERROR: 成功率低于 80%，保留旧快照不覆盖", file=sys.stderr)
        return 1

    funds = sort_funds(merge_with_previous(fresh, load_previous(), codes=codes))
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    payload = {
        "updated_at": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "source": "eastmoney + antfund",
        "count": len(funds),
        "funds": funds,
    }

    DATA.mkdir(parents=True, exist_ok=True)
    HISTORY.mkdir(parents=True, exist_ok=True)
    for path in (LATEST, HISTORY / f"{payload['date']}.json"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"已写入 {len(funds)} 只基金")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 首次真实运行**

Run: `python3 scripts/build.py`
Expected: 输出候选池约 57 只、逐只 ok、成功率 ≥ 95%、`已写入 NN 只基金`

- [ ] **Step 4: 校验产出**

```bash
python3 - <<'EOF'
import json
d = json.load(open('data/latest.json', encoding='utf-8'))
funds = d['funds']
print('总数', len(funds), '日期', d['date'])
buyable = [f for f in funds if f['status'] != '暂停申购']
print('可买', len(buyable), '暂停', len(funds) - len(buyable))
# 关键不变量
assert all(f.get('max_buy') != 0 for f in funds), '限额不得为 0'
assert all(f['max_buy'] is None for f in funds if f['status'] == '暂停申购'), '暂停不得有限额'
assert any(f['code'] == '161130' for f in funds), 'LOF 161130 缺失'
assert all(f['fee_annual'] is not None for f in funds), '年费缺失'
print('不变量校验通过')
print('前 5 名:')
for f in funds[:5]:
    print(f"  {f['code']} {f['name'][:22]:<24} 限额={f['max_buy']} 年费={f['fee_annual']}%")
EOF
```

Expected: 不变量校验通过，前 5 名按限额从高到低

- [ ] **Step 5: 提交**

```bash
git add scripts/qdii/fetch.py scripts/build.py data/
git commit -m "feat: 添加网络层与主编排脚本

串起基金池抓取、逐只取限额费率、支付宝状态标记、
排序与容错合并，产出 data/latest.json 与每日归档。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: 静态页面 — 结构、主题与 PC 表格

**Files:**
- Create: `index.html`

**Interfaces:**
- Consumes: `data/latest.json`
- Produces: 可在浏览器打开的完整页面（PC 表格视图 + 亮暗主题）

- [ ] **Step 1: 写页面骨架与主题变量**

创建 `index.html`，先写 `<head>` 与样式基座。配色严格取自 spec §8.5：

```html
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>纳指100 / 标普500 场外基金限额速查</title>
<style>
:root{
  --bg:#fafaf9; --surface:#ffffff; --text:#1c1e21; --muted:#6b7280;
  --line:#e5e7eb; --ok:#0f7b3f; --warn:#a16207; --off:#9ca3af;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#0f1115; --surface:#171a1f; --text:#e8e6e3; --muted:#9096a1;
    --line:#2a2f37; --ok:#3fbd6d; --warn:#d9a441; --off:#6b7280;
  }
}
:root[data-theme="dark"]{
  --bg:#0f1115; --surface:#171a1f; --text:#e8e6e3; --muted:#9096a1;
  --line:#2a2f37; --ok:#3fbd6d; --warn:#d9a441; --off:#6b7280;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif}
.wrap{max-width:1120px;margin:0 auto;padding:16px}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums}
header{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:12px}
h1{font-size:17px;margin:0;font-weight:600}
.meta{color:var(--muted);font-size:12px}
.summary{display:flex;gap:16px;margin:12px 0;font-size:13px}
.summary b{font-family:var(--mono);font-size:16px}
button{font:inherit;color:var(--text);background:var(--surface);
  border:1px solid var(--line);border-radius:4px;padding:4px 10px;cursor:pointer}
table{width:100%;border-collapse:collapse;background:var(--surface)}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line);
  height:36px;white-space:nowrap}
th{font-size:12px;color:var(--muted);font-weight:500;cursor:pointer;user-select:none}
th[aria-sort="ascending"]::after{content:" ▲"}
th[aria-sort="descending"]::after{content:" ▼"}
td.limit{font-family:var(--mono);font-variant-numeric:tabular-nums;
  font-size:16px;font-weight:600}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;
  margin-right:5px;vertical-align:middle}
.s-ok .dot{background:var(--ok)} .s-warn .dot{background:var(--warn)}
.s-off .dot{background:var(--off)}
.s-ok{color:var(--ok)} .s-warn{color:var(--warn)} .s-off{color:var(--off)}
tr.stale{opacity:.55}
.group-title{margin:24px 0 8px;font-size:14px;font-weight:600}
footer{margin:32px 0 16px;color:var(--muted);font-size:12px;line-height:1.7}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>纳指100 / 标普500 场外基金限额速查</h1>
    <span class="meta" id="meta"></span>
    <button id="theme" style="margin-left:auto" aria-label="切换主题">◐</button>
  </header>
  <div class="summary" id="summary"></div>
  <div id="content"></div>
  <footer>
    数据来源：天天基金（限额/费率）、蚂蚁基金（支付宝在售状态）。
    限额由基金公司公告设定，各代销渠道合并计算，同一代码在支付宝与微信共用额度；
    A/C 类为独立代码、独立额度。<br>
    申购费为天天基金折后价，支付宝折扣可能不同。
    <b>实际以下单页为准。</b>本页不构成投资建议。
  </footer>
</div>
<script>
/* Task 8 Step 2 起在此处填充 */
</script>
</body>
</html>
```

- [ ] **Step 2: 主题切换**

在 `<script>` 中加入（跟随系统 + 手动覆盖存 localStorage）：

```javascript
const themeBtn = document.getElementById('theme');
try {
  const saved = localStorage.getItem('theme');
  if (saved) document.documentElement.dataset.theme = saved;
} catch (e) {}
themeBtn.addEventListener('click', () => {
  const cur = document.documentElement.dataset.theme;
  const isDark = cur ? cur === 'dark'
    : matchMedia('(prefers-color-scheme: dark)').matches;
  const next = isDark ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('theme', next); } catch (e) {}
});
```

- [ ] **Step 3: 数据加载与格式化工具**

```javascript
const SUSPENDED = '暂停申购';
const fmtLimit = v => v == null ? '—' : (v >= 1 ? String(v) : v.toFixed(2));
const fmtPct = v => v == null ? '—' : v.toFixed(2) + '%';
const fmtDays = d => {
  if (d == null) return '无免费档';
  if (d % 365 === 0) return (d / 365) + '年';
  return d + '天';
};
const statusClass = f =>
  f.status === SUSPENDED ? 's-off' : (f.max_buy != null && f.max_buy < 100 ? 's-warn' : 's-ok');
const alipayLabel = a =>
  a === '正常申购' ? '有' : a === '暂停销售' ? '暂停' : a === '不可售' ? '无' : '—';

let STATE = { funds: [], sortKey: 'default', sortAsc: true };

async function load() {
  const res = await fetch('data/latest.json?t=' + Date.now());
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}
```

- [ ] **Step 4: 渲染表格与概览**

```javascript
const COLUMNS = [
  { key: 'code',             label: '代码'    },
  { key: 'name',             label: '名称'    },
  { key: 'max_buy',          label: '限额(元)' },
  { key: 'status',           label: '状态'    },
  { key: 'fee_annual',       label: '年费'    },
  { key: 'fee_buy',          label: '买入'    },
  { key: 'worst_redeem',     label: '卖出'    },
  { key: 'redeem_free_days', label: '免赎回费' },
  { key: 'alipay',           label: '支付宝'  },
];

const worstRedeem = f =>
  (f.redeem_tiers && f.redeem_tiers.length) ? f.redeem_tiers[0].rate : null;

function rowHtml(f) {
  const cls = statusClass(f);
  return `<tr class="${f.stale ? 'stale' : ''}">
    <td class="num">${f.code}</td>
    <td>${f.name}</td>
    <td class="limit">${f.status === SUSPENDED ? '—' : fmtLimit(f.max_buy)}</td>
    <td class="${cls}"><span class="dot"></span>${f.status || '—'}</td>
    <td class="num">${fmtPct(f.fee_annual)}</td>
    <td class="num">${fmtPct(f.fee_buy)}</td>
    <td class="num">${fmtPct(worstRedeem(f))}</td>
    <td class="num">${fmtDays(f.redeem_free_days)}</td>
    <td>${alipayLabel(f.alipay)}</td>
  </tr>`;
}

function tableHtml(list) {
  const head = COLUMNS.map(c =>
    `<th data-key="${c.key}" tabindex="0" role="button">${c.label}</th>`).join('');
  return `<table><thead><tr>${head}</tr></thead>
    <tbody>${list.map(rowHtml).join('')}</tbody></table>`;
}

function render() {
  const funds = STATE.funds;
  const buyable = funds.filter(f => f.status !== SUSPENDED);
  const paused = funds.filter(f => f.status === SUSPENDED);

  document.getElementById('summary').innerHTML =
    `<span>今日可买 <b class="s-ok">${buyable.length}</b> 只</span>
     <span>暂停 <b class="s-off">${paused.length}</b> 只</span>`;

  const groups = [
    ['纳斯达克 100', buyable.filter(f => f.index === 'NDX100')],
    ['标普 500',     buyable.filter(f => f.index === 'SP500')],
  ];
  let html = groups.map(([title, list]) => list.length
    ? `<h2 class="group-title">${title}（${list.length}）</h2>${tableHtml(list)}`
    : `<h2 class="group-title">${title}</h2><p class="meta">今日无可申购基金</p>`
  ).join('');

  html += `<details><summary class="group-title" style="cursor:pointer">
    已暂停申购（${paused.length}）</summary>${tableHtml(paused)}</details>`;
  document.getElementById('content').innerHTML = html;
  bindSort();
}
```

- [ ] **Step 5: 表头排序（含键盘可达）**

```javascript
function bindSort() {
  document.querySelectorAll('th[data-key]').forEach(th => {
    const act = () => {
      const key = th.dataset.key;
      STATE.sortAsc = STATE.sortKey === key ? !STATE.sortAsc : true;
      STATE.sortKey = key;
      const dir = STATE.sortAsc ? 1 : -1;
      const val = f => key === 'worst_redeem' ? worstRedeem(f) : f[key];
      STATE.funds.sort((a, b) => {
        const x = val(a), y = val(b);
        if (x == null && y == null) return 0;
        if (x == null) return 1;
        if (y == null) return -1;
        return (typeof x === 'number' ? x - y : String(x).localeCompare(String(y))) * dir;
      });
      render();
      document.querySelectorAll('th[data-key]').forEach(o =>
        o.removeAttribute('aria-sort'));
      th.setAttribute('aria-sort', STATE.sortAsc ? 'ascending' : 'descending');
    };
    th.addEventListener('click', act);
    th.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); act(); }
    });
  });
}

load().then(d => {
  STATE.funds = d.funds;
  const today = new Date().toISOString().slice(0, 10);
  const staleWarn = d.date !== today
    ? ` <b style="color:var(--warn)">数据来自 ${d.date}，非今日</b>` : '';
  document.getElementById('meta').innerHTML = `更新于 ${d.updated_at}${staleWarn}`;
  render();
}).catch(e => {
  document.getElementById('content').innerHTML =
    `<p class="meta">数据加载失败：${e.message}</p>`;
});
```

- [ ] **Step 6: 本地验证**

```bash
python3 -m http.server 8000 &
sleep 1
curl -s http://localhost:8000/index.html | head -3
curl -s -o /dev/null -w "latest.json: %{http_code}\n" http://localhost:8000/data/latest.json
```

在浏览器打开 `http://localhost:8000/`，确认：
- 表格显示两组，可买基金按限额从高到低
- 点击「年费」表头可排序，再点反向
- 系统切换深色时页面自动跟随；点右上角 ◐ 可手动覆盖并在刷新后保持
- 暂停申购的基金限额列显示 `—` 而非 0

验证完 `kill %1` 关闭服务。

- [ ] **Step 7: 提交**

```bash
git add index.html
git commit -m "feat: 添加静态页面与 PC 表格视图

亮暗双主题默认跟随系统、手动切换存 localStorage；
数字统一等宽字体加 tabular-nums 保证纵向可比；
表头可点击排序且支持键盘操作；暂停申购不显示限额数字。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: 移动端卡片视图与响应式

**Files:**
- Modify: `index.html`（新增媒体查询样式与卡片渲染分支）

**Interfaces:**
- Consumes: Task 8 的 `STATE`、`fmtLimit`、`fmtPct`、`fmtDays`、`statusClass`、`alipayLabel`、`worstRedeem`
- Produces: `cardHtml(f) -> string`、`isMobile() -> boolean`

设计约束（spec §8.3/§8.5）：卡片首屏只放限额、年费、状态三项；其余点开展开；一屏可见 5–6 张；**不得出现横向滚动表格**。

- [ ] **Step 1: 加入卡片样式与断点**

在 `<style>` 末尾追加：

```css
.cards{display:none}
.card{background:var(--surface);border:1px solid var(--line);border-radius:6px;
  padding:10px 12px;margin-bottom:8px}
.card summary{display:flex;align-items:center;gap:10px;cursor:pointer;
  list-style:none;outline-offset:2px}
.card summary::-webkit-details-marker{display:none}
.card .cname{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap;font-size:13px}
.card .ccode{font-family:var(--mono);font-size:11px;color:var(--muted)}
.card .climit{font-family:var(--mono);font-variant-numeric:tabular-nums;
  font-size:19px;font-weight:600;text-align:right;line-height:1.1}
.card .cfee{font-family:var(--mono);font-size:11px;color:var(--muted);text-align:right}
.card .detail{margin-top:10px;padding-top:10px;border-top:1px solid var(--line);
  display:grid;grid-template-columns:auto 1fr;gap:4px 14px;font-size:12px}
.card .detail dt{color:var(--muted)}
.card .detail dd{margin:0;font-family:var(--mono);
  font-variant-numeric:tabular-nums;text-align:right}
.card.stale{opacity:.55}

@media (max-width:768px){
  .wrap{padding:12px}
  h1{font-size:15px}
  table{display:none}
  .cards{display:block}
}
```

- [ ] **Step 2: 实现卡片渲染**

在 `<script>` 中 `tableHtml` 之后追加：

```javascript
const isMobile = () => matchMedia('(max-width:768px)').matches;

function cardHtml(f) {
  const cls = statusClass(f);
  const limit = f.status === SUSPENDED ? '—' : fmtLimit(f.max_buy);
  return `<details class="card ${f.stale ? 'stale' : ''}">
    <summary>
      <span style="flex:1;min-width:0">
        <span class="cname">${f.name}</span><br>
        <span class="ccode">${f.code}</span>
        <span class="${cls}" style="font-size:11px">
          <span class="dot"></span>${f.status || '—'}</span>
      </span>
      <span>
        <span class="climit">${limit}</span>
        <span class="cfee">年费 ${fmtPct(f.fee_annual)}</span>
      </span>
    </summary>
    <dl class="detail">
      <dt>买入费率</dt><dd>${fmtPct(f.fee_buy)}</dd>
      <dt>卖出费率(最短持有)</dt><dd>${fmtPct(worstRedeem(f))}</dd>
      <dt>免赎回费</dt><dd>${fmtDays(f.redeem_free_days)}</dd>
      <dt>管理/托管/销服</dt><dd>${fmtPct(f.fee_mgmt)} / ${fmtPct(f.fee_trustee)} / ${fmtPct(f.fee_sales)}</dd>
      <dt>买入确认</dt><dd>${f.confirm_days ? 'T+' + f.confirm_days : '—'}</dd>
      <dt>支付宝</dt><dd>${alipayLabel(f.alipay)}</dd>
    </dl>
  </details>`;
}

function listHtml(list) {
  return tableHtml(list) + `<div class="cards">${list.map(cardHtml).join('')}</div>`;
}
```

- [ ] **Step 3: 让 render 同时输出两种视图**

把 Task 8 中 `render()` 里三处 `tableHtml(` 调用改为 `listHtml(`：

```javascript
  let html = groups.map(([title, list]) => list.length
    ? `<h2 class="group-title">${title}（${list.length}）</h2>${listHtml(list)}`
    : `<h2 class="group-title">${title}</h2><p class="meta">今日无可申购基金</p>`
  ).join('');

  html += `<details><summary class="group-title" style="cursor:pointer">
    已暂停申购（${paused.length}）</summary>${listHtml(paused)}</details>`;
```

表格与卡片同时存在于 DOM，由 CSS 断点决定显示哪个——避免 resize 时需要重新渲染。

- [ ] **Step 4: 双端验证**

```bash
python3 -m http.server 8000 &
sleep 1
```

浏览器打开 `http://localhost:8000/`，逐项确认：
- 窗口宽度 > 768px：显示表格，无卡片
- 窗口宽度 < 768px（或开发者工具切到 iPhone 尺寸）：显示卡片，无表格，**页面无横向滚动条**
- 移动端一屏可见 5–6 张卡片
- 点击卡片展开详情，再点收起
- 深色模式下卡片边框与文字对比度正常

用真机验证移动端：手机与电脑同一 WiFi，访问 `http://<电脑内网IP>:8000/`。
内网 IP 用 `ipconfig getifaddr en0` 获取。

验证完 `kill %1`。

- [ ] **Step 5: 提交**

```bash
git add index.html
git commit -m "feat: 添加移动端卡片视图与响应式断点

768px 以下切换为卡片流，首屏只呈现限额/年费/状态三项核心信息，
其余点开展开。表格与卡片同时渲染由 CSS 控制显隐，
避免 resize 重绘。移动端不出现横向滚动。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: 定时工作流、说明文档与上线

**Files:**
- Create: `.github/workflows/update.yml`, `README.md`

**Interfaces:**
- Consumes: `scripts/build.py`
- Produces: 每日自动更新的线上页面

- [ ] **Step 1: 创建工作流**

创建 `.github/workflows/update.yml`：

```yaml
name: 更新基金数据

on:
  schedule:
    # 每天 01:30 UTC = 北京时间 09:30
    - cron: '30 1 * * *'
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: update-data
  cancel-in-progress: false

jobs:
  update:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: 运行单元测试
        run: python3 -m pytest tests -q

      - name: 抓取数据
        run: python3 scripts/build.py

      - name: 提交变更
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/
          if git diff --staged --quiet; then
            echo "数据无变化，跳过提交"
          else
            git commit -m "chore: 更新基金数据 $(date -u -d '+8 hours' +%Y-%m-%d)"
            git push
          fi
```

抓取脚本只用标准库，故无 `pip install` 步骤；测试先跑，抓取失败（退出码 1）会让工作流失败并告警。

- [ ] **Step 2: 本地验证工作流语法**

```bash
python3 -c "
import json,sys
try:
    import yaml
except ImportError:
    print('跳过：本地无 pyyaml，语法将由 GitHub 校验'); sys.exit()
d=yaml.safe_load(open('.github/workflows/update.yml'))
assert 'schedule' in d[True] or 'schedule' in d.get('on',{})
print('工作流 YAML 解析通过')
"
```

- [ ] **Step 3: 编写 README**

创建 `README.md`：

```markdown
# QDII 场外基金限额速查

每日自动更新纳斯达克 100 与标普 500 **场外**基金的申购限额、申购状态与各项费率。

解决的问题：QDII 基金因外汇额度紧张频繁限购或暂停申购，且限额逐日变动，
定投前无法预知当天实际能买多少。

## 数据说明

| 字段 | 来源 | 口径 |
|---|---|---|
| 限额、申购状态 | 天天基金 | 基金公司公告，各代销渠道统一 |
| 管理费 / 托管费 / 销售服务费 | 天天基金 | 从基金资产计提，全平台一致 |
| 申购费 | 天天基金 | **天天基金折后价**，支付宝折扣可能不同 |
| 赎回费与免费天数 | 天天基金 | 全平台一致 |
| 支付宝在售状态 | 蚂蚁基金 | 支付宝是否代销该基金 |

## 限额规则

限额按 **单日 × 单个基金账户 × 单只基金代码** 计算，**跨代销渠道合并计算**。

- 同一代码在支付宝与微信**共用**同一份额度
- 同一只基金的 A 类与 C 类是不同代码，**额度独立**
- 不同基金公司之间额度完全独立
- 基金公司直销渠道单独计额，额度通常更宽松

想加大投入应当**换代码**而非换平台。

## 本地运行

```bash
python3 -m pytest tests -q     # 单元测试
python3 scripts/build.py       # 抓取数据
python3 -m http.server 8000    # 打开 http://localhost:8000/
```

## 免责声明

数据来自公开接口，仅供参考，**实际以下单页面为准**。本页不构成投资建议。
```

- [ ] **Step 4: 跑全量测试确认绿**

Run: `python3 -m pytest tests -q`
Expected: 全部通过，无 failure

- [ ] **Step 5: 提交并推送**

```bash
git add .github README.md
git commit -m "chore: 添加定时工作流与说明文档

每日 01:30 UTC（北京 09:30）自动抓取，先跑测试再抓数据，
数据无变化时跳过提交。README 记录数据口径与限额规则。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push -u origin main
```

- [ ] **Step 6: 开启 GitHub Pages**

在仓库 Settings → Pages 中设置：
- Source: `Deploy from a branch`
- Branch: `main` / `/ (root)`

保存后等待约 1 分钟，访问 `https://promise96319.github.io/qdii/` 验证页面可正常加载数据。

- [ ] **Step 7: 手动触发一次工作流验证**

在仓库 Actions 页面选择「更新基金数据」→ Run workflow，确认：
- 测试步骤通过
- 抓取步骤输出成功率 ≥ 95%
- 数据有变化时产生一次 `chore: 更新基金数据` 提交

---

## Self-Review

**1. 规格覆盖检查**

| Spec 章节 | 对应任务 |
|---|---|
| §3.1 基金池接口 | Task 7 `fetch_fund_rows` |
| §3.2 限额费率接口 | Task 2 解析 + Task 7 抓取 |
| §3.3 支付宝状态 | Task 4 |
| §4 基金池过滤规则（含 LOF 保留） | Task 3（含回归用例） |
| §5 数据模型 | Task 2 `parse_rate_info` + Task 7 `build_record` |
| §6.1 免赎回费天数归一化 | Task 1 + Task 2 |
| §6.2 空值处理 | Task 2（`fee_sales` 空串、`max_buy` 为 None） |
| §6.3 状态与限额矛盾 | Task 2（`test_suspended_fund_has_no_max_buy...`） |
| §7 容错策略 | Task 6 + Task 7 |
| §8.1 排序 | Task 5 |
| §8.2 PC 表格（9 列含卖出费率） | Task 8 |
| §8.3 移动端卡片 | Task 9 |
| §8.4 概览与页脚免责 | Task 8 |
| §8.5 视觉规范（主题/等宽/密度/可访问性） | Task 8 + Task 9 |
| §10 架构与定时 | Task 10 |
| §11 测试策略 | Task 1–6 |

无遗漏。

**2. 占位符扫描**

已确认无 `TBD`/`TODO`/「适当处理」/「类似 Task N」等表述；所有代码步骤均含完整可运行代码块。

**3. 类型与命名一致性**

- `parse_rate_info` 产出的键（`status`/`max_buy`/`fee_annual`/`redeem_tiers`/`redeem_free_days`/`confirm_days`）与 Task 5 排序、Task 7 组装、Task 8/9 渲染中引用的键名逐一核对一致
- `merge_with_previous(fresh, previous, codes=None)` 的签名与 Task 7 调用处 `merge_with_previous(fresh, load_previous(), codes=codes)` 一致
- 前端 `worstRedeem`、`statusClass`、`alipayLabel`、`fmtLimit`、`fmtPct`、`fmtDays` 在 Task 8 定义、Task 9 复用，未出现改名
- `SUSPENDED` 常量在 Python（`parse.py`/`sort.py`）与 JS（`index.html`）中取值均为 `暂停申购`
