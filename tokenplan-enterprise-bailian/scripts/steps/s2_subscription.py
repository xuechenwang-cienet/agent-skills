"""s2 抓取订阅 / 席位 / 加油包状态（走接口，不解析页面文字）。"""
from __future__ import annotations

import json
import os

from lib.tokenplan_api import TokenPlanClient


def run(cfg, session, out_dir, log):
    log("─" * 68)
    log("s2 抓取订阅状态")
    raw_dir = os.path.join(out_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    client = TokenPlanClient(cfg, session, log=log)
    sub = client.fetch_subscription()

    for s in sub.get("seats", []):
        log(f"  · 席位 {s['type']:<9} {s['assigned']}/{s['total_seats']}  "
            f"已用 {s['used']:,.2f} / {s['cap']:,}")
    p = sub.get("pack") or {}
    log(f"  · 加油包 {p.get('count')} 个  已用 {p.get('used', 0):,.2f} / {p.get('cap', 0):,}"
        f"  剩余 {p.get('remaining', 0):,.2f}")

    path = os.path.join(raw_dir, "subscription.json")
    json.dump(sub, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"  ✓ {path}")
    return sub