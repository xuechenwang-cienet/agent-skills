"""s0 预检：环境、依赖、配置、五项确认、名册与日历的一致性。"""
from __future__ import annotations

import os
import shutil
import sys

from lib import bsk
from lib.config import KEY_LABEL

# 个人控制台（尚未支持）的停止提示
PERSONAL_UNSUPPORTED = [
    "  ✗ 个人控制台（personal）的采集流程尚未实现，本 skill 目前只支持企业版组织门户：",
    "      企业版  https://tokenplan-enterprise.bailian.aliyunportal.com   ← 已实现",
    "      个人版  https://bailian.console.aliyun.com                      ← 尚未支持",
    "    请把 config/config.yaml 的 web.console_type 改回 enterprise 后重跑；",
    "    如确需采集个人控制台，请先确认其采集模型（单账号 / 多账号聚合）再扩展本 skill。",
]


def _roster_summary(cfg):
    members = cfg.members
    accounts = sum(len(m.accounts) for m in members)
    groups = {}
    for m in members:
        groups.setdefault(m.team_owner, []).append(m)
    no_acc = [m for m in members if not m.accounts]
    no_mail = [m for m in members if not m.email]
    shared = [m for m in members if m.sharing_with]
    dup = {}
    for m in members:
        for a in m.accounts:
            dup.setdefault(a, []).append(m.name_zh)
    dup = {k: v for k, v in dup.items() if len(v) > 1}
    return dict(members=len(members), accounts=accounts, groups=groups,
                no_acc=no_acc, no_mail=no_mail, shared=shared, dup=dup)


def run(cfg, args, log):
    issues, fatal = [], []
    log("─" * 68)
    log("s0 预检")

    # ---- 数据来源（最先判定：个人版未实现，直接停，不做后续检查） ----
    ctype = cfg.console_type
    if ctype == "personal":
        log("  · 数据来源：personal（个人控制台）")
        for line in PERSONAL_UNSUPPORTED:
            log(line)
        return {"ok": False, "exit": 2, "fatal": ["数据来源为个人控制台，尚未支持"], "issues": []}
    if ctype != "enterprise":
        fatal.append(f"web.console_type 只能是 enterprise / personal，当前是 {ctype!r}")
        for f_ in fatal:
            log(f"  ✗ {f_}")
        return {"ok": False, "fatal": fatal, "issues": []}
    log("  · 数据来源：enterprise（企业版组织门户）")

    # ---- 依赖 ----
    log("  · 检查依赖")
    if sys.version_info < (3, 11):
        fatal.append(f"Python 版本过低：{sys.version.split()[0]}（需要 ≥3.11）")
    try:
        import yaml  # noqa
    except ImportError:
        fatal.append("缺少 PyYAML：uv pip install pyyaml")
    if not shutil.which("bsk"):
        fatal.append("找不到 bsk 命令（browser-skill CLI）")
    else:
        ok, msg = bsk.browser_connected()
        log(f"    bsk: {msg}")
        if not ok:
            fatal.append("浏览器未连接：请在 Chrome 中确认 browser-skill 扩展已连接")

    # ---- 页面可达 + org 校验 ----
    log("  · 校验 Web root / Org ID")
    log(f"    root  : {cfg.root}")
    log(f"    org_id: {cfg.org_id}")

    # ---- 名册 ----
    rs = _roster_summary(cfg)
    log(f"  · 名册：{rs['members']} 个席位 / {rs['accounts']} 个 Bailian 账号 / "
        f"{len(rs['groups'])} 个组 / {sum(1 for m in cfg.members if m.email)} 个邮箱")
    for g, ms in rs["groups"].items():
        log(f"      {g:<8} {len(ms):>2} 席")
    if rs["no_acc"]:
        log(f"      未开通（无 Bailian 账号）：{'、'.join(m.name_zh for m in rs['no_acc'])}")
    if rs["shared"]:
        log(f"      共享席位：{'、'.join(m.label for m in rs['shared'])}")
    if rs["dup"]:
        fatal.append(f"同一 Bailian 账号被映射到多行：{rs['dup']}")
    if rs["no_mail"]:
        issues.append(f"{len(rs['no_mail'])} 人缺邮箱：{'、'.join(m.name_zh for m in rs['no_mail'])}")

    # ---- 日历 ----
    from lib.calendar_cn import Calendar
    y, m = args.month
    cal = Calendar(cfg, y)
    this_m = cal.month_tally(y, m)
    log(f"  · 日历 {y}-{m:02d}：{this_m['workday']} 工作日 / {this_m['weekend']} 周末 / "
        f"{this_m['holiday']} 假日  {'✓ 已核对' if cal.is_verified(y, m) else '⚠ 未核对'}")
    if not cal.is_verified(y, m):
        issues.append(f"节假日配置未核对 {y}-{m:02d}，工作日数可能不准（请更新 config/holidays.yaml）")

    # ---- 价格 ----
    p = cfg.pricing
    log(f"  · 价格：标准 ¥{p['standard_seat']['price']}/{p['standard_seat']['credits']:,} · "
        f"高级 ¥{p['premium_seat']['price']}/{p['premium_seat']['credits']:,} · "
        f"加油包 ¥{p['pack']['price']}/{p['pack']['credits']:,}")

    # ---- 五项确认 ----
    log("  · 确认项")
    status = cfg.confirmation_status()
    bad = []
    for s in status:
        mark = "✓" if s["ok"] else "✗"
        log(f"    {mark} {KEY_LABEL[s['key']]:<20} {s['reason']}  (TTL {s['ttl']} 天)")
        if not s["ok"]:
            bad.append(s)

    if fatal:
        for f_ in fatal:
            log(f"  ✗ {f_}")
        return {"ok": False, "fatal": fatal, "issues": issues}

    if bad:
        if args.non_interactive:
            for b in bad:
                log(f"  ✗ 后台模式下确认项无效：{KEY_LABEL[b['key']]} — {b['reason']}")
            return {"ok": False, "exit": 2, "fatal": [b["reason"] for b in bad], "issues": issues}

        # 数据来源单独问：企业版 / 个人版二选一（personal 已在前面拦截，走到这里只可能是 enterprise）
        console_bad = next((b for b in bad if b["key"] == "console"), None)
        if console_bad:
            log("")
            log("  数据来源控制台（收集哪个）：")
            log("    [1] 企业版组织门户  https://tokenplan-enterprise.bailian.aliyunportal.com   ← 已实现")
            log("    [2] 个人控制台      https://bailian.console.aliyun.com                      ← 尚未支持")
            try:
                ans = input("  选择并确认？[1/2]（默认 1） ").strip().lower()
            except EOFError:
                ans = "1"
            if ans == "2":
                for line in PERSONAL_UNSUPPORTED:
                    log(line)
                return {"ok": False, "exit": 2, "fatal": ["选择了尚未支持的个人控制台"], "issues": issues}
            if ans not in ("", "1", "y", "yes"):
                return {"ok": False, "exit": 2, "fatal": ["用户拒绝确认"], "issues": issues}
            cfg.confirm("console", by=os.environ.get("USER", ""))
            bad = [b for b in bad if b["key"] != "console"]
            log("  ✓ 数据来源：企业版组织门户（已记录确认）")

        if bad:
            log("")
            for b in bad:
                log(f"  需要确认：{KEY_LABEL[b['key']]}")
            try:
                ans = input("  确认以上信息无误？[Y/n] ").strip().lower()
            except EOFError:
                ans = "y"
            if ans in ("", "y", "yes"):
                for b in bad:
                    cfg.confirm(b["key"], by=os.environ.get("USER", ""))
                log("  ✓ 已记录确认")
            else:
                return {"ok": False, "exit": 2, "fatal": ["用户拒绝确认"], "issues": issues}

    for i in issues:
        log(f"  ⚠ {i}")
    log("  ✓ 预检通过")
    return {"ok": True, "issues": issues, "roster": rs}