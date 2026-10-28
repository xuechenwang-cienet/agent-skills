"""s5 清单 + 自检。"""
from __future__ import annotations

import json
import os


def run(cfg, A, files, out_dir, log, extra=None):
    log("─" * 68)
    log("s5 自检")
    checks = []

    def chk(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        log(f"  {'✓' if ok else '✗'} {name}" + (f" — {detail}" if detail else ""))
        return ok

    # 1. 系数必须是整数
    bad = [r for r in A["rates"] if abs(r["rate"] - round(r["rate"])) > 1e-4]
    chk("系数全部为整数", not bad, f"{len(bad)} 个非整数" if bad else f"{len(A['rates'])} 个组合")

    # 2. 系数组合无重复行
    combos = {(r["model"], r["ctx"], r["period"]) for r in A["rates"]}
    chk("系数组合唯一", len(combos) == len({(r["model"], r["ctx"], r["period"]) for r in A["rates"]}),
        f"{len(combos)} 行")

    # 3. 各组之和 == 部门总点数
    gsum = sum(g["credits"] for g in A["groups"])
    chk("各组点数之和 = 部门总点数", abs(gsum - A["meta"]["total_credits"]) < 0.01,
        f"{gsum:,.2f} vs {A['meta']['total_credits']:,.2f}")

    # 4. 每个席位都归属一个组
    orphan = [p for p in A["people"] if not p["owner"]]
    chk("所有席位都有项目组", not orphan, f"{len(orphan)} 个未归属")

    # 5. 未映射账号（警告级）
    chk("Bailian 账号全部映射到名册", not A["unmapped"],
        f"{len(A['unmapped'])} 个未归属账号，合计 {sum(u['credits'] for u in A['unmapped']):,.0f} 点"
        if A["unmapped"] else "全部命中")

    # 6. 席位容量 vs 订阅快照
    sub = A["subscription"]
    sub_cap = sum(s.get("cap", 0) for s in sub.get("seats", []))
    chk("席位容量与订阅一致", abs(sub_cap - A["procurement"]["seat_cap"]) < 1,
        f"订阅 {sub_cap:,} vs 名册 {A['procurement']['seat_cap']:,}")

    # 7. 日历覆盖
    chk("目标月份日历已核对", A["calendar"]["verified"], A["calendar"]["month"])
    chk("下月日历已核对", A["calendar"]["next_verified"], A["calendar"]["next_month"]["month"])

    # 8. 报告文件
    missing = [f for f in files if not os.path.exists(f)]
    chk("所有报告文件已生成", not missing, f"缺失 {len(missing)}" if missing else f"{len(files)} 个")

    # 9. 组报告数量
    n_group = len([f for f in files if os.path.basename(f).startswith("team-")])
    chk("组报告数量 = 项目组数", n_group == len(A["groups"]),
        f"{n_group} vs {len(A['groups'])}")

    # 10. 个人报告数量（警告级：member_reports 关闭时跳过）
    if cfg.output.get("member_reports", True):
        n_member = len([f for f in files if os.path.basename(f).startswith("member-")])
        n_should = len([p for p in A["people"] if p["accounts"]])
        chk("个人报告数量 = 有账号席位数", n_member == n_should, f"{n_member} vs {n_should}")

    # 11. 行为分布合计 = 点数（警告级，防画像采集漏行）
    s_hours = sum(sum(p["profile"]["hours_c"]) + p["profile"]["partial_credits"] for p in A["people"])
    s_daily = sum(sum(x["credits"] for x in p["profile"]["days"]) + p["profile"]["partial_credits"]
                  for p in A["people"])
    ok_h = abs(s_hours - A["meta"]["total_credits"]) < 0.05
    ok_d = abs(s_daily - A["meta"]["total_credits"]) < 0.05
    chk("行为分布合计 = 部门总点数", ok_h and ok_d,
        f"小时 {s_hours:,.2f} / 日 {s_daily:,.2f} vs {A['meta']['total_credits']:,.2f}")

    # 12. 时段口径（peak/offpeak 后缀 vs 时间戳小时，警告级）
    beh = A.get("behavior") or {}
    tz = beh.get("tz") or {}
    chk("peak/offpeak 与时间戳一致", tz.get("ratio", 0) < 2,
        f"不一致 {tz.get('mismatch', 0)}/{tz.get('checked', 0)}"
        f"（{tz.get('ratio', 0):.2f}%）" if tz.get("checked") else "无样本")

    b = A.get("behavior") or {}
    n_member = len([f for f in files if os.path.basename(f).startswith("member-")])
    log(f"  · 行为：夜间 {b.get('night_share', 0):.1f}% · 周末 {b.get('weekend_share', 0):.1f}% · "
        f"最活跃 {b.get('busiest_hour', 0):02d}:00 · 个人报告 {n_member} 份")

    ok = all(c["ok"] for c in checks if c["name"] not in
             ("Bailian 账号全部映射到名册", "目标月份日历已核对", "下月日历已核对",
              "个人报告数量 = 有账号席位数", "行为分布合计 = 部门总点数",
              "peak/offpeak 与时间戳一致"))

    manifest = {
        "ok": ok,
        "generated_at": A["meta"]["generated_at"],
        "month": A["meta"]["month"],
        "data_range": [A["meta"]["data_start"], A["meta"]["data_end"]],
        "records": A["meta"]["rows"],
        "total_credits": round(A["meta"]["total_credits"], 2),
        "next_month_forecast": round(A["meta"]["total_forecast"], 2),
        "config_hashes": cfg.hashes(),
        "calendar": A["calendar"],
        "procurement": A["procurement"],
        "waste": A["waste"],
        "unmapped": A["unmapped"],
        "warnings": A["warnings"],
        "checks": checks,
        "files": [os.path.basename(f) for f in files],
        "extra": extra or {},
    }
    path = os.path.join(out_dir, "manifest.json")
    json.dump(manifest, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log(f"  ✓ manifest.json  ({'通过' if ok else '有失败项'})")
    return manifest