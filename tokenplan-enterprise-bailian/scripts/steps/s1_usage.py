"""s1 抓取全量用量明细。"""
from __future__ import annotations

import os

from lib.tokenplan_api import TokenPlanClient


def run(cfg, session, month, out_dir, log):
    y, m = month
    start = f"{y:04d}-{m:02d}-01 00:00:00"
    ny, nm = (y + (m == 12), (m % 12) + 1)
    end = f"{ny:04d}-{nm:02d}-01 00:00:00"
    log("─" * 68)
    log(f"s1 抓取用量明细  {start} ~ {end}")

    raw_dir = os.path.join(out_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    client = TokenPlanClient(cfg, session, log=log)
    log("  · 打开用量分析页并捕获 sec_token")
    client.open_usage()
    info = client.capture()
    log(f"    token={'✓' if info.get('token') else '✗'}  account={info.get('account') or '—'}")

    res = client.export_usage(start, end, raw_dir)
    n = res.get("records") or 0
    if n < int(cfg.export.get("min_records", 100)):
        raise RuntimeError(f"导出记录数异常偏低：{n}")
    res["start"], res["end"] = start, end
    log(f"  ✓ {res['file']}  {n:,} 行")
    return res