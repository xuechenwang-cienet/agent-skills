"""项目组报告渲染。"""
from __future__ import annotations

import collections
import html

from .ui import CSS, JS

PER = {"peak": ("PEAK", "高峰"), "offpeak": ("OFFPEAK", "平峰"), "flat": ("FLAT", "不分时段")}
PALETTE = ["#ff7a45", "#5fc9a5", "#7aa7d8", "#e8b44a", "#c792ea", "#9aa5b1", "#8b9dc3", "#d98b8b"]


def esc(s):
    return html.escape(str(s))


def f(v, dec=0):
    if v is None:
        return "—"
    return f"{v:,.{dec}f}"


def fnum(v):
    if v is None:
        return "—"
    return f"{v:,.0f}" if abs(v - round(v)) < 1e-6 else f"{v:,.2f}"


def _ts(ms):
    import datetime as dt
    if not ms:
        return "—"
    return dt.datetime.fromtimestamp(ms / 1000).astimezone().strftime("%Y-%m-%d %H:%M")


def render(A, cfg, group_name: str, accent: str) -> str:
    meta, cal, sub, proc = A["meta"], A["calendar"], A["subscription"], A["procurement"]
    by_key = {p["key"]: p for p in A["people"]}
    g = next(x for x in A["groups"] if x["name"] == group_name)
    ps = [by_key[k] for k in g["people"]]
    total = meta["total_credits"]
    denom = total or 1
    nx = cal["next_month"]["month"]
    cr = g["credits"]
    pcfg = cfg.pricing
    pack_unit = pcfg["pack"]["price"] / pcfg["pack"]["credits"]

    def rnd(v):
        return round(v) if abs(v - round(v)) < 1e-6 else round(v, 4)

    # ---------- 成员表 ----------
    mrows = []
    for p in sorted(ps, key=lambda x: -x["credits"]):
        cache = f'{p["cache_ratio"]:.1f}%' if p["cache_ratio"] is not None else "—"
        off = f'{p["offpeak_ratio"]:.1f}%' if p["offpeak_ratio"] is not None else "—"
        has_unused = p["unused"] > p["quota"] * A["waste"]["threshold"]
        waste_td = (f'<td class="num" style="color:var(--ember)">¥{p["waste"]:,.0f}</td>'
                    if has_unused else '<td class="num dim">—</td>')
        shared = f'<span class="shared">共享 · {esc(p["shared_with"])}</span>' if p["shared_with"] else ""
        mrows.append(f'''<tr{' class="hl"' if has_unused else ''}>
          <td class="m">{esc(p["name"])}{shared}</td>
          <td class="l dim" style="font-size:12px;line-height:1.45">{esc(p["dept"])}<br>
            <span style="font-family:var(--mono);font-size:10.5px;color:var(--dim2)">{esc(p["pcode"])}</span></td>
          <td class="num dim">{"高级<br>100,000" if p["premium"] else "标准<br>25,000"}</td>
          <td class="num"><span style="color:{'var(--ember)' if p["seat_pct"] >= 99.5 else ('var(--amber)' if p["seat_pct"] >= 80 else 'var(--dim)')}">{p["seat_pct"]:.0f}%</span></td>
          <td class="num">{f(p["credits"])}</td>
          <td class="num dim">{(p["credits"] / cr * 100) if cr else 0:.1f}%</td>
          <td class="num">¥{p["cost_now"]:,.0f}</td>
          <td class="l dim" style="font-family:var(--mono);font-size:11px">{esc(p["top_model"])}</td>
          <td class="num dim">{cache}</td>
          <td class="num">{off}</td>
          <td class="num">{f(p["forecast"])}</td>
          {waste_td}
          <td><span class="chip {'none' if p['status'] in ('未开通',) else ('warn' if p['status'] in ('席位结余', '席位紧张') else ('full' if p['status'] == '席位用尽' else 'ok'))}">{esc(p["status"])}</span></td></tr>''')

    cmax = max((p["credits"] for p in ps), default=1) or 1
    rank = []
    for p in sorted(ps, key=lambda x: -x["credits"])[:14]:
        rank.append(f'''<div class="rank-row"><span class="rank-name">{esc(p["name"])}</span>
          <span class="rank-track"><span class="rank-fill" style="width:{max(p["credits"] / cmax * 100, .4):.1f}%"></span></span>
          <span class="rank-val">{f(p["credits"])}</span>
          <span class="rank-pct">{(p["credits"] / cr * 100) if cr else 0:.1f}%</span></div>''')

    # ---------- 组内模型 ----------
    gmodels = collections.Counter()
    for p in ps:
        gmodels.update(p["models"])
    model_by_name = {m["name"]: m for m in A["models"]}
    rates = A["rates"]
    gtier = collections.defaultdict(float)
    for r in rates:
        gtier[(r["model"], r["ctx"], r["period"])] += r["credits"]
    gmodel_rows = []
    for mname, v in gmodels.most_common():
        cand = [(k, c) for k, c in gtier.items() if k[0] == mname]
        best = max(cand, key=lambda x: x[1])[0]      # (model, ctx, period)
        ctx, per = best[1], best[2]
        keys = {r["role"]: r["rate"] for r in rates
                if r["model"] == mname and r["ctx"] == ctx and r["period"] == per}
        users = sum(1 for p in ps if p["models"].get(mname, 0) > 0)
        tier = f' <span class="ctx">{esc(ctx)}</span>' if ctx else ""
        gmodel_rows.append(f'''<tr><td class="m">{esc(mname)}{tier}</td>
          <td><span class="chip {per}">{PER[per][0]}</span></td>
          <td class="num">{f(v)}</td><td class="num dim">{(v / cr * 100) if cr else 0:.1f}%</td>
          <td class="num dim">{users}</td>
          <td class="num">{fnum(keys.get("token_in"))}</td>
          <td class="num">{fnum(keys.get("token_out"))}</td>
          <td class="num dim">{fnum(keys.get("cache_read") or keys.get("cache"))}</td>
          <td class="num dim">{fnum(keys.get("cache_write_5m"))}</td></tr>''')

    # ---------- token / 时段 ----------
    inp = sum(p["tokens"]["in"] for p in ps)
    out = sum(p["tokens"]["out"] for p in ps)
    c_r = sum(p["tokens"]["cache_read"] for p in ps)
    c_w = sum(p["tokens"]["cache_write"] for p in ps)
    tok = (inp + c_r + c_w + out) or 1
    offp, pkw = sum(p["offpeak"] for p in ps), sum(p["peak"] for p in ps)
    off_r = offp / (offp + pkw) * 100 if (offp + pkw) else None
    cache_avg = [p["cache_ratio"] for p in ps if p["cache_ratio"] is not None]
    cache_g = sum(cache_avg) / len(cache_avg) if cache_avg else 0

    # ---------- 席位结余 ----------
    unused_ps = [p for p in ps if p["unused"] > p["quota"] * A["waste"]["threshold"]]
    grp_waste = sum(p["waste"] for p in unused_ps)
    if unused_ps:
        names = "".join(
            f'<tr><td class="m">{esc(p["label"])}</td><td class="num dim">{p["quota"]:,}</td>'
            f'<td class="num dim">{f(p["projected"])}</td><td class="num">{f(p["unused"])}</td>'
            f'<td class="num" style="color:var(--ember)">¥{p["waste"]:,.0f}</td></tr>'
            for p in sorted(unused_ps, key=lambda x: -x["unused"]))
        seat_panel = f'''
  <div class="panel-warn rv">
    <div class="pw-head"><span class="pw-k">本组 {len(unused_ps)} 个席位月末预计用不尽额度</span>
      <span class="pw-v">¥{grp_waste:,.0f}</span></div>
    <p class="pw-note">席位额度 <b>{_ts(sub.get("refresh"))} 重置，未用尽部分不结转</b>，所以这部分等同于已付未用。
      估算方式：<b>当前已用 + 工作日日均 × {cal["remaining"].get("workday", 0)} + 周末日均 × {cal["remaining"].get("weekend", 0)}</b>
      （剩余 {cal["remaining"].get("total", 0)} 天）；结余需超过额度 {A["waste"]["threshold"] * 100:.0f}% 才计入。
      折合单价按各席位类型：标准 ¥{pcfg["standard_seat"]["price"]}/{pcfg["standard_seat"]["credits"]:,} 点，
      高级 ¥{pcfg["premium_seat"]["price"]}/{pcfg["premium_seat"]["credits"]:,} 点。</p>
    <div class="tbl-wrap" style="max-height:none;margin-top:12px;background:transparent"><table>
      <thead><tr><th>席位（含共享人）</th><th>额度</th><th>月末预计用</th><th>预计结余</th><th>折合金额</th></tr></thead>
      <tbody>{names}</tbody></table></div>
  </div>'''
    else:
        seat_panel = f'''
  <div class="panel-ok rv"><span class="pw-k">本组席位预计全部可用尽</span>
    <p class="pw-note">按剩余 {cal["remaining"].get("total", 0)} 天测算，本组各席位都能在本月内用满额度。</p></div>'''

    # ---------- 采购 ----------
    g_pack = g["pack_forecast"]
    g_fee = g["seat_fee"]
    g_cost = g_fee + g_pack * pack_unit
    share_pool = (g_pack / proc["pack_forecast"] * 100) if proc["pack_forecast"] else 0
    upg = [p for p in ps if p["forecast"] > proc["breakeven"] and not p["premium"]]
    upg_html = ""
    if upg:
        upg_html = ("<p class='sec-note' style='margin-top:18px'>其中 <b>" +
                    "、".join(esc(p["label"]) for p in upg) + "</b>" +
                    f" 的 {nx} 预测超过 {proc['breakeven']:,.0f} 点，建议升级为高级坐席" +
                    f"（+¥{pcfg['premium_seat']['price'] - pcfg['standard_seat']['price']}/人，容量 25,000→100,000），" +
                    f"可让本组少动 <b>{f(len(upg) * (pcfg['premium_seat']['credits'] - pcfg['standard_seat']['credits']))}</b> 点加油包。</p>")

    n_std = sum(1 for p in ps if not p["premium"])
    n_prm = sum(1 for p in ps if p["premium"])

    # ---------- 技术建议 ----------
    advice = []
    if off_r is not None and off_r < 5 and (offp + pkw) > 5000:
        advice.append(("平峰迁移", f"本组 deepseek-v4.1-flash 平峰只占 <b>{off_r:.1f}%</b>（高峰 {f(pkw)} 点 / 平峰 {f(offp)} 点）。"
                       f"平峰 in <b>100 点/1M</b>、out <b>400 点/1M</b>，是高峰的一半。把可延迟任务放到 22:00–08:00，"
                       f"按迁移 30% 测算每月省 <b>{f(pkw * 0.3 * 0.5)}</b> 点。"))
    if cache_g and cache_g < 92:
        advice.append(("缓存命中", f"本组缓存读占输入 token 的 <b>{cache_g:.1f}%</b>，低于部门平均（约 95%）。"
                       f"保持 system prompt 稳定、复用相同前缀，可把更多输入转成 cache read 而不是普通输入。"))
    top1 = gmodels.most_common(1)
    if top1:
        m1 = top1[0][0]
        if m1 in ("qwen3.8-max", "glm-5.2"):
            advice.append(("选型价差", f"本组主力是 <b>{esc(m1)}</b>。同类任务若能换 glm-5.3（in 800 / out 2,800），"
                           f"单 token 便宜 33% / 22%；对延迟不敏感的批处理切到 deepseek-v4.1-flash 平峰（in 100 / out 400）差距更大。"))
    if unused_ps:
        advice.append(("席位结余", f"本组 <b>{len(unused_ps)} 个席位</b>月末预计用不尽，折合 ¥{grp_waste:,.0f}。"
                       f"若这些席位长期低负载，可评估回收或转分配给未分配坐席的同事。"))
    if len(advice) < 2 and tok:
        advice.append(("输出成本", f"本组输出 token 只占 token 总量的 <b>{out / tok * 100:.2f}%</b>，"
                       f"但 output 单价是 cache read 的 <b>20–36 倍</b>。限制 max_tokens、减少冗长解释更有效。"))
    adv_html = "".join(f'<div>{k}</div><div>{v}</div>' for k, v in advice)

    st_a = cal["next_month"]

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(group_name)} 组 · Token Plan 用量报告</title>
<style>{CSS}
body{{--accent:{accent}}}
</style></head><body>

<header class="mast"><div class="wrap">
  <div class="eyebrow"><span class="dot"></span><span>阿里云百炼 · Token Plan</span>
    <span>项目组用量报告</span><span>{meta["data_start"]} → {meta["data_end"]}</span></div>
  <h1>{esc(group_name)} <em>组</em></h1>
  <p class="lede">{g["count"]} 个席位 · {esc("、".join(sorted({p["dept"] for p in ps if p["dept"] != "—"})) or "—")} ·
  本月消耗 <b>{f(cr)}</b> 点，占部门 <b>{(cr / denom * 100) if total else 0:.1f}%</b>；
  {nx} 预测 <b>{f(g["forecast"])}</b> 点。</p>
  <div class="stats">
    <div class="stat"><div class="k">本月点数</div><div class="v">{f(cr)}</div></div>
    <div class="stat"><div class="k">占部门</div><div class="v">{(cr / denom * 100) if total else 0:.1f}<small>%</small></div></div>
    <div class="stat"><div class="k">{nx} 预测</div><div class="v">{f(g["forecast"])}</div></div>
    <div class="stat"><div class="k">折算费用</div><div class="v">¥{g_cost:,.0f}</div></div>
    <div class="stat"><div class="k">席位已用尽</div><div class="v">{sum(1 for p in ps if p["status"] == "席位用尽")}<small>/ {g["count"]}</small></div></div>
  </div>
</div></header>

<nav class="toc"><div class="wrap">
  <a href="#members" class="on">成员明细</a><a href="#rank">用量排行</a><a href="#models">模型结构</a>
  <a href="#tokens">Token 结构</a><a href="#buy">采购建议</a><a href="#tech">技术建议</a>
</div></nav>

<main>
<section id="members"><div class="wrap">
  <div class="sec-head"><span class="sec-num">01</span><h2>成员明细</h2></div>
  <p class="sec-note">本组全部 {g["count"]} 个席位。「席位已用」是本月席位额度消耗比例，「折算 ¥」= 席位月费 + 加油包支取 × ¥{pack_unit:.4f}；
  「月末结余」= 按剩余 {cal["remaining"].get("total", 0)} 天测算的未用尽额度折合金额，标红的行表示该席位预计用不完。</p>
  <div class="controls"><input class="search" id="q" type="search" placeholder="筛选成员…" aria-label="筛选成员"><span class="hint" id="cnt"></span></div>
  <div class="tbl-wrap" data-filterable style="max-height:none"><table>
    <thead><tr><th>姓名 / 共享人</th><th>部门 / P-code</th><th>席位</th><th>已用</th>
      <th>本月点数</th><th>占组比</th><th>折算 ¥</th><th>主力模型</th><th>缓存读</th><th>平峰</th>
      <th>{nx} 预测</th><th>月末结余</th><th>状态</th></tr></thead>
    <tbody>{''.join(mrows)}</tbody></table></div>
  <p class="sec-note" style="margin-top:12px">「平峰」只对带 peak/offpeak 区分的模型有意义（目前仅 deepseek-v4.1-flash），其余显示 —。</p>
</div></section>

<section id="rank"><div class="wrap">
  <div class="sec-head"><span class="sec-num">02</span><h2>用量排行</h2></div>
  <p class="sec-note">按本月点数降序，用于识别本组的用量重心。</p>
  <div class="rank rv">{''.join(rank)}</div>
</div></section>

<section id="models"><div class="wrap">
  <div class="sec-head"><span class="sec-num">03</span><h2>组内模型结构</h2></div>
  <p class="sec-note">本组各模型的点数消耗与单价。单价统一为 <b>点数 / 1M tokens</b>。</p>
  <div class="tbl-wrap" style="max-height:none"><table>
    <thead><tr><th>模型</th><th>时段</th><th>点数</th><th>占组比</th><th>使用人数</th>
      <th>token in</th><th>token out</th><th>cache read</th><th>cache write</th></tr></thead>
    <tbody>{''.join(gmodel_rows)}</tbody></table></div>
</div></section>

<section id="tokens"><div class="wrap">
  <div class="sec-head"><span class="sec-num">04</span><h2>Token 结构与时段</h2></div>
  <div class="grid2">
    <div>
      <p class="sec-note" style="margin-bottom:10px">本组 token 构成（合计 {tok / 1e6:.1f}M tokens）</p>
      <div class="bars-stack" style="height:14px">
        <i style="width:{inp / tok * 100:.2f}%;background:#7aa7d8"></i>
        <i style="width:{out / tok * 100:.2f}%;background:#ff7a45"></i>
        <i style="width:{c_r / tok * 100:.2f}%;background:#e8b44a"></i>
        <i style="width:{max(c_w / tok * 100, .2):.2f}%;background:#c792ea"></i>
      </div>
      <div class="lg"><span><i style="background:#7aa7d8"></i>输入 {inp / tok * 100:.2f}%</span>
        <span><i style="background:#ff7a45"></i>输出 {out / tok * 100:.2f}%</span>
        <span><i style="background:#e8b44a"></i>缓存读 {c_r / tok * 100:.2f}%</span>
        <span><i style="background:#c792ea"></i>缓存写 {c_w / tok * 100:.2f}%</span></div>
      <div class="kv" style="margin-top:20px">
        <div>缓存读占比</div><div><b>{cache_g:.1f}%</b> — 输入 token 里有多少走了缓存读取</div>
        <div>席位消耗</div><div>{f(g["seat"])} 点 / 额度 {f(g["quota"])} 点（{(g["seat"] / g["quota"] * 100) if g["quota"] else 0:.1f}%）</div>
        <div>加油包消耗</div><div>{f(g["pack"])} 点，从组织共享池支取</div>
      </div>
    </div>
    <div>
      <p class="sec-note" style="margin-bottom:10px">时段分布（仅 deepseek-v4.1-flash 可区分）</p>
      {(f'<div class="bars-stack" style="height:14px"><i style="width:{pkw / (pkw + offp) * 100:.2f}%;background:#ff7a45"></i><i style="width:{offp / (pkw + offp) * 100:.2f}%;background:#5fc9a5"></i></div><div class="lg"><span><i style="background:#ff7a45"></i>高峰 {f(pkw)} 点</span><span><i style="background:#5fc9a5"></i>平峰 {f(offp)} 点（{off_r:.1f}%）</span></div>') if (pkw + offp) > 0 else '<p class="sec-note">本组未使用带时段区分的模型。</p>'}
      <div class="kv" style="margin-top:20px">
        <div>主力模型</div><div>{esc(gmodels.most_common(1)[0][0]) if gmodels else "—"}</div>
        <div>活跃席位</div><div>{sum(1 for p in ps if p["credits"] > 0)} / {g["count"]}</div>
        <div>人均点数</div><div>{f(cr / g["count"] if g["count"] else 0)} 点</div>
      </div>
    </div>
  </div>
</div></section>

<section id="buy"><div class="wrap">
  <div class="sec-head"><span class="sec-num">05</span><h2>{nx} 采购建议</h2></div>
  <p class="sec-note">{nx} 共 <b>{st_a["workday"]} 个工作日 + {st_a["weekend"]} 个周末</b>{("，" + str(st_a["holiday"]) + " 天法定假日") if st_a.get("holiday") else "，无法定节假日"}。
  本月因假日 {cal["this_month"].get("holiday", 0)} 天，所以<b>不能用本月均值外推</b>，本预测用假期后按工作日/周末分开的日均建模。</p>
  <div class="grid3 rv" style="margin-bottom:20px">
    <div class="card"><span class="big">{f(g["forecast"])}<span>点</span></span><h3>{nx} 预测</h3>
      <p>按当前节奏，相对本月（{f(cr)} 点）的变化已扣除假日因素。</p></div>
    <div class="card warm"><span class="big">{f(g_pack)}<span>点</span></span><h3>需从共享池支取</h3>
      <p>席位额度 {f(g["quota"])} 点覆盖后仍需支取，占组织加油包总需求的 <b>{share_pool:.1f}%</b>。</p></div>
    <div class="card hot"><span class="big">¥{g_cost:,.0f}</span><h3>{nx} 折算成本</h3>
      <p>席位 ¥{g_fee:,} + 加油包 ¥{g_pack * pack_unit:,.0f}</p></div>
  </div>
  <div class="tbl-wrap" style="max-height:none"><table>
    <thead><tr><th class="l">项目</th><th>数量 / 容量</th><th class="l">说明</th></tr></thead>
    <tbody>
      <tr><td class="m">标准席位</td><td class="num">{n_std} × ¥{pcfg["standard_seat"]["price"]}</td>
        <td class="l dim">¥{n_std * pcfg["standard_seat"]["price"]:,}/月，每席 25,000 点/月</td></tr>
      <tr><td class="m">高级坐席</td><td class="num">{n_prm} × ¥{pcfg["premium_seat"]["price"]}</td>
        <td class="l dim">¥{n_prm * pcfg["premium_seat"]["price"]:,}/月，每席 100,000 点/月</td></tr>
      <tr><td class="m">席位合计</td><td class="num">¥{g_fee:,}</td><td class="l dim">容量 {f(g["quota"])} 点</td></tr>
      <tr><td class="m">加油包（共享池）</td><td class="num">{g_pack / pcfg["pack"]["credits"]:.2f} 个</td>
        <td class="l dim">¥{g_pack * pack_unit:,.0f}，按 ¥{pcfg["pack"]["price"]:,}/{pcfg["pack"]["credits"]:,} 点折算；组织共享，不单独采购</td></tr>
      <tr><td class="m">折算合计</td><td class="num strong">¥{g_cost:,.0f}</td>
        <td class="l dim">实际由组织共享池统一购买</td></tr>
    </tbody></table></div>
  {seat_panel}
  {upg_html}
  <div class="kv rv" style="margin-top:22px">
    <div>共享池现状</div><div>组织加油包总量 {f((sub.get("pack") or {}).get("cap", 0))} 点，剩余 <b>{f((sub.get("pack") or {}).get("remaining", 0))}</b> 点，
      最近到期 {_ts((sub.get("pack") or {}).get("nearest_expire"))}，余量按有效期<b>可结转至下月</b>。</div>
    <div>本组占用</div><div>{nx} 需从共享池支取 <b>{f(g_pack)}</b> 点，占组织总需求（{f(proc["pack_forecast"])} 点）的 <b>{share_pool:.1f}%</b>。</div>
    <div>节假日</div><div>本报告的日均与预测已按法定节假日/调休校准。目标月份{'已' if cal["verified"] else '<b>尚未</b>'}在节假日配置的已核对清单内，下月{'已' if cal["next_verified"] else '<b>尚未</b>'}覆盖。</div>
  </div>
</div></section>

<section id="tech" style="border-bottom:0"><div class="wrap">
  <div class="sec-head"><span class="sec-num">06</span><h2>组内技术建议</h2></div>
  <p class="sec-note">按本组实际数据生成，收益均以点数计。</p>
  <div class="kv rv">{adv_html}</div>
  <p class="sec-note" style="margin-top:20px">
    模型单价速查（点数 / 1M tokens）：qwen3.8-max <b>1,200 / 3,600</b> · glm-5.3 <b>800 / 2,800</b> ·
    deepseek-v4.1-flash 高峰 <b>200 / 800</b>、平峰 <b>100 / 400</b>。缓存读普遍只有 <b>10–100</b> 点，缓存写 <b>750–1,500</b> 点。
  </p>
</div></section>
</main>

<footer><div class="wrap">
  <span><a href="token_credits_report.html">← 返回部门报告</a></span>
  <span>数据截至 {meta["data_end"]} · 生成于 {meta["generated_at"]}</span>
</div></footer>
<script>{JS}</script></body></html>"""