"""报告通用绘图工具：热力网格、24h 柱状、配色。供 member / group / dept 报告共用。"""
from __future__ import annotations

import html


def esc(s):
    return html.escape(str(s))


def f(v, dec=0):
    if v is None:
        return "—"
    return f"{v:,.{dec}f}"


def fnum(v, dec=0):
    if v is None:
        return "—"
    return f"{v:,.{dec}f}" if abs(v - round(v)) < 1e-6 else f"{v:,.{dec}f}"


def heat_bg(v: float, vmax: float, rgb=(232, 180, 74), lo=0.05, hi=0.92) -> str:
    """值 → 热力格背景色。0 值给极淡的底，保证网格可见。"""
    if vmax <= 0 or v <= 0:
        return f"rgba({rgb[0]},{rgb[1]},{rgb[2]},0.045)"
    a = lo + (hi - lo) * min(v / vmax, 1.0) ** 0.7   # γ<1：小值也有可辨识的色差
    return f"rgba({rgb[0]},{rgb[1]},{rgb[2]},{a:.3f})"


def heat_grid(rows, cols, values, *, vmax=None, rgb=(232, 180, 74),
              row_w=64, cell=15, gap=2, title=None, col_head_every=1, fill=False):
    """通用热力网格。

    rows  : 行标签列表（第一列）
    cols  : 列标签列表（表头行）
    values: values[i][j] 数值二维表
    title : (i, j, v) -> 悬浮提示文本，缺省为「行 · 列 · 值」
    fill  : True 时列宽 1fr 撑满容器（适合行少的图，如 7×24）；False 用固定 cell 宽
    """
    n_r, n_c = len(rows), len(cols)
    if vmax is None:
        vmax = max((v for row in values for v in row), default=0)

    def tip(i, j, v):
        return title(i, j, v) if title else f"{rows[i]} · {cols[j]} · {f(v)}"

    head = "".join(
        f'<span class="hgx{" b" if (j % col_head_every == 0) else ""}">{esc(c)}</span>'
        for j, c in enumerate(cols))
    body = []
    for i, rl in enumerate(rows):
        cells = "".join(
            f'<i style="background:{heat_bg(values[i][j], vmax, rgb)}" title="{esc(tip(i, j, values[i][j]))}"></i>'
            for j in range(n_c))
        body.append(f'<span class="hgl">{esc(rl)}</span>{cells}')
    cols_def = f"repeat({n_c},1fr)" if fill else f"repeat({n_c},{cell}px)"
    return (f'<div class="heat" style="--roww:{row_w}px;--cell:{cell}px;--gap:{gap}px;'
            f'grid-template-columns:var(--roww) {cols_def}">'
            f'<span class="hgl hx"></span>{head}{"".join(body)}</div>')


def hbars(values, *, height=110, rgb="accent", fmt=f, labels=None, bold_every=3):
    """24（或任意 n）列细柱图。labels 为列头文本；bold_every 控制加粗刻度。"""
    vmax = max(values, default=0) or 1
    col = "var(--accent)" if rgb == "accent" else rgb
    bars = "".join(
        f'<div class="hcol" title="{esc(labels[j] if labels else j)} · {esc(fmt(v))}">'
        f'<i style="height:{max(v / vmax * 100, (0.8 if v > 0 else 0)):.1f}%;background:{col}"></i></div>'
        for j, v in enumerate(values))
    axis = "".join(
        f'<span class="{"b" if (j % bold_every == 0) else ""}">{esc(c)}</span>'
        for j, c in enumerate(labels or [str(j) for j in range(len(values))]))
    return (f'<div class="hbars" style="height:{height}px;grid-template-columns:repeat({len(values)},1fr)">{bars}</div>'
            f'<div class="haxis" style="grid-template-columns:repeat({len(values)},1fr)">{axis}</div>')


def pct_row(label, value_text, pct, *, rgb=(122, 167, 216)):
    """分位条：0–100。pct=None 显示 —。"""
    if pct is None:
        fill, ptext = "", '<span class="pv dim">—</span>'
    else:
        fill = (f'<span class="pt"><i style="width:{max(pct, 0.8):.1f}%;'
                f'background:rgba({rgb[0]},{rgb[1]},{rgb[2]},.75)"></i>'
                f'<i class="mk" style="left:{max(pct, 0.8):.1f}%"></i></span>')
        ptext = f'<span class="pv">P{pct:.0f}</span>'
    return (f'<div class="pctx"><span class="pn">{esc(label)}</span>{fill}'
            f'<span class="pv mono">{esc(value_text)}</span>{ptext}</div>')


PER = {"peak": ("PEAK", "高峰"), "offpeak": ("OFFPEAK", "平峰"), "flat": ("FLAT", "不分时段")}
PATTERN_CHIP = {
    "白天型": "ok", "持续稳定": "ok", "混合型": "flat",
    "早晚型": "warn", "夜间型": "warn", "集中攻坚": "full",
    "轻量偶发": "none", "零用量": "none", "未开通": "none",
}


def pattern_chip(pattern: str) -> str:
    cls = PATTERN_CHIP.get(pattern, "flat")
    return f'<span class="chip {cls}">{esc(pattern)}</span>'
