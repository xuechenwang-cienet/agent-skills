"""把原始 CSV + 名册 + 订阅快照 + 日历 合成一份 analysis.json。

输出结构（s4 渲染只依赖这里）：
  meta / calendar / subscription / rates / models / people / groups / unmapped / warnings
"""
from __future__ import annotations

import bisect
import collections
import csv
import datetime as dt
import math
import re
import statistics

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


def _hhmm(s: str) -> int:
    return int(s[:2]) * 60 + int(s[3:5])


def _minstr(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def _pctile(values: list, v):
    """v 在 values 中的分位（0–100，越大越靠前）。v 为 None 返回 None。"""
    if v is None:
        return None
    vals = sorted(values)
    below = bisect.bisect_left(vals, v)
    return below / max(len(vals) - 1, 1) * 100


# ---------------- 行为画像（完整日口径） ----------------
def _profile(d: dict, cal, month_start: dt.date, month_end: dt.date,
             rate_end: dt.date, beh: dict) -> dict:
    """把逐人采集的原始计数合成行为画像。

    所有比例均基于「完整日」（剔除数据不完整的最后一天），避免早/晚占比被半天数据拉偏。
    """
    gap = int(beh.get("session_gap_min", 15))
    n0, n1 = beh.get("night", [22, 8])
    c0, c1 = beh.get("core", [9, 18])

    hours_c = [d["hour_c"].get(h, 0.0) for h in range(24)]
    hours_m = [len(s) for s in d["hour_m"]]
    credits_fd = sum(hours_c)
    denom = credits_fd or 1.0

    night_h = list(range(n0, 24)) + list(range(0, n1))
    night_c = sum(hours_c[h] for h in night_h)
    evening_c = sum(hours_c[18:22])
    core_c = sum(hours_c[c0:c1])
    lunch_c = hours_c[12] + hours_c[13]

    days, firsts, lasts, spans = [], [], [], []
    active_minutes = active_days = 0
    sessions = session_mins = session_max = 0
    streak = best_streak = 0
    peak_day, peak_c = None, 0.0
    cur = month_start
    while cur <= min(month_end, rate_end):
        s = cur.isoformat()
        c = d["daily_c"].get(s, 0.0)
        mins = sorted(d["daily_min"].get(s, ()))
        kind = cal.kind(cur)
        first = last = None
        if mins:
            first, last = _hhmm(mins[0]), _hhmm(mins[-1])
            firsts.append(first)
            lasts.append(last)
            spans.append(last - first + 1)
            active_minutes += len(mins)
            active_days += 1
            seg = run = 1
            for a, b in zip(mins, mins[1:]):
                if _hhmm(b) - _hhmm(a) <= gap:
                    run += 1
                else:
                    session_mins += run
                    session_max = max(session_max, run)
                    seg += 1
                    run = 1
            session_mins += run
            session_max = max(session_max, run)
            sessions += seg
            streak += 1
            best_streak = max(best_streak, streak)
        else:
            streak = 0
        if mins and c > peak_c:
            peak_day, peak_c = s, c
        days.append({"date": s, "credits": c, "minutes": len(mins), "kind": kind,
                     "first": _minstr(first) if first is not None else None,
                     "last": _minstr(last) if last is not None else None})
        cur += dt.timedelta(days=1)

    wdh = [[0.0] * 24 for _ in range(7)]
    for (w, h), v in d["wdh"].items():
        wdh[w][h] = v
    dh = [[d["dh"].get((x["date"], h), 0.0) for h in range(24)] for x in days]

    mshare = []
    mtot = sum(ms["credits"] for ms in d["mstat"].values()) or 1.0
    for name, ms in d["mstat"].items():
        mshare.append({
            "name": name, "credits": ms["credits"], "share": ms["credits"] / mtot * 100,
            "tokens": ms["tokens"], "rows": ms["rows"], "days": len(ms["days"]),
            "mix_price": (ms["credits"] / ms["tokens"] * 1e6) if ms["tokens"] else None,
            "inp": ms["inp"], "out": ms["out"], "cr": ms["cr"], "cw": ms["cw"]})
    mshare.sort(key=lambda x: -x["credits"])

    total_c = d["credits"] or 1.0
    wd_c = sum(x["credits"] for x in days if x["kind"] == "weekend")
    work_c = sum(x["credits"] for x in days if x["kind"] == "workday")
    tokens_total = d["inp"] + d["out"] + d["cr"] + d["cw"]
    latest = max(((x["date"], x["last"]) for x in days if x["last"]), key=lambda x: x[1], default=None)
    earliest = min(((x["date"], x["first"]) for x in days if x["first"]), key=lambda x: x[1], default=None)

    return {
        "hours_c": hours_c, "hours_m": hours_m,
        "night_share": night_c / denom * 100,
        "evening_share": evening_c / denom * 100,
        "core_share": core_c / denom * 100,
        "lunch_share": lunch_c / denom * 100,
        "weekend_share": (wd_c / (wd_c + work_c) * 100) if (wd_c + work_c) else None,
        "active_days": active_days, "active_minutes": active_minutes,
        "avg_min_day": active_minutes / active_days if active_days else 0.0,
        "avg_span_h": (sum(spans) / len(spans) / 60) if spans else None,
        "start_med": _minstr(int(statistics.median(firsts))) if firsts else None,
        "end_med": _minstr(int(statistics.median(lasts))) if lasts else None,
        "latest": latest, "earliest": earliest,
        "streak_max": best_streak,
        "peak_day": peak_day, "peak_credits": peak_c, "peak_share": peak_c / total_c * 100,
        "sessions": sessions,
        "session_avg_min": (session_mins / sessions) if sessions else 0.0,
        "session_max_min": session_max,
        "sessions_per_day": sessions / active_days if active_days else 0.0,
        "days": days, "wdh": wdh, "dh": dh,
        "models": mshare,
        "top1_share": mshare[0]["share"] if mshare else 0.0,
        "model_hhi": sum((x["share"]) ** 2 for x in mshare) / 10000.0,
        "mix_price": (credits_fd / tokens_total * 1e6) if tokens_total else None,
        "tokens_total": tokens_total,
        "credits_per_active_hour": (credits_fd / (active_minutes / 60)) if active_minutes else None,
        "tokens_per_active_min": (tokens_total / active_minutes) if active_minutes else None,
        "partial_credits": d["partial_credits"],
    }


# ---------------- 模式标签 / 分位 / 相似同事 / 组与部门行为汇总 ----------------
def _behavior_agg(ps: list) -> dict:
    """组级 / 部门级行为汇总：24h 曲线、时段占比（点数加权）、模式分布。"""
    hour_c = [0.0] * 24
    hour_people = [0] * 24
    csum = sum(p["credits"] for p in ps) or 1.0
    wsum = 0.0
    for p in ps:
        pr = p["profile"]
        for h in range(24):
            hour_c[h] += pr["hours_c"][h]
            if pr["hours_m"][h] > 0:
                hour_people[h] += 1
        wsum += (pr["weekend_share"] or 0) * p["credits"]
    return {
        "hour_c": hour_c, "hour_people": hour_people,
        "night_share": sum(p["profile"]["night_share"] * p["credits"] for p in ps) / csum,
        "evening_share": sum(p["profile"]["evening_share"] * p["credits"] for p in ps) / csum,
        "core_share": sum(p["profile"]["core_share"] * p["credits"] for p in ps) / csum,
        "weekend_share": wsum / csum,
        "active_minutes": sum(p["profile"]["active_minutes"] for p in ps),
        "active_days_med": statistics.median([p["profile"]["active_days"] for p in ps]) if ps else 0,
        "patterns": dict(collections.Counter(p["pattern"] for p in ps)),
    }


def _behavior_pass(cfg, people: list, sample: dict, tz=None) -> dict:
    accounts = [p for p in people if p["accounts"]]
    used = [p for p in accounts if p["credits"] > 0]

    metrics = {
        "credits": [p["credits"] for p in used],
        "night": [p["profile"]["night_share"] for p in used],
        "weekend": [p["profile"]["weekend_share"] or 0 for p in used],
        "active_days": [p["profile"]["active_days"] for p in used],
        "minutes": [p["profile"]["avg_min_day"] for p in used],
        "mix_price": [p["profile"]["mix_price"] for p in used if p["profile"]["mix_price"]],
        "span": [p["profile"]["avg_span_h"] for p in used if p["profile"]["avg_span_h"]],
    }
    for p in people:
        pr = p["profile"]
        has = p["credits"] > 0
        p["pct"] = {
            "credits": _pctile(metrics["credits"], p["credits"]) if has else None,
            "night": _pctile(metrics["night"], pr["night_share"]) if has else None,
            "weekend": _pctile(metrics["weekend"], pr["weekend_share"] or 0) if has else None,
            "active_days": _pctile(metrics["active_days"], pr["active_days"]) if has else None,
            "minutes": _pctile(metrics["minutes"], pr["avg_min_day"]) if has else None,
            "mix_price": _pctile(metrics["mix_price"], pr["mix_price"]) if pr["mix_price"] else None,
            "span": _pctile(metrics["span"], pr["avg_span_h"]) if pr["avg_span_h"] else None,
        }

    # ---- 模式标签（单一标签，规则按顺序命中即止） ----
    med_active = statistics.median(metrics["active_days"]) if metrics["active_days"] else 0
    grp_avg = collections.defaultdict(lambda: [0.0, 0])
    for p in people:
        grp_avg[p["owner"]][0] += p["credits"]
        grp_avg[p["owner"]][1] += 1
    for p in people:
        pr = p["profile"]
        if not p["accounts"]:
            p["pattern"] = "未开通"
            continue
        if p["credits"] <= 0:
            p["pattern"] = "零用量"
            continue
        gavg = grp_avg[p["owner"]][0] / max(grp_avg[p["owner"]][1], 1)
        ns, es, cs = pr["night_share"], pr["evening_share"], pr["core_share"]
        if pr["active_days"] <= 3 or p["credits"] < gavg * 0.05:
            p["pattern"] = "轻量偶发"
        elif ns >= 25:
            p["pattern"] = "夜间型"
        elif es + ns >= 40 and cs < 60:
            p["pattern"] = "早晚型"
        elif cs >= 70:
            p["pattern"] = "白天型"
        elif med_active and pr["active_days"] <= med_active * 0.5 and pr["peak_share"] >= 25:
            p["pattern"] = "集中攻坚"
        elif sample.get("workday") and pr["active_days"] >= sample["workday"] * 0.85 and pr["peak_share"] < 20:
            p["pattern"] = "持续稳定"
        else:
            p["pattern"] = "混合型"

    # ---- 相似同事：组内模型结构余弦相似度 Top3 ----
    by_owner = collections.defaultdict(list)
    for p in people:
        by_owner[p["owner"]].append(p)
    for ps in by_owner.values():
        used_ps = [p for p in ps if p["credits"] > 0]
        vocab = sorted({m["name"] for p in used_ps for m in p["profile"]["models"]})
        if len(used_ps) < 2 or not vocab:
            for p in ps:
                p["peers"] = []
            continue
        idx = {n: i for i, n in enumerate(vocab)}
        vecs = {}
        for p in used_ps:
            v = [0.0] * len(vocab)
            for m in p["profile"]["models"]:
                v[idx[m["name"]]] = m["share"]
            vecs[p["key"]] = v

        def cos(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a))
            nb = math.sqrt(sum(x * x for x in b))
            return dot / (na * nb) if na and nb else 0.0

        for p in used_ps:
            sims = sorted(((cos(vecs[p["key"]], vecs[q["key"]]), q) for q in used_ps if q is not p),
                          key=lambda x: -x[0])
            p["peers"] = [{"key": q["key"], "name": q["name"], "sim": round(s * 100)} for s, q in sims[:3]]
        for p in ps:
            p.setdefault("peers", [])

    # ---- 组级 / 部门级行为汇总 ----
    behavior = _behavior_agg(accounts)
    sw = sample.get("workday", 0)
    tiers = {"高频": 0, "稳定": 0, "偶发": 0, "沉睡": 0}
    for p in accounts:
        if p["credits"] <= 0:
            tiers["沉睡"] += 1
        elif sw and p["profile"]["active_days"] >= sw * 0.8:
            tiers["高频"] += 1
        elif sw and p["profile"]["active_days"] >= sw * 0.5:
            tiers["稳定"] += 1
        else:
            tiers["偶发"] += 1
    clusters = collections.Counter()
    cluster_c = collections.Counter()
    for p in used:
        clusters[p["profile"]["models"][0]["name"] if p["profile"]["models"] else "—"] += 1
        cluster_c[p["profile"]["models"][0]["name"] if p["profile"]["models"] else "—"] += p["credits"]
    busiest = max(range(24), key=lambda h: behavior["hour_c"][h])
    core_hours = [h for h in range(9, 18) if behavior["hour_people"][h] > 0]
    tz_bad, tz_n = tz or (0, 0)
    behavior.update({
        "tiers": tiers,
        "clusters": [{"model": k, "count": v, "credits": cluster_c[k]} for k, v in clusters.most_common()],
        "median_active_days": med_active,
        "busiest_hour": busiest,
        "quiet_core_hour": min(core_hours, key=lambda h: behavior["hour_people"][h]) if core_hours else None,
        "tz": {"checked": tz_n, "mismatch": tz_bad, "ratio": (tz_bad / tz_n * 100) if tz_n else 0.0},
    })
    return behavior


def build(cfg, csv_path: str, subscription: dict, cal, month: tuple[int, int], log=print) -> dict:
    year, mon = month
    warnings: list[str] = []
    beh = dict(cfg.raw.get("behavior") or {})   # 行为画像口径（可选配置，不参与确认哈希）

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
    tz_bad = tz_n = 0        # _peak/_offpeak 后缀与时间戳小时的一致性（时区哨兵）
    for r in rows:
        model, unit = r["模型名称"], r["用量单位"]
        if unit == "tokens":
            ctx, base, per = split_type(r["用量类型"])
            t = r["用量类型"]
            if t.endswith("_peak") or t.endswith("_offpeak"):
                h = int(r["统计开始时间"][11:13])
                tz_n += 1
                if (8 <= h <= 21) != t.endswith("_peak"):
                    tz_bad += 1
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
    if tz_n and tz_bad / tz_n > 0.02:
        warnings.append(f"peak/offpeak 后缀与时间戳小时不一致 {tz_bad}/{tz_n}（{tz_bad / tz_n * 100:.1f}%），"
                        f"导出时区或时段口径可能已变化，作息分析仅供参考")

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

    def _mstat():
        return dict(credits=0.0, tokens=0.0, inp=0.0, out=0.0, cr=0.0, cw=0.0, rows=0, days=set())

    # ---- 成员身份 key：全局解析一遍，防撞名 ----
    # 回退链：中文名 > 钉联名（bailian_accounts 首项）> 邮箱前缀 > hrid > 英文名 > unknown
    # hrid 仅作最后兜底，不参与日常身份/文件名逻辑（名册里 hrid 可能是错数据）
    key_map: dict[int, str] = {}
    used_keys: set[str] = set()
    for m in cfg.members:
        cand = (m.name_zh or (m.accounts[0] if m.accounts else "")
                or (m.email.split("@", 1)[0] if m.email else "")
                or m.hrid or m.name_en or "unknown")
        k = cand
        n = 2
        while k in used_keys:
            k = f"{cand}-{n}"
            n += 1
        if k != cand:
            warnings.append(f"成员 key 撞名：{cand} → {k}（第 {n - 1} 个同名）")
        used_keys.add(k)
        key_map[id(m)] = k

    def key_of(m):
        return key_map[id(m)]

    P = {key_of(m): dict(
        credits=0.0, seat=0.0, pack=0.0, rows=0,
        day=collections.Counter(), model=collections.Counter(),
        inp=0.0, cr=0.0, cw=0.0, out=0.0, peak=0.0, offpeak=0.0,
        # ---- 行为画像采集（均为完整日口径，剔除不完整最后一天） ----
        partial_credits=0.0,                       # 不完整日产生的点数（不计入作息分布）
        hour_c=collections.Counter(),              # 小时 → Credits
        hour_m=[set() for _ in range(24)],         # 小时 → {date hh:mm} 活跃分钟
        dh=collections.Counter(),                  # (date, hour) → Credits（日历热力图）
        daily_c=collections.Counter(),             # date → Credits（含不完整日）
        daily_min=collections.defaultdict(set),    # date → {"HH:MM"}（完整日）
        wdh=collections.Counter(),                 # (weekday, hour) → Credits
        mstat=collections.defaultdict(_mstat)) for m in cfg.members}

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
        ts = r["统计开始时间"]
        day = _d(ts)
        day_s = ts[:10]
        d["daily_c"][day_s] += c
        if day <= rate_end:
            k = cal.kind(day)
            if k in ("workday", "weekend"):
                d["day"][k] += c
            hh = int(ts[11:13])
            d["hour_c"][hh] += c
            d["hour_m"][hh].add(ts[:16])
            d["dh"][(day_s, hh)] += c
            d["daily_min"][day_s].add(ts[11:16])
            d["wdh"][(day.weekday(), hh)] += c
            ms = d["mstat"][r["模型名称"]]
            ms["credits"] += c
            ms["rows"] += 1
            ms["days"].add(day_s)
        else:
            d["partial_credits"] += c
        if r["用量单位"] == "tokens":
            t, n = r["用量类型"], float(r["原始用量"])
            if "cache_creation" in t:
                d["cw"] += n
                tok_role = "cw"
            elif "cache" in t:
                d["cr"] += n
                tok_role = "cr"
            elif "output" in t:
                d["out"] += n
                tok_role = "out"
            else:
                d["inp"] += n
                tok_role = "inp"
            if day <= rate_end:
                d["mstat"][r["模型名称"]][tok_role] += n
                d["mstat"][r["模型名称"]]["tokens"] += n
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
            "profile": _profile(d, cal, month_start, month_end, rate_end, beh),
        })

    # ---- 行为后处理：分位 / 模式标签 / 相似同事 / 部门级行为汇总 ----
    behavior = _behavior_pass(cfg, people, sample, tz=(tz_bad, tz_n))

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
    byp = {p["key"]: p for p in people}
    for g in groups:
        g["behavior"] = _behavior_agg([byp[k] for k in g["people"]])

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
        "behavior": behavior,
        "waste": {"threshold": thr, "total": waste_total,
                  "count": len(unused_people),
                  "people": [p["key"] for p in unused_people]},
        "warnings": warnings,
    }
