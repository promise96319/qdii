#!/usr/bin/env python3
"""抓取纳指100/标普500 场外基金数据，产出 data/latest.json 与每日归档。

退出码 0 成功，1 表示抓取成功率不足、已保留旧快照。
"""
import datetime
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from scripts.qdii import fetch
from scripts.qdii.alipay import parse_alipay_status
from scripts.qdii.filters import build_pool
from scripts.qdii.merge import merge_with_previous, should_write, success_rate
from scripts.qdii.parse import SUSPENDED, parse_rate_info
from scripts.qdii.sort import sort_funds

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LATEST = DATA / "latest.json"
INDEX = ROOT / "index.html"
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


def _esc(text):
    return (str(text or "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render_seo_summary(funds, date):
    """渲染供搜索引擎抓取的静态摘要。

    页面数据由 JS 渲染，爬虫看不到内容，故在构建时把当日结果写进 HTML。
    该区块在 JS 加载完成后会被交互式表格替换，只在首屏和爬虫眼中出现。
    """
    buyable = [f for f in funds if f["status"] != SUSPENDED]
    paused = [f for f in funds if f["status"] == SUSPENDED]
    total = sum(f["max_buy"] or 0 for f in buyable)

    def fee(v):
        return "--" if v is None else f"{v:.2f}%"

    lines = ['<div class="seo-sum">']
    lines.append(
        f'<p class="lead">截至 {date}，纳斯达克100 与标普500 场外基金共 {len(funds)} 只，'
        f'其中 <strong>{len(buyable)} 只今日可申购</strong>、{len(paused)} 只暂停申购，'
        f'可申购基金单日限额合计约 {total:,.0f} 元。</p>'
    )
    for title, key in (("纳斯达克 100", "NDX100"), ("标普 500", "SP500")):
        group = [f for f in buyable if f["index"] == key]
        if not group:
            lines.append(f"<h2>{title}</h2><p>今日无可申购基金。</p>")
            continue
        lines.append(f"<h2>{title}（{len(group)} 只可申购）</h2><ul>")
        for f in group:
            limit = "未披露" if f["max_buy"] is None else f'{f["max_buy"]:,.0f} 元'
            lines.append(
                f'<li>{_esc(f["name"])}（{_esc(f["code"])}）'
                f'单日限额 {limit}，年费 {fee(f.get("fee_annual"))}，'
                f'买入费率 {fee(f.get("fee_buy"))}</li>'
            )
        lines.append("</ul>")
    if paused:
        names = "、".join(f'{_esc(f["name"])}（{_esc(f["code"])}）' for f in paused[:10])
        more = f" 等 {len(paused)} 只" if len(paused) > 10 else ""
        lines.append(f"<h2>今日暂停申购</h2><p>{names}{more}。</p>")
    lines.append("</div>")
    return "".join(lines)


def inject_seo(funds, date):
    """把摘要写入 index.html 的标记区，失败不影响数据产出。"""
    if not INDEX.exists():
        return False
    try:
        html = INDEX.read_text(encoding="utf-8")
    except OSError:
        return False
    start, end = "<!--SEO:START-->", "<!--SEO:END-->"
    if start not in html or end not in html:
        print("WARN: index.html 缺少 SEO 标记区，跳过注入", file=sys.stderr)
        return False
    head, rest = html.split(start, 1)
    _, tail = rest.split(end, 1)
    INDEX.write_text(
        head + start + render_seo_summary(funds, date) + end + tail,
        encoding="utf-8",
    )
    return True


def main():
    rows = fetch.fetch_fund_rows()
    if not rows:
        print("ERROR: 基金列表抓取失败，中止", file=sys.stderr)
        return 1

    pool = build_pool(rows)
    print(f"候选基金池: {len(pool)} 只", flush=True)

    fresh, codes = [], []
    for i, entry in enumerate(pool, 1):
        codes.append(entry["code"])
        fresh.append(build_record(entry))
        mark = "ok" if fresh[-1] else "FAIL"
        print(f"  [{i}/{len(pool)}] {entry['code']} {mark}", flush=True)
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
    if inject_seo(funds, payload["date"]):
        print("已注入 SEO 摘要到 index.html")
    print(f"已写入 {len(funds)} 只基金")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
