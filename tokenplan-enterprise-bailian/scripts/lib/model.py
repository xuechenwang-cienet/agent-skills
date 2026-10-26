"""把原始 CSV + 名册 + 订阅快照 + 日历 合成一份 analysis.json。

输出结构（s4 渲染只依赖这里）：
  meta / calendar / subscription / rates / models / people / groups / unmapped / warnings
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import math
import re

from .calendar_cn import Calendar

CTX = re.compile(r"^context_(\S+?)_(.+)$")
SUF = re.compile(r"_(peak|offpeak)$")
ROLE = {
    "input_token": "token_in",
    "output_token": "token_out",
    "input_token_cache": "cache",
    "input_token_cache_read": "cache_read",
    "input_token_cache_creation_5m": "cache_write_5m",
    "input_token_cache_creation_1h": "cache_write_1h",
}


def split_type(t: str):
    m = CTX.match(t)
    ctx, base = (m.group(1), m.group(2)) if m else ("", t)
    s = SUF.search(base)
    return ctx, SUF.sub("", base), (s.group(1) if s else "flat")


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s[:10])


def build(cfg, csv_path: str, subscription: dict, cal, month: tuple[int, int], log=print) -> dict:
    year, mon = month
    warnings: list[str] = []

    # ---------------- 读取明细 ----------------
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
    if not rows:
        raise RuntimeError("明细 CSV 为空")
    cols = set(rows[0].keys())
    need = {"统计开始时间", "成员ID", "模型名称", "套餐类型", "用量类型", "原始用量", "用量单位", "用量（Credits）"}
    if not need.issubset(cols):
        raise RuntimeError(f"明细 CSV 列不完整，缺少 {need - cols}")

    stamps = [r["统计开始时间"] for r in rows if r.get("统计开始时间")]
    data_start = min(stamps)
    data_end = max(stamps)
    end_date = _d(data_end)
    partial = data_end[11:16] < "23:59"
    rate_end = end_date - dt.timedelta(days=1) if partial else end_date
    if partial:
        warnings.append(f"最后一天 {end_date} 数据不完整（截至 {data_end[11:16]}），已从日均样本中剔除")

    # ---------------- 名册映射 ----------------
    acc2m = {a: m for m in cfg.members for a in m.account_ids}
    # 兜底：名册里只有名字没有 id 时，用名字匹配（首次导入前的旧配置）
    if not acc2m:
        by_name = {a: m for m in cfg.members for a in m.accounts}
        if by_name:
            warnings.append("名册缺少 bailian_account_ids，已退化为按显示名匹配，建议重新运行 import_roster.py")
    unmapped_credits = collections.Counter()
    unmapped_rows = collections.Counter()
    for r in rows:
        aid = r["成员ID"]
        if aid not in acc2m:
            unmapped_credits[aid] += float(r["用量（Credits）"])
            unmapped_rows[aid] += 1
    unmapped = [{"account_id": a, "credits": round(c, 4), "rows": unmapped_rows[a]}
                for a, c in unmapped_credits.most_common()]
    if unmapped:
        warnings.append(f"{len(unmapped)} 个 Bailian 账号未在名册中（合计 {sum(u['credits'] for u in unmapped):,.0f} 点），已单列为「未归属」")

    # ---------------- 系数 ----------------
    rate_agg = collections.defaultdict(lambda: [0.0, 0.0, 0])   # credits, tokens, n
    call_agg = collections.defaultdict(lambda: [0.0, 0.0, 0])
    for r in rows:
        model, unit = r["模型名称"], r["用量单位"]
        if unit == "tokens":
            ctx, base, per = split_type(r["用量类型"])
            a = rate_agg[(model, ctx, base, per)]
            a[0] += float(r["用量（Credits）"])
            a[1] += float(r["原始用量"])
            a[2] += 1
        elif unit == "次":
            _, _, per = split_type(r["用量类型"])
            a = call_agg[(model, per)]
            a[0] += float(r["用量（Credits）"])
            a[1] += float(r["原始用量"])
            a[2] += 1

    rates = []
    non_integer = []
    for (model, ctx, base, per), (c, t, n) in rate_agg.items():
        if not t:
            continue
        v = c / t * 1e6
        if abs(v - round(v)) > 1e-4:
            non_integer.append({"model": model, "ctx": ctx, "base": base, "period": per, "rate": v})
        rates.append({"model": model, "ctx": ctx, "base": base, "period": per,
                      "role": ROLE.get(base, base), "rate": v, "credits": c, "tokens": t, "rows": n})
    if non_integer:
        warnings.append(f"{len(non_integer)} 个系数不是整数，请检查数据（详见 manifest）")

    calls = [{"model": m, "period": p, "credits": c, "calls": t, "rows": n,
              "unit_price": c / t if t else 0} for (m, p), (c, t, n) in call_agg.items()]

    # ---------------- 日历 ----------------
    month_start, month_end = cal.month_range(year, mon)
    this_month = cal.month_tally(year, mon)
    ny, nm = (year + (mon == 12), (mon % 12) + 1)
    next_cal = cal if ny == year else Calendar(cfg, ny)
    next_start, next_end = next_cal.month_range(ny, nm)
    next_month = next_cal.month_tally(ny, nm)

    rate_start = month_start
    if rate_end < rate_start:
        rate_start, rate_end = month_start, month_start

    # 样本日：剔除假日与不完整日
    sample = {"workday": 0, "weekend": 0}
    for d in cal.days(rate_start, rate_end):
        k = cal.kind(d)
        if k in ("workday", "weekend"):
            sample[k] += 1
    # 剩余天数从「数据结束日的次日」开始算；结束当天可能只跑了一半，其已发生用量已计入 credits
    rem_start = end_date + dt.timedelta(days=1)
    remaining = cal.tally(rem_start, month_end) if rem_start <= month_end else {"workday": 0, "weekend": 0, "holiday": 0, "total": 0}

    if sample["workday"] < 3:
        warnings.append(f"本月工作日样本仅 {sample['workday']} 天，预测可信度较低")

    calendar_info = {
        "month": f"{year:04d}-{mon:02d}",
        "start": month_start.isoformat(), "end": month_end.isoformat(),
        "this_month": this_month,
        "next_month": {"month": f"{ny:04d}-{nm:02d}", **next_month},
        "sample": sample,
        "remaining": remaining,
        "holidays": cal.holiday_list(year, mon),
        "makeups": cal.makeup_list(year, mon),
        "verified": cal.is_verified(year, mon),
        "next_verified": next_cal.is_verified(ny, nm),
    }
    if not calendar_info["verified"]:
        warnings.append(f"节假日配置未覆盖 {year}-{mon:02d}，工作日数可能不准")
    if not calendar_info["next_verified"]:
        warnings.append(f"节假日配置未覆盖 {ny}-{nm:02d}（下月预测用）")

    # ---------------- 逐人 ----------------
    pri = cfg.pricing
    std_p, std_c = pri["standard_seat"]["price"], pri["standard_seat"]["credits"]
    prm_p, prm_c = pri["premium_seat"]["price"], pri["premium_seat"]["credits"]
    pack_p, pack_c = pri["pack"]["price"], pri["pack"]["credits"]

    P = {m.hrid or m.name_zh: dict(
        credits=0.0, seat=0.0, pack=0.0, rows=0,
        day=collections.Counter(), model=collections.Counter(),
        inp=0.0, cr=0.0, cw=0.0, out=0.0, peak=0.0, offpeak=0.0) for m in cfg.members}

    def key_of(m):
        return m.hrid or m.name_zh

    for r in rows:
        m = acc2m.get(r["成员ID"])
        if not m:
            continue
        d = P[key_of(m)]
        c = float(r["用量（Credits）"])
        d["credits"] += c
        d["rows"] += 1
        d["model"][r["模型名称"]] += c
        if r["套餐类型"] == "SEAT":
            d["seat"] += c
        else:
            d["pack"] += c
        day = _d(r["统计开始时间"])
        if day <= rate_end:
            k = cal.kind(day)
            if k in ("workday", "weekend"):
                d["day"][k] += c
        if r["用量单位"] == "tokens":
            t, n = r["用量类型"], float(r["原始用量"])
            if "cache_creation" in t:
                d["cw"] += n
            elif "cache" in t:
                d["cr"] += n
            elif "output" in t:
                d["out"] += n
            else:
                d["inp"] += n
        if r["用量类型"].endswith("_peak"):
            d["peak"] += c
        elif r["用量类型"].endswith("_offpeak"):
            d["offpeak"] += c

    sw, se = max(sample["workday"], 1), max(sample["weekend"], 1)
    people = []
    for m in cfg.members:
        d = P[key_of(m)]
        wd_rate = d["day"]["workday"] / sw
        we_rate = d["day"]["weekend"] / se
        next_fc = wd_rate * next_month["workday"] + we_rate * next_month["weekend"]
        rem_fc = wd_rate * remaining.get("workday", 0) + we_rate * remaining.get("weekend", 0)
        quota = m.seat_credits
        unit_price = prm_p / prm_c if m.premium else std_p / std_c
        projected = d["credits"] + rem_fc
        unused = max(0.0, quota - projected)
        waste = unused * unit_price
        people.append({
            "key": key_of(m), "name": m.name_zh, "label": m.label,
            "name_en": m.name_en, "email": m.email,
            "owner": m.team_owner, "dept": m.dept, "pcode": m.pcode,
            "accounts": m.accounts, "shared_with": m.sharing_with,
            "quota": quota, "premium": m.premium,
            "seat_unit_price": unit_price, "seat_fee": prm_p if m.premium else std_p,
            "credits": d["credits"], "seat": d["seat"], "pack": d["pack"], "rows": d["rows"],
            "models": dict(d["model"].most_common()),
            "top_model": (d["model"].most_common(1)[0][0] if d["model"] else "—"),
            "tokens": {"in": d["inp"], "out": d["out"], "cache_read": d["cr"], "cache_write": d["cw"]},
            "cache_ratio": (d["cr"] / (d["cr"] + d["inp"]) * 100) if (d["cr"] + d["inp"]) else None,
            "offpeak_ratio": (d["offpeak"] / (d["offpeak"] + d["peak"]) * 100) if (d["offpeak"] + d["peak"]) else None,
            "peak": d["peak"], "offpeak": d["offpeak"],
            "seat_pct": (d["seat"] / quota * 100) if quota else 0,
            "wd_rate": wd_rate, "we_rate": we_rate,
            "rem_forecast": rem_fc, "projected": projected,
            "unused": unused, "waste": waste,
            "forecast": next_fc, "pack_forecast": max(next_fc - quota, 0),
            "cost_now": (prm_p if m.premium else std_p) + d["pack"] * pack_p / pack_c,
            "status": ("未开通" if not m.accounts else
                       "席位结余" if unused > quota * cfg.forecast["seat_unused_threshold"] else
                       "席位用尽" if d["credits"] >= quota * 0.995 else
                       "席位紧张" if d["credits"] >= quota * 0.8 else
                       "零用量" if d["credits"] == 0 else "正常"),
        })

    # ---------------- 分组 ----------------
    groups = []
    for owner in dict.fromkeys(m.team_owner for m in cfg.members):
        ps = [p for p in people if p["owner"] == owner]
        groups.append({
            "name": owner, "count": len(ps),
            "credits": sum(p["credits"] for p in ps),
            "seat": sum(p["seat"] for p in ps),
            "pack": sum(p["pack"] for p in ps),
            "quota": sum(p["quota"] for p in ps),
            "seat_fee": sum(p["seat_fee"] for p in ps),
            "forecast": sum(p["forecast"] for p in ps),
            "pack_forecast": sum(p["pack_forecast"] for p in ps),
            "rows": sum(p["rows"] for p in ps),
            "people": [p["key"] for p in ps],
            "models": dict(collections.Counter(
                {k: v for p in ps for k, v in p["models"].items()}).most_common()),
        })

    # ---------------- 模型 ----------------
    M = collections.defaultdict(lambda: dict(credits=0.0, tokens=0.0, inp=0.0, out=0.0,
                                             cr=0.0, cw=0.0, users=set(), groups=set(),
                                             by_group=collections.Counter(), peak=0.0, offpeak=0.0, rows=0))
    for r in rows:
        md = M[r["模型名称"]]
        c = float(r["用量（Credits）"])
        md["credits"] += c
        md["rows"] += 1
        m = acc2m.get(r["成员ID"])
        if m:
            md["users"].add(key_of(m))
            md["groups"].add(m.team_owner)
            md["by_group"][m.team_owner] += c
        if r["用量单位"] == "tokens":
            t, n = r["用量类型"], float(r["原始用量"])
            md["tokens"] += n
            if "cache_creation" in t:
                md["cw"] += n
            elif "cache" in t:
                md["cr"] += n
            elif "output" in t:
                md["out"] += n
            else:
                md["inp"] += n
        if r["用量类型"].endswith("_peak"):
            md["peak"] += c
        elif r["用量类型"].endswith("_offpeak"):
            md["offpeak"] += c

    models = []
    for name, md in sorted(M.items(), key=lambda kv: -kv[1]["credits"]):
        models.append({
            "name": name, "credits": md["credits"], "rows": md["rows"],
            "tokens": md["tokens"], "in": md["inp"], "out": md["out"],
            "cache_read": md["cr"], "cache_write": md["cw"],
            "mix_price": (md["credits"] / md["tokens"] * 1e6) if md["tokens"] else 0,
            "users": len(md["users"]), "groups": sorted(md["groups"]),
            "by_group": dict(md["by_group"]),
            "peak": md["peak"], "offpeak": md["offpeak"],
        })

    # ---------------- 采购测算 ----------------
    total_credits = sum(p["credits"] for p in people)
    total_forecast = sum(p["forecast"] for p in people)
    pack_forecast = sum(p["pack_forecast"] for p in people)
    seat_cap = sum(p["quota"] for p in people)
    seat_fee = sum(p["seat_fee"] for p in people)

    seats_now = {s["type"]: s for s in subscription.get("seats", [])}
    seat_left_now = sum((s.get("remaining") or 0) for s in subscription.get("seats", []))
    pack_left_now = (subscription.get("pack") or {}).get("remaining") or 0
    rem_forecast_total = sum(p["rem_forecast"] for p in people)
    pack_draw_rest = max(0.0, rem_forecast_total - seat_left_now)
    pack_carry = max(0.0, pack_left_now - pack_draw_rest)

    breakeven = std_c + (prm_p - std_p) / (pack_p / pack_c)
    upgrade = [p for p in people if p["forecast"] > breakeven and not p["premium"]]
    save_pts = len(upgrade) * (prm_c - std_c)

    def packs_needed(need: float) -> int:
        return max(0, math.ceil((need - pack_carry) / pack_c)) if need > pack_carry else 0

    packs_a = packs_needed(pack_forecast)
    packs_b = packs_needed(max(0.0, pack_forecast - save_pts))
    seat_fee_b = seat_fee + len(upgrade) * (prm_p - std_p)

    procurement = {
        "seat_cap": seat_cap, "seat_fee": seat_fee,
        "pack_forecast": pack_forecast,
        "pack_left_now": pack_left_now, "seat_left_now": seat_left_now,
        "rem_forecast_total": rem_forecast_total,
        "pack_draw_rest": pack_draw_rest, "pack_carry": pack_carry,
        "breakeven": breakeven,
        "plan_a": {"packs": packs_a, "pack_cost": packs_a * pack_p,
                   "seat_fee": seat_fee, "total": seat_fee + packs_a * pack_p,
                   "need": pack_forecast},
        "plan_b": {"packs": packs_b, "pack_cost": packs_b * pack_p,
                   "seat_fee": seat_fee_b, "total": seat_fee_b + packs_b * pack_p,
                   "need": max(0.0, pack_forecast - save_pts),
                   "upgrades": [p["key"] for p in upgrade], "saved_points": save_pts},
    }

    # ---------------- 结余 ----------------
    thr = cfg.forecast["seat_unused_threshold"]
    unused_people = [p for p in people if p["unused"] > p["quota"] * thr]
    waste_total = sum(p["waste"] for p in unused_people)

    return {
        "meta": {
            "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "month": calendar_info["month"],
            "data_start": data_start, "data_end": data_end,
            "csv": csv_path, "rows": len(rows),
            "models": len(models), "members": len(people),
            "total_credits": total_credits,
            "total_forecast": total_forecast,
        },
        "calendar": calendar_info,
        "subscription": subscription,
        "rates": rates, "calls": calls, "models": models,
        "people": people, "groups": groups, "unmapped": unmapped,
        "procurement": procurement,
        "waste": {"threshold": thr, "total": waste_total,
                  "count": len(unused_people),
                  "people": [p["key"] for p in unused_people]},
        "warnings": warnings,
    }
