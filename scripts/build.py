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
    print(f"已写入 {len(funds)} 只基金")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
