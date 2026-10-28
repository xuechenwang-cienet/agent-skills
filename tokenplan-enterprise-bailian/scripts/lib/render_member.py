"""个人（成员）行为画像报告渲染。输入 analysis dict + 成员 key，输出 HTML 字符串。

口径说明：作息与时长均由「分钟级计费桶」推断 —— 代表有调用发生的时刻，不等同于考勤；
所有比例基于完整日（剔除数据不完整的最后一天）。
"""
from __future__ import annotations

import collections

from .render_util import (PER, esc, f, fnum, hbars, heat_grid, pct_row,
                          pattern_chip)
from .ui import CSS, JS

WD = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
KIND_MARK = {"workday": "", "weekend": "周末", "holiday": "休", "makeup": "调休"}


def _price_of(rates, model):
    """模型 → 主力档位 {role: rate}；取该模型点数最大的 (ctx, period)。"""
    tier = collections.defaultdict(float)
    for r in rates:
        if r["model"] == model:
            tier[(r["ctx"], r["period"])] += r["credits"]
    if not tier:
        return {}, ("", "flat")
    ctx, per = max(tier, key=lambda k: tier[k])
    return {r["role"]: r["rate"] for r in rates
            if r["model"] == model and r["ctx"] == ctx and r["period"] == per}, (ctx, per)


def render(A, cfg, key: str, accent: str, role: str = "member") -> str:
    """role="member" 发本人的裁剪版（跨人信息匿名化）；role="full" 管理者点开的完整版。"""
    assert role in ("member", "full"), role
    meta, cal, sub, proc = A["meta"], A["calendar"], A["subscription"], A["procurement"]
    by_key = {p["key"]: p for p in A["people"]}
    p = by_key[key]
    pr = p["profile"]
    pct = p["pct"]
    group = next(g for g in A["groups"] if g["name"] == p["owner"])
    gb = group["behavior"]
    beh = A["behavior"]
    rates = A["rates"]
    pcfg = cfg.pricing
    pack_unit = pcfg["pack"]["price"] / pcfg["pack"]["credits"]
    denom = meta["total_credits"] or 1
    nx = cal["next_month"]["month"]
    hours = [str(h) if h % 3 == 0 else "" for h in range(24)]

    credits, total = p["credits"], meta["total_credits"]
    has_usage = credits > 0
    models = pr["models"]

    # ---------- 02 模型偏好 ----------
    top6 = models[:6]
    other_c = sum(m["credits"] for m in models[6:])
    segs, legend = [], []
    palette = ["#7aa7d8", "#ff7a45", "#e8b44a", "#c792ea", "#5fc9a5", "#d98b8b", "#9aa5b1"]
    for i, m in enumerate(top6 + ([{"name": "其他", "share": 100 - sum(x["share"] for x in top6), "credits": other_c}] if other_c > 0 else [])):
        col = palette[i % len(palette)]
        segs.append(f'<i style="width:{max(m["share"], .15):.2f}%;background:{col}"></i>')
        legend.append(f'<span><i style="background:{col}"></i>{esc(m["name"])} {m["share"]:.1f}%</span>')
    mrows = []
    for m in models:
        keys, (ctx, per) = _price_of(rates, m["name"])
        tier = f' <span class="ctx">{esc(ctx)}</span>' if ctx else ""
        mrows.append(f'''<tr><td class="m">{esc(m["name"])}{tier}</td>
          <td><span class="chip {per}">{PER[per][0]}</span></td>
          <td class="num">{f(m["credits"])}</td><td class="num dim">{m["share"]:.1f}%</td>
          <td class="num dim">{fnum(m["tokens"] / 1e6, 2)}M</td>
          <td class="num">{fnum(m["mix_price"])}</td>
          <td class="num dim">{m["days"]}</td><td class="num dim">{m["rows"]:,}</td></tr>''')

    sel_kv = []
    if models:
        sel_kv.append(("主力模型", f'<b>{esc(models[0]["name"])}</b>，占 {models[0]["share"]:.1f}%'
                       + (f'（共 {models[0]["days"]} 天有调用）' if models[0]["days"] else "")))
    sel_kv.append(("模型集中度", f'HHI <b>{pr["model_hhi"]:.2f}</b>' +
                   ("——高度单一" if pr["model_hhi"] > 0.85 else
                    "——主次分明" if pr["model_hhi"] > 0.5 else "——多头并用")))
    if pr["mix_price"]:
        sel_kv.append(("个人混合单价", f'<b>{fnum(pr["mix_price"])}</b> 点 / 1M tokens'
                       + (f'（部门 P{pct["mix_price"]:.0f}）' if pct["mix_price"] is not None else "")))
    if p["models"]:
        gtop = max(group["models"].items(), key=lambda kv: kv[1])
        sel_kv.append(("对比本组", f'本组主力是 <b>{esc(gtop[0])}</b>（{gtop[1] / group["credits"] * 100:.1f}%），'
                       f'本组夜间占比 {gb["night_share"]:.1f}%、周末 {gb["weekend_share"]:.1f}%'))

    # ---------- 03 工作时段 ----------
    seg_cards = f'''
  <div class="grid3 rv" style="grid-template-columns:repeat(4,1fr);margin:18px 0 6px">
    <div class="card cool"><span class="big">{pr["core_share"]:.1f}<span>%</span></span><h3>核心时段 09–18</h3><p>{f(sum(pr["hours_c"][9:18]))} 点发生在工作时间。</p></div>
    <div class="card warm"><span class="big">{pr["evening_share"]:.1f}<span>%</span></span><h3>晚间 18–22</h3><p>{f(sum(pr["hours_c"][18:22]))} 点，下班后时段。</p></div>
    <div class="card hot"><span class="big">{pr["night_share"]:.1f}<span>%</span></span><h3>夜间 22–08</h3><p>{f(sum(pr["hours_c"][22:]) + sum(pr["hours_c"][:8]))} 点（部门平均 {beh["night_share"]:.1f}%）。</p></div>
    <div class="card"><span class="big">{(pr["weekend_share"] or 0):.1f}<span>%</span></span><h3>周末</h3><p>{f(sum(x["credits"] for x in pr["days"] if x["kind"] == "weekend"))} 点在周末产生（部门 {beh["weekend_share"]:.1f}%）。</p></div>
  </div>'''
    # 预计算（避免在 f-string 内嵌套同引号 f-string，兼容 Python 3.11）
    span_txt = f'{pr["avg_span_h"]:.1f}' if pr["avg_span_h"] is not None else "—"
    latest_txt = f'{pr["latest"][0]} {pr["latest"][1]}' if pr["latest"] else "—"
    earliest_txt = f'{pr["earliest"][0]} {pr["earliest"][1]}' if pr["earliest"] else "—"
    cph_txt = f'{pr["credits_per_active_hour"]:,.0f}' if pr["credits_per_active_hour"] else "—"
    tpam_txt = f'{pr["tokens_per_active_min"]:,.0f}' if pr["tokens_per_active_min"] else "—"
    off_txt = (f'平峰 {p["offpeak_ratio"]:.1f}%（deepseek-v4.1-flash 可见时段差异）'
               if p["offpeak_ratio"] is not None else "本月未使用带高峰/平峰区分的模型")
    cache_txt = f'{p["cache_ratio"]:.1f}%' if p["cache_ratio"] is not None else "—"
    night_hot = "hot" if pr["night_share"] >= 25 else "warm"
    sched_kv = f'''
  <div class="kv rv" style="margin-top:18px">
    <div>典型作息</div><div>{esc(pr["start_med"] or "—")} → {esc(pr["end_med"] or "—")}（中位数；日均跨度 <b>{span_txt} 小时</b>）</div>
    <div>最晚一次</div><div>{esc(latest_txt)}</div>
    <div>最早一次</div><div>{esc(earliest_txt)}</div>
    <div>活跃强度</div><div>日均活跃 <b>{pr["avg_min_day"]:.0f} 分钟</b>（部门 P{pct["minutes"]:.0f}），全月累计 {pr["active_minutes"]:,} 分钟 ≈ {pr["active_minutes"] / 60:.0f} 小时</div>
    <div>口径说明</div><div>由<b>分钟级计费桶</b>推断：分钟内有调用即计为活跃，<b>不等同于考勤</b>；比例基于完整日。</div>
  </div>'''

    # ---------- 04 使用节奏 ----------
    day_rows = [f'{x["date"][5:]} {KIND_MARK.get(x["kind"], "")}'.strip() for x in pr["days"]]
    cal_heat = heat_grid(
        day_rows, hours, pr["dh"], row_w=76, cell=13,
        title=lambda i, j, v: f'{pr["days"][i]["date"]} {j:02d}:00 · {f(v)} 点 · 活跃 {pr["days"][i]["minutes"]} 分钟')
    cards4 = f'''
  <div class="grid3 rv" style="grid-template-columns:repeat(4,1fr);margin:20px 0 8px">
    <div class="card"><span class="big">{pr["active_days"]}<span>/ {len(pr["days"])} 个完整日</span></span>
      <h3>活跃天数</h3><p>样本期共 {cal["sample"]["workday"]} 个工作日 + {cal["sample"]["weekend"]} 个周末日（不含法定假日）。</p></div>
    <div class="card cool"><span class="big">{pr["streak_max"]}<span>天</span></span><h3>最长连续活跃</h3><p>含周末在内的自然日连击。</p></div>
    <div class="card warm"><span class="big">{pr["peak_credits"]:,.0f}</span><h3>峰值日 {esc(pr["peak_day"] or "—")}</h3>
      <p>占全月 <b>{pr["peak_share"]:.1f}%</b>{"——单日集中度高，偏项目攻坚型" if pr["peak_share"] >= 25 else ""}。</p></div>
    <div class="card"><span class="big">{pr["sessions"]:,}<span>段</span></span><h3>使用会话</h3>
      <p>间隔 ≤15 分钟算同一段；平均 <b>{pr["session_avg_min"]:.0f} 分钟</b>，最长 {pr["session_max_min"]} 分钟，日均 {pr["sessions_per_day"]:.1f} 段。</p></div>
  </div>'''

    # ---------- 05 Token 结构与效率 ----------
    inp, out = p["tokens"]["in"], p["tokens"]["out"]
    c_r, c_w = p["tokens"]["cache_read"], p["tokens"]["cache_write"]
    tok = (inp + out + c_r + c_w) or 1
    tok_kv = f'''
  <div class="kv rv" style="margin-top:18px">
    <div>缓存命中率</div><div>{cache_txt} —— 输入 token 里走缓存读取的比例</div>
    <div>输出占比</div><div>{out / tok * 100:.2f}%（输出单价是输入的 2–4 倍，是成本的主要放大器）</div>
    <div>点数效率</div><div>每活跃小时 <b>{cph_txt}</b> 点，每活跃分钟 {tpam_txt} tokens</div>
    <div>时段结构</div><div>{off_txt}</div>
  </div>'''

    # ---------- 06 横向对比 ----------
    def mm(v, unit="", dec=0):
        return f"{v:,.{dec}f}{unit}" if v is not None else "—"

    pct_rows = "".join([
        pct_row("本月点数", f(credits), pct["credits"]),
        pct_row("活跃天数", mm(pr["active_days"], " 天"), pct["active_days"]),
        pct_row("日均活跃分钟", mm(pr["avg_min_day"], " 分钟"), pct["minutes"]),
        pct_row("作息跨度", mm(pr["avg_span_h"], " 小时", 1), pct["span"]),
        pct_row("夜间占比", mm(pr["night_share"], "%", 1), pct["night"], rgb=(255, 122, 69)),
        pct_row("周末占比", mm(pr["weekend_share"], "%", 1), pct["weekend"], rgb=(255, 122, 69)),
        pct_row("混合单价", mm(pr["mix_price"], "", 0), pct["mix_price"], rgb=(199, 146, 234)),
    ])
    if role == "member":
        peers = (f'<span class="hint">组内另有 {len(p["peers"])} 位模型结构相近的同事'
                 f'{"，姓名仅管理者可见" if p["peers"] else ""}。</span>'
                 if p["credits"] > 0 else
                 '<span class="hint">本月暂无用量，无法计算结构相似度。</span>')
    else:
        peers = ('<span class="hint" style="margin-left:10px">组内暂无可比的活跃同事</span>'
                 if not p["peers"] else
                 "".join(f'<a class="file" style="display:inline-flex;gap:10px;margin:4px 6px 0 0;padding:8px 13px" '
                         f'href="member-{esc(q["key"])}.html"><span class="nm">{esc(q["name"])}</span>'
                         f'<span class="ds" style="margin:0">模型结构相似 {q["sim"]}%</span></a>'
                         for q in p["peers"]))

    # ---------- 07 建议 ----------
    advice = []

    def save_move(in_tok, out_tok, src_in_rate, src_out_rate, dst_in_rate, dst_out_rate, ratio=0.3):
        # credits = tokens / 1e6 × rate；省 = 迁移比例 × token 数 × 单价差
        return ratio * (in_tok * (src_in_rate - dst_in_rate)
                        + out_tok * (src_out_rate - dst_out_rate)) / 1e6

    if models:
        m0 = models[0]
        keys, _ = _price_of(rates, m0["name"])
        flash = next((r for r in rates if r["model"] == "deepseek-v4.1-flash"
                      and r["period"] == "offpeak" and r["role"] == "token_in"), None)
        flash_out = next((r for r in rates if r["model"] == "deepseek-v4.1-flash"
                          and r["period"] == "offpeak" and r["role"] == "token_out"), None)
        if keys.get("token_in") and flash and flash_out and keys["token_in"] > flash["rate"] * 2:
            save = save_move(m0["inp"], m0["out"], keys["token_in"], keys["token_out"],
                             flash["rate"], flash_out["rate"], 0.3)
            advice.append(("选型降级", f"主力 <b>{esc(m0['name'])}</b> 输入 {fnum(keys.get('token_in'))} / 输出 {fnum(keys.get('token_out'))} 点/1M。"
                           f"若把 30% 的输入/输出换到 deepseek-v4.1-flash 平峰（{fnum(flash['rate'])} / {fnum(flash_out['rate'])}），"
                           f"全月约省 <b>{f(save)}</b> 点。适合批处理、摘要、评测类负载。"))
    if p["offpeak_ratio"] is not None and p["offpeak_ratio"] < 20 and p["peak"] > 5000:
        advice.append(("平峰迁移", f"deepseek-v4.1-flash 平峰只占 <b>{p['offpeak_ratio']:.1f}%</b>（高峰 {f(p['peak'])} 点）。"
                       f"平峰价格减半，把可延迟任务放到 22:00–08:00，按迁移 30% 测算每月省 <b>{f(p['peak'] * 0.3 * 0.5)}</b> 点。"))
    if pr["night_share"] >= 25:
        advice.append(("夜间用量", f"夜间(22–08)占 <b>{pr['night_share']:.1f}%</b>、部门平均 {beh['night_share']:.1f}%。"
                       f"若为定时/批量任务，建议固定走平峰模型；若为人工加班使用，注意与团队排班沟通。"))
    if p["cache_ratio"] is not None and p["cache_ratio"] < 92 and (c_r + inp) > 1e6:
        advice.append(("缓存命中", f"缓存读占输入 <b>{p['cache_ratio']:.1f}%</b>，低于部门平均（约 95%）。"
                       f"稳定 system prompt、复用相同前缀，可把普通输入转成 10–100 点/1M 的 cache read。"))
    if out / tok > 0.03 and out > 5e5:
        advice.append(("控制输出", f"输出占 token 的 <b>{out / tok * 100:.2f}%</b>。限制 max_tokens、减少冗长解释更直接。"))
    if p["unused"] > p["quota"] * A["waste"]["threshold"]:
        advice.append(("席位结余", f"月末预计结余 <b>{f(p['unused'])}</b> 点 ≈ ¥{p['waste']:,.0f}，当月未用尽不结转。"
                       f"若长期如此可评估降配或共享。"))
    elif p["forecast"] > proc["breakeven"] and not p["premium"]:
        advice.append(("建议升级", f"{nx} 预测 <b>{f(p['forecast'])}</b> 点 > 盈亏平衡 {proc['breakeven']:,.0f} 点，"
                       f"升级高级坐席（+¥{pcfg['premium_seat']['price'] - pcfg['standard_seat']['price']}/月）比走加油包更省。"))
    if len(advice) < 2:
        advice.append(("节奏观察", f"本月在 {pr['active_days']} 天有使用、日均 {pr['avg_min_day']:.0f} 分钟，"
                       f"混合单价 {pr['mix_price'] and fnum(pr['mix_price']) or '—'} 点/1M。"
                       f"模型单价速查：qwen3.8-max 1,200/3,600 · glm-5.3 800/2,800 · flash 平峰 100/400。"))
    adv_html = "".join(f'<div>{k}</div><div>{v}</div>' for k, v in advice)

    status_chip = {"席位结余": "warn", "席位紧张": "warn", "席位用尽": "full"}.get(p["status"], "ok" if has_usage else "none")

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(p["label"])} · 个人用量画像</title>
<style>{CSS}
body{{--accent:{accent}}}
</style></head><body>

<header class="mast"><div class="wrap">
  <div class="eyebrow"><span class="dot"></span><span>阿里云百炼 · Token Plan</span>
    <span>个人用量画像</span><span>{meta["data_start"]} → {meta["data_end"]}</span>
    <span>{f'<a href="team-{esc(p["owner"])}.html">{esc(p["owner"])} 组</a>' if role == "full" else f'{esc(p["owner"])} 组'}</span></div>
  <h1>{esc(p["name"])}<em>.</em></h1>
  <p class="lede">{esc(p["dept"])} · {esc(p["pcode"])} · {esc("高级" if p["premium"] else "标准")}席位
    {f'· 与 {esc(p["shared_with"])} 共享' if p["shared_with"] else ""} ·
    本月消耗 <b>{f(credits)}</b> 点，占部门 <b>{credits / denom * 100:.1f}%</b>；
    {nx} 预测 <b>{f(p["forecast"])}</b> 点。
    <span class="chip {status_chip}" style="vertical-align:2px">{esc(p["status"])}</span></p>
  <div class="stats">
    <div class="stat"><div class="k">本月点数</div><div class="v">{f(credits)}</div></div>
    <div class="stat"><div class="k">部门分位</div><div class="v">{"P" + f'{pct["credits"]:.0f}' if pct["credits"] is not None else "—"}</div></div>
    <div class="stat"><div class="k">活跃天数</div><div class="v">{pr["active_days"]}<small>/ {len(pr["days"])} 个完整日</small></div></div>
    <div class="stat"><div class="k">活跃时长</div><div class="v">{pr["active_minutes"] / 60:,.0f}<small>小时</small></div></div>
    <div class="stat"><div class="k">{nx} 预测</div><div class="v">{f(p["forecast"])}</div></div>
  </div>
</div></header>

<nav class="toc"><div class="wrap">
  <a href="#overview" class="on">概览</a><a href="#models">模型偏好</a><a href="#hours">工作时段</a>
  <a href="#rhythm">使用节奏</a><a href="#tokens">Token 效率</a><a href="#peers">横向对比</a><a href="#advice">建议</a>
</div></nav>

<main>
<section id="overview"><div class="wrap">
  <div class="sec-head"><span class="sec-num">01</span><h2>概览 {pattern_chip(p["pattern"])}</h2></div>
  <div class="grid3 rv">
    <div class="card"><span class="big">{f(credits)}<span>点</span></span><h3>本月消耗</h3>
      <p>占本组 <b>{credits / group["credits"] * 100 if group["credits"] else 0:.1f}%</b>（组 {f(group["credits"])} 点），
      席位已用 {p["seat_pct"]:.0f}%，加油包支取 {f(p["pack"])} 点。</p></div>
    <div class="card cool"><span class="big">{pr["avg_min_day"]:.0f}<span>分钟/日</span></span><h3>使用节奏</h3>
      <p>{pr["active_days"]} 天活跃 · 日均跨度 {span_txt} 小时 ·
      {pr["sessions"]:,} 段会话。作息由计费桶推断，非考勤。</p></div>
    <div class="card {night_hot}"><span class="big">{pr["night_share"]:.1f}<span>%</span></span><h3>夜间占比 22–08</h3>
      <p>晚间(18–22) {pr["evening_share"]:.1f}% · 核心(09–18) {pr["core_share"]:.1f}% ·
      周末 {(pr["weekend_share"] or 0):.1f}%。</p></div>
  </div>
  <div class="kv rv" style="margin-top:22px">
    <div>项目组</div><div>{f'<a href="team-{esc(p["owner"])}.html">{esc(p["owner"])} 组</a>' if role == "full" else f'{esc(p["owner"])} 组'} · {esc(p["dept"])} · {esc(p["pcode"])}</div>
    <div>联系邮箱</div><div class="mono">{esc(p["email"] or "—")}</div>
    <div>Bailian 账号</div><div class="mono">{esc("；".join(p["accounts"])) if p["accounts"] else "未开通"}</div>
    <div>席位</div><div>{"高级" if p["premium"] else "标准"} · 额度 {f(p["quota"])} 点/月 ·
      已用 {f(p["seat"])}（{p["seat_pct"]:.1f}%）{f' · 共享人 {esc(p["shared_with"])}' if p["shared_with"] else ""}</div>
    <div>{nx} 预测</div><div><b>{f(p["forecast"])}</b> 点（工作日日均 {f(p["wd_rate"])} + 周末日均 {f(p["we_rate"])} × 剩余日）</div>
    <div>月末结余</div><div>{f(p["unused"])} 点 ≈ <b>¥{p["waste"]:,.0f}</b>（重置 {_ts(sub.get("refresh"))}，不结转）</div>
  </div>
</div></section>

<section id="models"><div class="wrap">
  <div class="sec-head"><span class="sec-num">02</span><h2>模型偏好</h2></div>
  <p class="sec-note">按点数占比。单价为该模型主力档位的「点数 / 1M tokens」，随上下文档位与高峰/平峰浮动。</p>
  <div class="bars-stack rv" style="height:16px">{''.join(segs) or '<i style="width:100%;background:rgba(255,255,255,.06)"></i>'}</div>
  <div class="lg rv">{''.join(legend) or "<span>本月无用量</span>"}</div>
  <div class="tbl-wrap rv" style="max-height:none;margin-top:20px"><table>
    <thead><tr><th>模型</th><th>时段</th><th>点数</th><th>占比</th><th>tokens</th>
      <th>混合单价 / 1M</th><th>活跃天数</th><th>计费行</th></tr></thead>
    <tbody>{''.join(mrows) or '<tr><td colspan="8" class="dim">本月无模型用量</td></tr>'}</tbody></table></div>
  <div class="kv rv" style="margin-top:20px">{''.join(f'<div>{k}</div><div>{v}</div>' for k, v in sel_kv)}</div>
</div></section>

<section id="hours"><div class="wrap">
  <div class="sec-head"><span class="sec-num">03</span><h2>工作时段</h2></div>
  <p class="sec-note">上图为<b>点数</b>的时间分布（钱花在几点），下图为<b>活跃分钟</b>（人在几点发起调用）。两者错位说明：短时大批量（点数高、分钟少）或长时小批量。</p>
  <p class="heat-cap rv">点数分布（Credits / 小时）</p>
  <div class="rv">{hbars(pr["hours_c"], labels=hours, fmt=lambda v: f'{v:,.0f} 点')}</div>
  <p class="heat-cap rv" style="margin-top:22px">活跃分钟（有调用的分钟数 / 小时）</p>
  <div class="rv">{hbars(pr["hours_m"], labels=hours, rgb="#5fc9a5", fmt=lambda v: f'{v:,.0f} 分钟')}</div>
  {seg_cards}
  <p class="heat-cap rv" style="margin-top:22px">周内 × 24 小时（颜色 = 点数）</p>
  <div class="heat-wrap rv">{heat_grid(WD, hours, pr["wdh"], row_w=48, cell=18, fill=True,
        title=lambda i, j, v: f'{WD[i]} {j:02d}:00 · {f(v)} 点')}</div>
  {sched_kv}
</div></section>

<section id="rhythm"><div class="wrap">
  <div class="sec-head"><span class="sec-num">04</span><h2>使用节奏</h2></div>
  <p class="sec-note">整月「日 × 小时」热力图：每一行是一天，颜色越亮表示该小时的点数消耗越大。可直接看出深夜与周末的使用。</p>
  <div class="heat-wrap rv">{cal_heat}</div>
  {cards4}
</div></section>

<section id="tokens"><div class="wrap">
  <div class="sec-head"><span class="sec-num">05</span><h2>Token 结构与效率</h2></div>
  <div class="rv">
    <div class="bars-stack" style="height:14px">
      <i style="width:{inp / tok * 100:.2f}%;background:#7aa7d8"></i>
      <i style="width:{out / tok * 100:.2f}%;background:#ff7a45"></i>
      <i style="width:{c_r / tok * 100:.2f}%;background:#e8b44a"></i>
      <i style="width:{max(c_w / tok * 100, .2):.2f}%;background:#c792ea"></i>
    </div>
    <div class="lg"><span><i style="background:#7aa7d8"></i>输入 {inp / tok * 100:.2f}%</span>
      <span><i style="background:#ff7a45"></i>输出 {out / tok * 100:.2f}%</span>
      <span><i style="background:#e8b44a"></i>缓存读 {c_r / tok * 100:.2f}%</span>
      <span><i style="background:#c792ea"></i>缓存写 {c_w / tok * 100:.2f}%</span>
      <span>合计 {tok / 1e6:.1f}M tokens</span></div>
  </div>
  {tok_kv}
</div></section>

<section id="peers"><div class="wrap">
  <div class="sec-head"><span class="sec-num">06</span><h2>横向对比</h2></div>
  <p class="sec-note">与部门内<b>有用量的 {len([x for x in A["people"] if x["credits"] > 0])} 人</b>比较的分位（P50 = 中位，P90 = 前 10%）。
  刻意不列名次——横向只看相对位置，不做排行榜。</p>
  <div class="rv" style="max-width:860px">{pct_rows}</div>
  <p class="sec-note rv" style="margin-top:22px">模型结构最接近的同事（余弦相似度，点击可跳转）：</p>
  <div class="rv">{peers}</div>
</div></section>

<section id="advice" style="border-bottom:0"><div class="wrap">
  <div class="sec-head"><span class="sec-num">07</span><h2>给 ta 的建议</h2></div>
  <p class="sec-note">按本人实际数据生成，收益以点数计。</p>
  <div class="kv rv">{adv_html}</div>
</div></section>
</main>

<footer><div class="wrap">
  <span>{f'<a href="team-{esc(p["owner"])}.html">← {esc(p["owner"])} 组报告</a> · ' if role == "full" else ""}<a href="token_credits_report.html">系数与计费口径（基础版）</a></span>
  <span>数据截至 {meta["data_end"]} · 生成于 {meta["generated_at"]} · 作息为计费桶推断，非考勤</span>
</div></footer>
<script>{JS}</script></body></html>"""


def _ts(ms):
    import datetime as dt
    if not ms:
        return "—"
    return dt.datetime.fromtimestamp(ms / 1000).astimezone().strftime("%Y-%m-%d %H:%M")
