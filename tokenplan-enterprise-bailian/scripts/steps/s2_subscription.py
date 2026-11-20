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
    unassigned = sum(max(0, (s.get("total_seats") or 0) - (s.get("assigned") or 0))
                     for s in sub.get("seats", []))
    log(f"  · 剩余未分配席位 {unassigned}")
    p = sub.get("pack") or {}
    log(f"  · 加油包 {p.get('count')} 个  已用 {p.get('used', 0):,.2f} / {p.get('cap', 0):,}"
        f"  剩余 {p.get('remaining', 0):,.2f}")

    path = os.path.join(raw_dir, "subscription.json")
    json.dump(sub, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"  ✓ {path}")

    # ---- 成员席位分配（成员管理页口径：谁有席位、本周期额度） ----
    try:
        mem = client.fetch_member_seats()
        seated = [m for m in mem["members"] if m["seat"]]
        log(f"  · 组织成员 {mem['total_members']} 人  已分配席位 {mem['seated_count']} 人"
            f"  未分配 {mem['total_members'] - mem['seated_count']} 人")
        specs = {}
        for m in seated:
            specs[m["seat"]["spec"]] = specs.get(m["seat"]["spec"], 0) + 1
        log(f"  · 席位规格分布 {specs or '{}'}")
        mpath = os.path.join(raw_dir, "organization_members.json")
        json.dump(mem, open(mpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        log(f"  ✓ {mpath}")
        sub["member_seats_file"] = os.path.basename(mpath)
        sub["seats_unassigned"] = unassigned
        json.dump(sub, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception as e:  # 席位分配抓取失败不阻塞：s3 回退全量口径并告警
        log(f"  ! 成员席位分配抓取失败（不影响订阅数据）：{e}")
    return sub