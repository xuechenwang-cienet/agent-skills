"""s3 分析：系数 / 逐人 / 分组 / 模型 / 预测 / 结余 / 采购。"""
from __future__ import annotations

import json
import os

from lib.calendar_cn import Calendar
from lib.model import build


def run(cfg, csv_path, subscription, month, out_dir, log):
    log("─" * 68)
    log(f"s3 分析  {os.path.basename(csv_path)}")

    cal = Calendar(cfg, month[0])
    A = build(cfg, csv_path, subscription, cal, month, log=log)

    meta = A["meta"]
    log(f"  · 明细 {meta['rows']:,} 行 · 模型 {meta['models']} 个 · 席位 {meta['members']} 个")
    log(f"  · 本月点数 {meta['total_credits']:,.2f}")
    log(f"  · 系数组合 {len(A['rates'])} 个（唯一行 {len({(r['model'], r['ctx'], r['period']) for r in A['rates']})} 行）")
    log(f"  · {A['calendar']['next_month']['month']} 预测 {meta['total_forecast']:,.0f} 点")
    log(f"  · 席位结余 {A['waste']['count']} 席 / ¥{A['waste']['total']:,.0f}")
    for w in A["warnings"]:
        log(f"  ⚠ {w}")

    path = os.path.join(out_dir, "data", "analysis.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(A, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log(f"  ✓ {path}")
    return A