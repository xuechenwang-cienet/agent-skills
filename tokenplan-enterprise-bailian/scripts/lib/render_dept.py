"""部门报告渲染。输入 analysis dict，输出 HTML 字符串。"""
from __future__ import annotations

import collections
import html

from .ui import CSS, JS

PER = {"peak": ("PEAK", "高峰"), "offpeak": ("OFFPEAK", "平峰"), "flat": ("FLAT", "不分时段")}
COLS = ["token_in", "token_out", "cache", "cache_read", "cache_write_5m", "cache_write_1h"]
ROLE_LABEL = {"token_in": "token in", "token_out": "token out", "cache": "cache",
              "cache_read": "cache read", "cache_write_5m": "cache write 5m",
              "cache_write_1h": "cache write 1h"}


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


def render(A, cfg) -> str:
    meta, cal, sub, proc = A["meta"], A["calendar"], A["subscription"], A["procurement"]
    people = A["people"]
    groups = A["groups"]
    models = A["models"]
    rates = A["rates"]
    total = meta["total_credits"]
    denom = total or 1
    mon = meta["month"]
    nx = cal["next_month"]["month"]

    # ---------- 01 系数总表 ----------
    combos = collections.OrderedDict()
    for r in sorted(rates, key=lambda x: (models.index(next(m for m in models if m["name"] == x["model"])), x["ctx"], {"offpeak": 0, "peak": 1, "flat": 2}[x["period"]])):
        combos.setdefault((r["model"], r["ctx"], r["period"]), {})[r["role"]] = r["rate"]

    trs = []
    for (model, ctx, per), cells in combos.items():
        tds = ""
        for col in COLS:
            v = cells.get(col)
            tds += ('<td class="num dim">—</td>' if v is None else
                    f'<td class="num"><span data-c="{v:.4g}" data-i="{1e6 / v:,.0f}">{fnum(v)}</span></td>')
        ctx_html = f'<span class="ctx">{esc(ctx)}</span>' if ctx else '<span class="dim">—</span>'
        trs.append(f'<tr><td class="m">{esc(model)}</td>'
                   f'<td><span class="chip {per}">{PER[per][0]}</span></td>'
                   f'<td>{ctx_html}</td>{tds}</tr>')

    raws = []
    for r in sorted(rates, key=lambda x: (models.index(next(m for m in models if m["name"] == x["model"])), x["base"])):
        raws.append(f'<tr><td class="m">{esc(r["model"])}</td>'
                    f'<td><span class="chip {r["period"]}">{PER[r["period"]][0]}</span></td>'
                    f'<td class="dim">{esc(r["ctx"]) or "—"}</td>'
                    f'<td class="mono l" style="color:var(--dim)">{esc(r["base"])}</td>'
                    f'<td class="num">{fnum(r["rate"])}</td>'
                    f'<td class="num dim">{1e6 / r["rate"]:,.0f}</td></tr>')

    # ---------- 06 组 ----------
    gmax = max((g["credits"] for g in groups), default=1) or 1
    grows = []
    for g in groups:
        caches = [p["cache_ratio"] for p in people if p["owner"] == g["name"] and p["cache_ratio"] is not None]
        top = max(g["models"].items(), key=lambda kv: kv[1])[0] if g["models"] else "—"
        w = g["credits"] / gmax * 100
        grows.append(f'''<tr>
          <td class="m"><a href="team-{esc(g["name"])}.html">{esc(g["name"])} 组</a>
            {'<span style="display:block;height:3px;width:%.0f%%;background:var(--accent);opacity:.5;margin-top:4px;border-radius:1px"></span>' % w if w > 0 else ''}</td>
          <td class="num">{g["count"]}</td><td class="num">{f(g["credits"])}</td>
          <td class="num dim">{g["credits"] / denom * 100:.1f}%</td>
          <td class="num">{f(g["credits"] / g["count"] if g["count"] else 0)}</td>
          <td class="num dim">{f(g["seat"])}</td><td class="num dim">{f(g["pack"])}</td>
          <td class="num">{f(g["forecast"])}</td>
          <td class="num dim">{f(sum(caches) / len(caches), 1) if caches else "—"}%</td>
          <td class="l dim" style="font-family:var(--mono);font-size:11.5px">{esc(top)}</td></tr>''')

    # ---------- 07 模型 ----------
    mrows = []
    for m in models:
        mrows.append(f'''<tr><td class="m">{esc(m["name"])}</td>
          <td class="num">{f(m["credits"])}</td><td class="num dim">{m["credits"] / denom * 100:.1f}%</td>
          <td class="num dim">{m["users"]}</td><td class="num dim">{len(m["groups"])}</td>
          <td class="num strong">{f(m["mix_price"])}</td><td class="num dim">{f(m["tokens"] / 1e6, 2)}M</td></tr>''')

    # 单价对比条：每个模型取消耗最大的档位
    tier = collections.defaultdict(float)
    for r in rates:
        tier[(r["model"], r["ctx"], r["period"])] += r["credits"]
    dom = {}
    for (m, ctx, per), c in tier.items():
        if m not in dom or c > dom[m][1]:
            dom[m] = ((ctx, per), c)
    pairs = []
    for m in models:
        if m["name"] not in dom:
            continue
        (ctx, per), _ = dom[m["name"]]
        pin = next((r["rate"] for r in rates if r["model"] == m["name"] and r["ctx"] == ctx and r["period"] == per and r["role"] == "token_in"), None)
        pout = next((r["rate"] for r in rates if r["model"] == m["name"] and r["ctx"] == ctx and r["period"] == per and r["role"] == "token_out"), None)
        pairs.append((m["name"], ctx, per, pin, pout))
    pairs.sort(key=lambda x: -(x[4] or 0))
    pmax = max(((p[4] or 0) for p in pairs), default=1) or 1
    prows = ['<div class="pr-h"><span>模型</span><span>输入 (in)</span><span></span><span>输出 (out)</span><span></span></div>']
    for m, ctx, per, pin, pout in pairs:
        badge = f'<span class="chip {per}" style="margin-left:6px">{PER[per][0]}</span>' if per != "flat" else ""
        tierb = f'<span class="ctx" style="margin-left:6px">{esc(ctx)}</span>' if ctx else ""
        prows.append(f'''<div class="pr">
          <span class="pn">{esc(m)}{badge}{tierb}</span>
          <span class="pt"><i style="width:{max((pin or 0) / pmax * 100, 0.6):.1f}%;background:#7aa7d8"></i></span>
          <span class="pv" style="color:#7aa7d8">{fnum(pin)}</span>
          <span class="pt"><i style="width:{max((pout or 0) / pmax * 100, 0.6):.1f}%;background:#ff7a45"></i></span>
          <span class="pv" style="color:#ff7a45">{fnum(pout)}</span></div>''')

    srows = []
    for m in models[:10]:
        t = m["tokens"] or 1
        srows.append(f'''<div style="display:grid;grid-template-columns:150px 1fr;gap:12px;align-items:center;padding:6px 0">
          <span style="font-family:var(--serif);font-size:13.5px">{esc(m["name"])}</span>
          <span class="bars-stack">
            <i style="width:{m["in"] / t * 100:.2f}%;background:#7aa7d8"></i>
            <i style="width:{m["out"] / t * 100:.2f}%;background:#ff7a45"></i>
            <i style="width:{m["cache_read"] / t * 100:.2f}%;background:#e8b44a"></i>
            <i style="width:{max(m["cache_write"] / t * 100, .4):.2f}%;background:#c792ea"></i>
          </span></div>''')

    # ---------- 08 矩阵 ----------
    topm = models[:8]
    gorder = [g["name"] for g in groups]
    mh = "".join(f"<th>{esc(g)}</th>" for g in gorder)
    mrow = []
    for m in topm:
        vals = [m["by_group"].get(g, 0) for g in gorder]
        mx = max(vals) or 1
        tds = "".join('<td class="z">·</td>' if v < 0.5 else
                      f'<td style="background:rgba(232,180,74,{0.06 + 0.6 * v / mx:.2f})">{f(v)}</td>' for v in vals)
        mrow.append(f'<tr><td>{esc(m["name"])}</td>{tds}</tr>')

    # ---------- 09 订阅 ----------
    seats = {s["type"]: s for s in sub.get("seats", [])}
    std, prm = seats.get("standard", {}), seats.get("pro", {})
    pack = sub.get("pack", {})
    seat_cap = proc["seat_cap"]
    seat_used_now = sum(s.get("used", 0) for s in sub.get("seats", []))
    seat_pct_now = seat_used_now / seat_cap * 100 if seat_cap else 0

    # ---------- 10 席位结余 ----------
    wp = {p["key"]: p for p in people}
    waste_people = [wp[k] for k in A["waste"]["people"]]
    by_group = collections.OrderedDict()
    for p in waste_people:
        by_group.setdefault(p["owner"], []).append(p)
    seat_rows = []
    for g in groups:
        ups = by_group.get(g["name"], [])
        if ups:
            amt = sum(x["waste"] for x in ups)
            seat_rows.append(f'<tr><td class="m">{esc(g["name"])} 组</td>'
                             f'<td class="num">{len(ups)}<span class="dim" style="font-size:11px"> / {g["count"]}</span></td>'
                             f'<td class="num strong">¥{amt:,.0f}</td>'
                             f'<td class="l dim" style="font-size:12px;white-space:normal">'
                             f'{"、".join(esc(x["label"]) for x in ups)}</td></tr>')
        else:
            seat_rows.append(f'<tr><td class="m">{esc(g["name"])} 组</td>'
                             f'<td class="num dim">0<span class="dim" style="font-size:11px"> / {g["count"]}</span></td>'
                             f'<td class="num dim">—</td><td class="l dim">全部席位预计可用尽</td></tr>')

    # ---------- 11 采购 ----------
    a, b = proc["plan_a"], proc["plan_b"]
    upg = [wp[k] for k in b["upgrades"]]
    adv_rows = "".join(
        f'<tr><td class="m">{esc(p["label"])}</td><td class="dim">{esc(p["owner"])} 组</td>'
        f'<td class="num">{f(p["forecast"])}</td><td class="num dim">{p["quota"]:,}</td>'
        f'<td class="num">{f(p["forecast"] - p["quota"])}</td></tr>'
        for p in sorted(upg, key=lambda x: -x["forecast"]))
    idle = [p for p in people if p["credits"] == 0 and p["accounts"]]

    v41 = next((m for m in models if m["name"] == "deepseek-v4.1-flash"), None)
    peak_ratio = (v41["offpeak"] / (v41["offpeak"] + v41["peak"]) * 100) if v41 and (v41["offpeak"] + v41["peak"]) else 0
    full_cnt = sum(1 for p in people if p["status"] == "席位用尽")

    st_m, st_a = cal["this_month"], cal["next_month"]
    warn_html = "".join(f'<div class="panel-warn rv" style="margin-top:14px"><span class="pw-k">⚠ {esc(w)}</span></div>'
                        for w in A["warnings"])

    unmapped_html = ""
    if A["unmapped"]:
        rows = "".join(f'<tr><td class="mono">{esc(u["account_id"])}</td><td class="num">{f(u["credits"])}</td>'
                       f'<td class="num dim">{u["rows"]}</td></tr>' for u in A["unmapped"])
        unmapped_html = f'''
  <h3 style="font-family:var(--sans);font-size:14px;font-weight:600;margin:28px 0 10px">未归属账号</h3>
  <p class="sec-note" style="margin-bottom:10px">以下 Bailian 账号在名册中找不到对应的人，<b>未计入任何组</b>，仅在此列出。</p>
  <div class="tbl-wrap" style="max-height:40vh"><table>
    <thead><tr><th>Bailian 账号</th><th>点数</th><th>明细行数</th></tr></thead>
    <tbody>{rows}</tbody></table></div>'''

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Token ↔ Credits 兑换率 · 部门报告 · {mon}</title>
<style>{CSS}</style></head>
<body>
<header class="mast"><div class="wrap">
  <div class="eyebrow"><span class="dot"></span><span>阿里云百炼 · Token Plan</span>
    <span>组织用量分析</span><span>{meta["data_start"]} → {meta["data_end"]}</span><span><b>全量导出</b></span></div>
  <h1>Token <span class="arrow">↔</span> <em>Credits</em><br>兑换率与部门用量</h1>
  <p class="lede">从组织用量明细的<b>全量导出</b>反推每个模型、每种 token 类型、每个时段的结算系数；
  并按<b>项目组</b>汇总用量、比较模型、测算下月采购。系数由「Credits 合计 ÷ 原始用量合计」直接算出，
  同一组合内逐行核算零波动。</p>
  <div class="stats">
    <div class="stat"><div class="k">明细行数</div><div class="v">{meta["rows"]:,}</div></div>
    <div class="stat"><div class="k">模型 / 席位</div><div class="v">{meta["models"]}<span class="slash">/</span>{meta["members"]}</div></div>
    <div class="stat"><div class="k">本月点数</div><div class="v">{f(total)}<small>Credits</small></div></div>
    <div class="stat"><div class="k">项目组</div><div class="v">{len(groups)}</div></div>
    <div class="stat"><div class="k">{nx} 预测</div><div class="v">{f(meta["total_forecast"])}<small>Credits</small></div></div>
  </div>
</div></header>

<nav class="toc"><div class="wrap">
  <a href="#rates" class="on">系数总表</a><a href="#period">高峰/平峰</a><a href="#cache">三种 cache</a>
  <a href="#context">上下文分档</a><a href="#raw">原始类型</a><a href="#groups">组用量</a>
  <a href="#models">模型横向</a><a href="#matrix">组×模型</a><a href="#subs">订阅容量</a>
  <a href="#seat">席位结余</a><a href="#advice">诊断建议</a>
</div></nav>

<main>
<section id="rates"><div class="wrap">
  <div class="sec-head"><span class="sec-num">01</span><h2>系数总表</h2></div>
  <p class="sec-note">单位可在「每百万 tokens 消耗多少点数」与「1 个点数能换多少 tokens」之间切换。<code class="hint">—</code> 表示该模型没有这一计费项。</p>
  <div class="controls">
    <input class="search" id="q" type="search" placeholder="筛选模型…" aria-label="筛选模型">
    <div class="seg" role="group" aria-label="单位"><button id="u1" aria-pressed="true">点数 / 1M tokens</button><button id="u2" aria-pressed="false">tokens / 点数</button></div>
    <span class="hint" id="cnt"></span>
  </div>
  <div class="tbl-wrap" data-filterable><table>
    <thead><tr><th>模型</th><th>时段</th><th>上下文档位</th><th>token in</th><th>token out</th>
      <th>cache</th><th>cache read</th><th>cache write 5m</th><th>cache write 1h</th></tr></thead>
    <tbody>{''.join(trs)}</tbody></table></div>
  {warn_html}
</div></section>

<section id="period"><div class="wrap">
  <div class="sec-head"><span class="sec-num">02</span><h2>高峰 / 平峰</h2></div>
  <p class="sec-note">明细的「用量类型」自带 <code class="hint">_peak</code> / <code class="hint">_offpeak</code> 后缀，时段不用靠时间猜。实测高峰 <b>08:00–21:59</b>、平峰 <b>22:00–07:59</b>（Asia/Shanghai）。</p>
  <div class="grid3 rv">
    <div class="card hot"><span class="big">×0.5</span><h3>平峰 = 高峰的一半</h3>
      <p>目前只有 <b>deepseek-v4.1-flash</b> 同时出现两种时段：input 200→100、output 800→400、cache 20→10，三项严格对折。</p></div>
    <div class="card cool"><span class="big">24h<span>恒定</span></span><h3>多数模型不分时段</h3>
      <p><b>qwen*</b> / <b>glm*</b> / <b>kimi*</b> 的用量类型没有 peak / offpeak 后缀，0 点到 23 点费率一致。</p></div>
    <div class="card warm"><span class="big">{sum(1 for m in models if any(r["period"] == "peak" for r in rates if r["model"] == m["name"]) and not any(r["period"] == "offpeak" for r in rates if r["model"] == m["name"]))}<span>个模型</span></span><h3>只有高峰数据</h3>
      <p>这些模型本月只在高峰被调用，平峰系数<b>没有真实数据</b>，不能按 ×0.5 硬套。</p></div>
  </div>
</div></section>

<section id="cache"><div class="wrap">
  <div class="sec-head"><span class="sec-num">03</span><h2>三种「cache」不是同一件事</h2></div>
  <p class="sec-note">把它们并成一列会算错一个数量级。它们是三条独立的计费路径。</p>
  <div class="kv rv">
    <div>cache</div><div><code class="hint">input_token_cache</code> — 单一缓存价。deepseek-v4-flash / pro、glm-5.2 / 5.3、qwen3.7-max、qwen3.8-flash 使用。</div>
    <div>cache read</div><div><code class="hint">input_token_cache_read</code> — 缓存读取价。qwen3.8-max、glm-5.1、qwen3.6 / 3.7-plus 使用。</div>
    <div>cache write 5m</div><div><code class="hint">input_token_cache_creation_5m</code> — 缓存写入价，5 分钟 TTL。</div>
  </div>
  <p class="sec-note" style="margin-top:16px">典型例子 <b>qwen3.7-max</b>：cache 120、cache read 60、cache write <b>750</b>——同时存在，价格差 12 倍。</p>
</div></section>

<section id="context"><div class="wrap">
  <div class="sec-head"><span class="sec-num">04</span><h2>上下文长度分档</h2></div>
  <p class="sec-note">原始类型带 <code class="hint">context_x-y</code> 前缀的模型，按输入上下文长度分档计价。这是最容易忽略的价格跳变。</p>
  <div class="grid3 rv">
    <div class="card cool"><span class="big">×4</span><h3>qwen3.6-plus</h3><p>0-256k：in 200 / out 1,200<br>256k-1m：in 800 / out 4,800</p></div>
    <div class="card cool"><span class="big">×3</span><h3>qwen3.7-plus</h3><p>0-256k：in 200 / out 800<br>256k-1m：in 600 / out 2,400</p></div>
    <div class="card warm"><span class="big">¾</span><h3>glm-5.1</h3><p>0-32k：in 600 / out 2,400<br>32k-200k：in 800 / out 2,800</p></div>
  </div>
  <p class="sec-note" style="margin-top:18px"><b>glm-5.2 / glm-5.3 / qwen3.8-* / deepseek-*</b> 的导出里没有 context 前缀，即不分档计价。</p>
</div></section>

<section id="raw"><div class="wrap">
  <div class="sec-head"><span class="sec-num">05</span><h2>按原始用量类型</h2></div>
  <p class="sec-note">同一模型的每种 token 类型单独成行，用于核对与二次计算。</p>
  <div class="tbl-wrap" style="max-height:56vh"><table>
    <thead><tr><th>模型</th><th>时段</th><th>上下文</th><th class="l">原始用量类型</th><th>点数 / 1M</th><th>tokens / 点数</th></tr></thead>
    <tbody>{''.join(raws)}</tbody></table></div>
</div></section>

<section id="groups"><div class="wrap">
  <div class="sec-head"><span class="sec-num">06</span><h2>部门总览 · 按项目组</h2></div>
  <p class="sec-note">按组长（Team Owner）归集。点击组名可进入该组的独立报告（人员明细、模型结构、下月采购建议）。</p>
  <div class="tbl-wrap" style="max-height:none"><table>
    <thead><tr><th>项目组</th><th>人数</th><th>本月点数</th><th>占比</th><th>人均</th><th>席位消耗</th>
      <th>加油包消耗</th><th>{nx} 预测</th><th>缓存读占比</th><th class="l">主力模型</th></tr></thead>
    <tbody>{''.join(grows)}</tbody></table></div>
  {unmapped_html}
</div></section>

<section id="models"><div class="wrap">
  <div class="sec-head"><span class="sec-num">07</span><h2>模型横向比较</h2></div>
  <p class="sec-note">三层视角：<b>用量与成本</b>（谁在花钱）、<b>单价</b>（同样的 1M token 谁更便宜）、<b>token 结构</b>（钱花在输入、输出还是缓存上）。</p>

  <h3 style="font-family:var(--sans);font-size:14px;font-weight:600;margin:26px 0 10px">7.1 用量与成本</h3>
  <div class="tbl-wrap" style="max-height:none"><table>
    <thead><tr><th>模型</th><th>点数</th><th>占部门</th><th>覆盖人数</th><th>覆盖组数</th><th>混合单价 / 1M</th><th>tokens</th></tr></thead>
    <tbody>{''.join(mrows)}</tbody></table></div>
  <p class="sec-note" style="margin-top:12px">「混合单价」= 该模型总点数 ÷ 总 tokens，把输入/输出/缓存按实际比例混合后的平均价。
  前三个模型合计占 <b>{sum(m["credits"] for m in models[:3]) / denom * 100:.1f}%</b>。</p>

  <h3 style="font-family:var(--sans);font-size:14px;font-weight:600;margin:30px 0 10px">7.2 单价横向（点数 / 1M tokens）</h3>
  <p class="sec-note" style="margin-bottom:14px">同一刻度下比较输入与输出单价，按输出单价排序。每个模型取<b>本月实际主力档位</b>。</p>
  <div class="rv">{''.join(prows)}</div>
  <div class="lg"><span><i style="background:#7aa7d8"></i>输入 in</span><span><i style="background:#ff7a45"></i>输出 out</span></div>
  <p class="sec-note" style="margin-top:12px">输出单价普遍是输入的 <b>2–4 倍</b>，而输出 token 只占 token 总量的不到 2%——真正拉开账单差距的是输出长度。</p>

  <h3 style="font-family:var(--sans);font-size:14px;font-weight:600;margin:30px 0 10px">7.3 token 结构（Top 10 模型）</h3>
  <div class="rv">{''.join(srows)}</div>
  <div class="lg"><span><i style="background:#7aa7d8"></i>输入</span><span><i style="background:#ff7a45"></i>输出</span>
    <span><i style="background:#e8b44a"></i>缓存读</span><span><i style="background:#c792ea"></i>缓存写</span></div>
</div></section>

<section id="matrix"><div class="wrap">
  <div class="sec-head"><span class="sec-num">08</span><h2>组 × 模型矩阵</h2></div>
  <p class="sec-note">格子内为该组在这个模型上的点数消耗，颜色越亮表示该组在此模型的投入越大。</p>
  <div class="tbl-wrap" style="max-height:none;padding:10px"><table class="matrix">
    <thead><tr><th>模型</th>{mh}</tr></thead><tbody>{''.join(mrow)}</tbody></table></div>
</div></section>

<section id="subs"><div class="wrap">
  <div class="sec-head"><span class="sec-num">09</span><h2>当前订阅与容量</h2></div>
  <p class="sec-note">以下为订阅概览接口实测值（{sub.get("fetched_at", "—")}），非推算。
    订阅周期 <b>{_ts(sub.get("start"))} → {_ts(sub.get("end"))}</b>，席位重置 <b>{_ts(sub.get("refresh"))}</b>。</p>
  <div class="grid3 rv" style="margin-bottom:18px">
    <div class="card"><span class="big">{f(std.get("used", 0))}<span>/ {f(std.get("cap", 0))}</span></span><h3>标准席位 {std.get("assigned", 0)} / {std.get("total_seats", 0)}</h3>
      <p>已用 {(std.get("used", 0) / std.get("cap", 1) * 100):.1f}%，剩余 <b>{f(std.get("remaining", 0))}</b> 点。</p></div>
    <div class="card"><span class="big">{f(prm.get("used", 0))}<span>/ {f(prm.get("cap", 0))}</span></span><h3>高级席位 {prm.get("assigned", 0)} / {prm.get("total_seats", 0)}</h3>
      <p>已用 {(prm.get("used", 0) / prm.get("cap", 1) * 100):.1f}%，剩余 <b>{f(prm.get("remaining", 0))}</b> 点。</p></div>
    <div class="card hot"><span class="big">{f(pack.get("remaining", 0))}<span>点剩余</span></span><h3>加油包 · 共享池 {pack.get("count", 0)} 个</h3>
      <p>总量 {f(pack.get("cap", 0))}，已用 {(pack.get("used", 0) / pack.get("cap", 1) * 100):.1f}%。
        <b>最近一个包 {_ts(pack.get("nearest_expire"))} 到期</b>，余量按有效期可结转至下月。</p></div>
  </div>
  <div class="kv rv">
    <div>组织成员</div><div>{sub.get("org", {}).get("total_members", "—")} 人，已分配坐席 <b>{sub.get("org", {}).get("seated", "—")}</b>，未分配 {sub.get("org", {}).get("unseated", "—")}。</div>
    <div>加油包单价</div><div>¥{cfg.pricing["pack"]["price"]:,} / {cfg.pricing["pack"]["credits"]:,} 点 = <b>¥{cfg.pricing["pack"]["price"] / cfg.pricing["pack"]["credits"]:.4f}/点</b></div>
    <div>标准席位</div><div>¥{cfg.pricing["standard_seat"]["price"]} / {cfg.pricing["standard_seat"]["credits"]:,} 点 = <b>¥{cfg.pricing["standard_seat"]["price"] / cfg.pricing["standard_seat"]["credits"]:.4f}/点</b></div>
    <div>高级坐席</div><div>¥{cfg.pricing["premium_seat"]["price"]} / {cfg.pricing["premium_seat"]["credits"]:,} 点 = <b>¥{cfg.pricing["premium_seat"]["price"] / cfg.pricing["premium_seat"]["credits"]:.4f}/点</b>，全场最低</div>
    <div>升级盈亏平衡</div><div>高级坐席超出 25,000 的 75,000 点，边际成本 ¥{cfg.pricing["premium_seat"]["price"] - cfg.pricing["standard_seat"]["price"]} ÷ 75,000 =
      <b>¥{(cfg.pricing["premium_seat"]["price"] - cfg.pricing["standard_seat"]["price"]) / 75000:.4f}/点</b>，比加油包便宜。
      <b>月消耗 &gt; {proc["breakeven"]:,.0f} 点的人升级一定更省。</b></div>
  </div>
</div></section>

<section id="seat"><div class="wrap">
  <div class="sec-head"><span class="sec-num">10</span><h2>月末席位结余预测</h2></div>
  <p class="sec-note">席位额度 <b>{_ts(sub.get("refresh"))} 重置，当月未用尽的部分不结转</b>，所以月末结余等同于已付未用的成本。</p>
  <div class="kv rv" style="margin-bottom:22px">
    <div>估算方法 ①</div><div>剩余天数 = <b>{cal["remaining"].get("total", 0)} 天</b>（{cal["remaining"].get("workday", 0)} 个工作日 + {cal["remaining"].get("weekend", 0)} 个周末{("，含 " + str(cal["remaining"]["holiday"]) + " 天假日") if cal["remaining"].get("holiday") else "，无法定节假日"}）。</div>
    <div>估算方法 ②</div><div>个体日均取 <b>{cal["start"]} ~ {( __import__("datetime").date.fromisoformat(cal["end"]) ).isoformat()}</b> 中已完整结束的日期，剔除法定假日与不完整日，工作日、周末分别计算（样本：{cal["sample"]["workday"]} 个工作日 / {cal["sample"]["weekend"]} 个周末）。</div>
    <div>估算方法 ③</div><div>月末预计 = 当前已用点数 + 工作日日均 × {cal["remaining"].get("workday", 0)} + 周末日均 × {cal["remaining"].get("weekend", 0)}。</div>
    <div>估算方法 ④</div><div>预计结余 = max(0, 席位额度 − 月末预计)；<b>结余需超过额度的 {A["waste"]["threshold"] * 100:.0f}% 才计入</b>，避免把预测误差当浪费。</div>
    <div>估算方法 ⑤</div><div>折合金额 = 结余点数 × 席位单价：标准 <b>¥{cfg.pricing["standard_seat"]["price"]} / {cfg.pricing["standard_seat"]["credits"]:,} 点</b>，高级 <b>¥{cfg.pricing["premium_seat"]["price"]} / {cfg.pricing["premium_seat"]["credits"]:,} 点</b>。</div>
    <div>共享席位</div><div>名册中标注「Sharing with」的席位由两人共用，按<b>整席</b>计算，不拆分到个人。</div>
  </div>
  <div class="grid3 rv" style="margin-bottom:22px">
    <div class="card warm"><span class="big">{A["waste"]["total"]:,.0f}<span>¥</span></span><h3>部门合计预计结余</h3>
      <p>{A["waste"]["count"]} 个席位月末预计用不尽额度。这是已付未用的成本，不结转、不退还。</p></div>
    <div class="card"><span class="big">{seat_pct_now:.1f}<span>%</span></span><h3>当前席位额度使用率</h3>
      <p>{std.get("assigned", 0)} 标准 + {prm.get("assigned", 0)} 高级，总容量 {f(seat_cap)} 点，当前已用 {f(seat_used_now)} 点。</p></div>
    <div class="card"><span class="big">{len(by_group)}<span>组</span></span><h3>存在结余的项目组</h3>
      <p>各组情况见下表。<b>按名册顺序列出，非排名</b>；各组人数与套餐结构不同，金额不宜直接互相比较。</p></div>
  </div>
  <div class="tbl-wrap" style="max-height:none"><table>
    <thead><tr><th>项目组</th><th>预计结余席位数</th><th>折合金额</th><th class="l">涉及席位（含共享人）</th></tr></thead>
    <tbody>{''.join(seat_rows)}</tbody></table></div>
  <p class="sec-note" style="margin-top:12px">提示：结余集中在用量本身很低的席位（零调用、零星调用），与模型选型无关；这类席位的问题在「要不要保留」，不在「怎么用」。逐人明细见各组报告。</p>
</div></section>

<section id="advice"><div class="wrap">
  <div class="sec-head"><span class="sec-num">11</span><h2>技术诊断与建议</h2></div>
  <p class="sec-note">全部基于本月全量明细计算，收益按点数计。</p>
  <div class="grid3 rv" style="margin-bottom:22px">
    <div class="card warm"><span class="big">{peak_ratio:.2f}%</span><h3>平峰利用率</h3>
      <p>deepseek-v4.1-flash 高峰 <b>{f(v41["peak"]) if v41 else "—"}</b> 点、平峰 <b>{f(v41["offpeak"]) if v41 else "—"}</b> 点。平峰是高峰的一半价，这是最大的一块可省空间。</p></div>
    <div class="card hot"><span class="big">{full_cnt}<span>/ {len(people)}</span></span><h3>席位已用尽</h3>
      <p>用尽后全部走共享加油包（¥{cfg.pricing["pack"]["price"] / cfg.pricing["pack"]["credits"]:.4f}/点），比高级坐席的边际价贵。</p></div>
    <div class="card cool"><span class="big">15×</span><h3>缓存写入比读取贵</h3>
      <p>cache write 通常 1,000–1,500 点 / 1M，cache read 只有 60–100 点。优化空间在<b>减少重建</b>（稳定前缀、少改 system prompt）。</p></div>
  </div>
  <div class="kv rv">
    <div>建议 1 · 平峰迁移</div><div>把可延迟任务（批量推理、离线评测、数据清洗、长文档摘要）放到 <b>22:00–08:00</b>。
      deepseek-v4.1-flash 平峰 in <b>100 点/1M</b>、out <b>400 点/1M</b>，是高峰的一半，也是全场最低价。
      按高峰迁移 30% 测算，每月省 <b>{f((v41["peak"] if v41 else 0) * 0.3 * 0.5)}</b> 点。</div>
    <div>建议 2 · 席位前置</div><div>{full_cnt} 人席位已用尽。按 {nx} 预测，有 <b>{len(upg)} 人</b>月消耗超过 {proc["breakeven"]:,.0f} 点，升级高级坐席比走加油包更省，见下方测算。</div>
    <div>建议 3 · 控制输出长度</div><div>输出 token 只占 token 总量不到 2%，却贡献了大部分成本：output 单价是 cache read 的 <b>20–36 倍</b>。
      限制 <code class="hint">max_tokens</code>、减少冗长解释、用结构化输出，比压缩输入更有效。</div>
    <div>建议 4 · 上下文别越档</div><div>qwen3.6-plus 超过 256k 后 input ×4、output ×4；qwen3.7-plus 超过 256k 后 ×3；glm-5.1 超过 32k 后 ×1.33。长上下文场景先算清档位再选型。</div>
    <div>建议 5 · 选型价差</div><div>同类任务下，glm-5.3（in 800 / out 2,800）比 qwen3.8-max（in 1,200 / out 3,600）省 <b>33% / 22%</b>；
      对延迟不敏感的任务切到 deepseek-v4.1-flash 平峰（in 100 / out 400），价格差一个数量级。</div>
  </div>

  <h3 style="font-family:var(--sans);font-size:14px;font-weight:600;margin:32px 0 10px">{nx} 采购测算</h3>
  <p class="sec-note">{nx} 共 <b>{st_a["workday"]} 个工作日 + {st_a["weekend"]} 个周末</b>{("，" + str(st_a["holiday"]) + " 天法定假日") if st_a.get("holiday") else "，无法定节假日"}。
  本月因假日 {st_m.get("holiday", 0)} 天，所以<b>不能直接拿本月均值外推</b>，这里用假期后按工作日/周末分开的日均建模。</p>
  <div class="tbl-wrap" style="max-height:none"><table>
    <thead><tr><th class="l">方案</th><th>席位配置</th><th>席位月费</th><th>加油包</th><th>加油包费用</th><th>月度合计</th></tr></thead>
    <tbody>
      <tr><td class="m">A · 维持现状</td><td class="dim">{std.get("assigned", 0)} 标准 + {prm.get("assigned", 0)} 高级</td>
        <td class="num">¥{a["seat_fee"]:,}</td>
        <td class="num dim">缺口 {f(a["need"])} → 加购 {a["packs"]} 个</td>
        <td class="num">¥{a["pack_cost"]:,}</td><td class="num strong">¥{a["total"]:,}</td></tr>
      <tr><td class="m">B · 升级 {len(upg)} 人 <span class="chip ok">推荐</span></td>
        <td class="dim">{std.get("assigned", 0) - len(upg)} 标准 + {prm.get("assigned", 0) + len(upg)} 高级</td>
        <td class="num">¥{b["seat_fee"]:,}</td>
        <td class="num dim">缺口 {f(b["need"])} → 加购 {b["packs"]} 个</td>
        <td class="num">¥{b["pack_cost"]:,}</td><td class="num strong">¥{b["total"]:,}</td></tr>
    </tbody></table></div>
  <p class="sec-note" style="margin-top:14px">
    方案 B 当月省 <b>¥{a["total"] - b["total"]:,}</b>{("（主要来自躲过一整个加油包的粒度）" if a["total"] > b["total"] else "")}；
    共享池当前剩余 {f(proc["pack_left_now"])} 点，扣除本月剩余天数预计支取 {f(proc["pack_draw_rest"])} 点后，
    可结转 <b>{f(proc["pack_carry"])}</b> 点用于下月，已计入测算。</p>

  <div class="tbl-wrap" style="max-height:none;margin-top:18px"><table>
    <thead><tr><th>建议升级人员</th><th class="l">所属组</th><th>{nx} 预测</th><th>现席位额度</th><th>需走加油包</th></tr></thead>
    <tbody>{adv_rows}</tbody></table></div>
  <p class="sec-note" style="margin-top:12px">
    另有 <b>{len(idle)} 个席位零用量</b>（{'、'.join(esc(p["label"]) for p in idle) or "无"}），
    ¥{sum(p["seat_fee"] for p in idle)}/月 空转。</p>
</div></section>

<section id="files" style="border-bottom:0"><div class="wrap">
  <div class="sec-head"><span class="sec-num">12</span><h2>配套文件</h2></div>
  <div class="files">
    {''.join(f'<div class="file"><span class="ext">组报告</span><span class="nm">team-{esc(g["name"])}.html</span><span class="ds">{g["count"]} 个席位 · {f(g["credits"])} 点</span></div>' for g in groups)}
    <div class="file"><span class="ext">XLSX</span><span class="nm">token_credits_coefficients.xlsx</span><span class="ds">系数 / 原始类型 / 成员 / 模型</span></div>
    <div class="file"><span class="ext">CSV</span><span class="nm">raw/usage_detail.csv</span><span class="ds">全量原始明细 {meta["rows"]:,} 行</span></div>
    <div class="file"><span class="ext">CSV</span><span class="nm">recipients.csv</span><span class="ds">各组收件人清单（姓名 / 邮箱 / 角色）</span></div>
    <div class="file"><span class="ext">JSON</span><span class="nm">manifest.json</span><span class="ds">运行清单与自检结果</span></div>
  </div>
</div></section>
</main>

<footer><div class="wrap"><span>数据源 · {cfg.root}</span>
  <span>生成于 {meta["generated_at"]} · 数据截至 {meta["data_end"]}</span></div></footer>
<script>{JS}</script></body></html>"""