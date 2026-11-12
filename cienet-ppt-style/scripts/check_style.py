#!/usr/bin/env python3
"""校验 CIeNET 品牌 PPT 是否符合母版 / 配色 / 语义规范。

只用 Python 标准库：直接读 pptx（zip + XML），不依赖 officecli，
可以在 CI 或没有 Office 的机器上跑。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import sys
import zipfile
from collections import OrderedDict
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

EMU_PER_CM = 360000
SLIDE_W = 12192000
SLIDE_H = 6858000
SLIDE_AREA = SLIDE_W * SLIDE_H

# ---------------------------------------------------------------- 规范常量

BRAND = OrderedDict(
    [
        ("brand-blue", "2453B3"),
        ("brand-purple", "5230A2"),
        ("brand-magenta", "932193"),
        ("tint-blue", "DAE6FB"),
        ("tint-purple", "E7E6F8"),
        ("tint-pink", "F5E5F5"),
        ("ink", "1A1A1A"),
        ("neutral-dark", "5A5A5A"),
        ("neutral-line", "D9D9D9"),
        ("white", "FFFFFF"),
        ("black", "000000"),
    ]
)

# 母版既有色：只允许沿用，不允许作为新元素的自由色
TEMPLATE_COLORS = {
    "6D97D2",  # 内容页眉标
    "E8EEF8",  # 封面第三行 / 致谢副标题
    "D8E2F2",  # 封面元信息 / 致谢落款
    "0A54BA",  # 母版渐变 / 页脚
    "A10B98",  # 母版渐变
    "980F9A",  # 母版渐变
    "D7E7FD",  # 母版浅渐变
    "F8E4F6",  # 母版浅渐变
    "582EA8",  # 母版紫
    "1A5CAE",  # 母版深蓝
    "043962",  # 母版深蓝
}

ALLOWED_COLORS = set(BRAND.values()) | TEMPLATE_COLORS
MAGENTA = BRAND["brand-magenta"]
MAGENTA_MAX_RATIO = 0.05

LAYOUT_ALLOWLIST = [
    "Custom Layout 2",
    "TITLE",
    "TITLE PAGE 1",
    "Contact information",
    "AGENDA 1",
    "Title and Content",
    "Acknowledgements",
    "DEFAULT_1",
]

# 封面 / 目录 / 致谢这类页面允许没有 >=24pt 的标题
TITLE_EXEMPT = {"TITLE PAGE 1", "TITLE", "AGENDA 1", "Acknowledgements"}

ALLOWED_LATIN = {"Calibri"}
ALLOWED_EA = {"宋体", "SimSun", ""}

AREA_CHART_TYPES = {
    "barChart",
    "bar3DChart",
    "pieChart",
    "pie3DChart",
    "doughnutChart",
    "areaChart",
    "area3DChart",
}

# ---------------------------------------------------------------- 数据结构


@dataclass
class Finding:
    level: str  # FAIL / WARN
    check: str
    slide: int
    detail: str

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "check": self.check,
            "slide": self.slide,
            "detail": self.detail,
        }

    def format(self, path: str) -> str:
        loc = f"{path}#slide{self.slide}" if self.slide else path
        return f"[{self.level}] {loc} {self.check}: {self.detail}"


@dataclass
class SlideInfo:
    number: int
    part: str
    layout: str
    layout_part: str
    area_magenta: int = 0
    magenta_items: list = field(default_factory=list)
    colors: set = field(default_factory=set)
    fonts: set = field(default_factory=set)
    max_size: float = 0.0
    text_len: int = 0
    has_picture: bool = False
    charts: list = field(default_factory=list)
    shape_bounds: list = field(default_factory=list)


# ---------------------------------------------------------------- 工具函数


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def color_of(el) -> str | None:
    """从一个填充/颜色父节点里取十六进制色值（不含 #）。"""
    if el is None:
        return None
    for child in el.iter():
        name = local(child.tag)
        if name == "srgbClr":
            val = (child.get("val") or "").upper()
            if len(val) == 6:
                return val
        if name == "schemeClr":
            return None
    return None


def scheme_of(el) -> str | None:
    if el is None:
        return None
    for child in el.iter():
        if local(child.tag) == "schemeClr":
            return child.get("val")
    return None


def rels_path(part: str) -> str:
    d, f = posixpath.split(part)
    return posixpath.join(d, "_rels", f + ".rels")


def resolve(base_part: str, target: str) -> str:
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/"))
    base_dir = posixpath.dirname(base_part)
    return posixpath.normpath(posixpath.join(base_dir, target))


def read_rels(zf: zipfile.ZipFile, part: str) -> dict:
    path = rels_path(part)
    if path not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read(path))
    out = {}
    for rel in root:
        rid = rel.get("Id")
        typ = rel.get("Type", "")
        target = rel.get("Target", "")
        if rel.get("TargetMode") == "External":
            continue
        out[rid] = (typ.rsplit("/", 1)[-1], resolve(part, target))
    return out


def shape_name(el) -> str:
    for child in el.iter():
        if local(child.tag) == "cNvPr":
            return child.get("name") or ""
    return ""


def shape_xfrm(el):
    # p:spPr/a:xfrm, p:pic/p:spPr/a:xfrm, p:graphicFrame/p:xfrm
    for child in el:
        if local(child.tag) in ("spPr", "grpSpPr"):
            x = child.find("a:xfrm", NS)
            if x is not None:
                off = x.find("a:off", NS)
                ext = x.find("a:ext", NS)
                if off is not None and ext is not None:
                    return (
                        int(off.get("x", 0)),
                        int(off.get("y", 0)),
                        int(ext.get("cx", 0)),
                        int(ext.get("cy", 0)),
                    )
        if local(child.tag) == "xfrm":
            off = child.find("a:off", NS)
            ext = child.find("a:ext", NS)
            if off is not None and ext is not None:
                return (
                    int(off.get("x", 0)),
                    int(off.get("y", 0)),
                    int(ext.get("cx", 0)),
                    int(ext.get("cy", 0)),
                )
    return None


def iter_shapes(root):
    """遍历顶层与组内形状（sp / pic / graphicFrame / cxnSp）。"""
    for el in root.iter():
        if local(el.tag) in ("sp", "pic", "graphicFrame", "cxnSp"):
            yield el


# ---------------------------------------------------------------- 主校验


class Deck:
    def __init__(self, path: str):
        self.path = path
        self.zf = zipfile.ZipFile(path)
        self.theme_colors = self._theme_colors()
        self.pres_part = "ppt/presentation.xml"
        self.pres = ET.fromstring(self.zf.read(self.pres_part))
        self.pres_rels = read_rels(self.zf, self.pres_part)
        self.slides: list[SlideInfo] = []
        self._load_slides()

    def _theme_colors(self) -> dict:
        colors = {}
        for name in self.zf.namelist():
            if name.startswith("ppt/theme/theme") and name.endswith(".xml"):
                root = ET.fromstring(self.zf.read(name))
                scheme = root.find(".//a:clrScheme", NS)
                if scheme is None:
                    continue
                for child in scheme:
                    key = local(child.tag)
                    c = color_of(child)
                    if c:
                        colors.setdefault(key, c)
                break
        return colors

    def resolve_color(self, el) -> str | None:
        c = color_of(el)
        if c:
            return c
        s = scheme_of(el)
        if s:
            return self.theme_colors.get(s)
        return None

    def _fill_color(self, el):
        for child in el:
            if local(child.tag) in ("spPr", "grpSpPr"):
                solid = child.find("a:solidFill", NS)
                if solid is not None:
                    return self.resolve_color(solid)
        return None

    def _load_slides(self):
        sld_list = self.pres.find("p:sldIdLst", NS)
        if sld_list is None:
            return
        number = 0
        for sld in sld_list:
            rid = sld.get(f"{{{NS['r']}}}id")
            rel = self.pres_rels.get(rid)
            if not rel:
                continue
            number += 1
            part = rel[1]
            layout_part, layout_name = "", ""
            for typ, target in read_rels(self.zf, part).values():
                if typ == "slideLayout":
                    layout_part = target
                    try:
                        lroot = ET.fromstring(self.zf.read(target))
                        cSld = lroot.find("p:cSld", NS)
                        layout_name = cSld.get("name", "") if cSld is not None else ""
                    except KeyError:
                        layout_name = ""
            info = SlideInfo(number, part, layout_name, layout_part)
            self._parse_slide(info)
            self.slides.append(info)

    def _parse_slide(self, info: SlideInfo):
        root = ET.fromstring(self.zf.read(info.part))
        for el in iter_shapes(root):
            tag = local(el.tag)
            name = shape_name(el)
            bounds = shape_xfrm(el)
            if bounds:
                info.shape_bounds.append((name, bounds))
            if tag == "pic":
                info.has_picture = True

            # 文字与字体
            for t in el.iter(f"{{{NS['a']}}}t"):
                if t.text and t.text.strip():
                    info.text_len += 1
            for rpr in el.iter(f"{{{NS['a']}}}rPr"):
                self._collect_run_props(info, rpr)
            for rpr in el.iter(f"{{{NS['a']}}}endParaRPr"):
                self._collect_run_props(info, rpr)
            for defrpr in el.iter(f"{{{NS['a']}}}defRPr"):
                self._collect_run_props(info, defrpr)

            # 所有显式颜色（填充、文字、线）
            for clr in el.iter(f"{{{NS['a']}}}srgbClr"):
                val = (clr.get("val") or "").upper()
                if len(val) == 6:
                    info.colors.add(val)

            # 形状纯色填充的洋红面积
            fill = self._fill_color(el)
            if fill and bounds and tag != "pic":
                if fill == MAGENTA:
                    area = bounds[2] * bounds[3]
                    info.area_magenta += area
                    info.magenta_items.append((name or f"shape{tag}", area))

            # 表格单元格
            tbl = el.find(".//a:tbl", NS)
            if tbl is not None and bounds:
                rows = tbl.findall("a:tr", NS)
                ncols = len(rows[0].findall("a:tc", NS)) if rows else 0
                if rows and ncols:
                    cell_w = bounds[2] // ncols
                    for tr in rows:
                        cells = tr.findall("a:tc", NS)
                        cell_h = (bounds[3] // len(rows)) if len(rows) else 0
                        for idx, tc in enumerate(cells):
                            tcpr = tc.find("a:tcPr", NS)
                            cell_fill = None
                            if tcpr is not None:
                                for child in tcpr:
                                    if local(child.tag) == "solidFill":
                                        cell_fill = self.resolve_color(child)
                            if cell_fill == MAGENTA:
                                area = cell_w * cell_h
                                info.area_magenta += area
                                info.magenta_items.append(
                                    (f"{name or 'table'} r?c{idx + 1}", area)
                                )

            # 图表
            if tag == "graphicFrame":
                for typ, target in read_rels(self.zf, info.part).values():
                    if typ == "chart":
                        info.charts.append(
                            self._parse_chart(target, bounds, info.number)
                        )

        # 同一图表可能被多个 rel 引用，按 part 去重
        uniq = OrderedDict()
        for ch in info.charts:
            uniq[ch["part"]] = ch
        info.charts = list(uniq.values())

    def _collect_run_props(self, info: SlideInfo, rpr):
        sz = rpr.get("sz")
        if sz:
            try:
                info.max_size = max(info.max_size, int(sz) / 100.0)
            except ValueError:
                pass
        latin = rpr.find("a:latin", NS)
        ea = rpr.find("a:ea", NS)
        if latin is not None and latin.get("typeface"):
            info.fonts.add(latin.get("typeface"))
        if ea is not None and ea.get("typeface"):
            info.fonts.add(ea.get("typeface"))

    def _parse_chart(self, part: str, bounds, slide_no: int) -> dict:
        try:
            root = ET.fromstring(self.zf.read(part))
        except KeyError:
            return {"part": part, "slide": slide_no, "series": [], "type": ""}
        plot = root.find(".//c:plotArea", NS)
        chart_type = ""
        if plot is not None:
            for child in plot:
                if local(child.tag).endswith("Chart"):
                    chart_type = local(child.tag)
                    break
        series = []
        for ser in root.iter(f"{{{NS['c']}}}ser"):
            name = ""
            tx = ser.find("c:tx", NS)
            if tx is not None:
                v = tx.find(".//c:v", NS)
                if v is not None:
                    name = v.text or ""
            color = None
            sppr = ser.find("c:spPr", NS)
            if sppr is not None:
                solid = sppr.find("a:solidFill", NS)
                if solid is not None:
                    color = self.resolve_color(solid)
            series.append({"name": name, "color": color})
        return {
            "part": part,
            "slide": slide_no,
            "type": chart_type,
            "series": series,
            "area": (bounds[2] * bounds[3]) if bounds else 0,
        }


# ---------------------------------------------------------------- 检查项


def check_deck(deck: Deck, findings: list, template: str | None = None):
    # 1. 画布
    sz = deck.pres.find("p:sldSz", NS)
    cx = int(sz.get("cx", 0)) if sz is not None else 0
    cy = int(sz.get("cy", 0)) if sz is not None else 0
    if (cx, cy) != (SLIDE_W, SLIDE_H):
        findings.append(
            Finding(
                "FAIL",
                "画布",
                0,
                f"{cx}x{cy} EMU，不是 16:9（应为 {SLIDE_W}x{SLIDE_H}）",
            )
        )

    # 2. 页数
    if not deck.slides:
        findings.append(Finding("FAIL", "页数", 0, "演示文稿没有页面"))
        return

    seen_layout = set()
    for s in deck.slides:
        # 3. 布局白名单
        if s.layout not in LAYOUT_ALLOWLIST:
            findings.append(
                Finding("FAIL", "布局", s.number, f"布局 '{s.layout}' 不在允许列表内")
            )
        seen_layout.add(s.layout)

        # 4. 色值白名单
        bad = sorted(c for c in s.colors if c not in ALLOWED_COLORS)
        if bad:
            findings.append(
                Finding(
                    "FAIL",
                    "色值",
                    s.number,
                    "出现色卡外颜色 " + ", ".join("#" + c for c in bad),
                )
            )

        # 5. 字体
        bad_fonts = sorted(
            f
            for f in s.fonts
            if f not in ALLOWED_LATIN and f not in ALLOWED_EA
        )
        if bad_fonts:
            findings.append(
                Finding(
                    "FAIL",
                    "字体",
                    s.number,
                    "出现非 Calibri/宋体 字体 " + ", ".join(bad_fonts),
                )
            )

        # 6. 洋红面积
        ratio = s.area_magenta / SLIDE_AREA if SLIDE_AREA else 0
        if ratio > MAGENTA_MAX_RATIO:
            names = sorted(s.magenta_items, key=lambda x: -x[1])[:3]
            detail = f"洋红面积 {ratio * 100:.1f}%（上限 5%）"
            if names:
                detail += "；最大元素：" + "、".join(
                    f"{n} {a / EMU_PER_CM / EMU_PER_CM:.1f}cm²" for n, a in names
                )
            findings.append(Finding("FAIL", "洋红面积", s.number, detail))

        # 7. 渐变方向
        for grad in _iter_gradfills(deck, s):
            for stop in grad:
                pos = int(stop.get("pos", "0"))
                c = None
                for child in stop:
                    if local(child.tag) == "srgbClr":
                        c = (child.get("val") or "").upper()
                    elif local(child.tag) == "schemeClr":
                        c = deck.theme_colors.get(child.get("val"))
                if c == MAGENTA and pos < 50000:
                    findings.append(
                        Finding(
                            "FAIL",
                            "洋红渐变",
                            s.number,
                            f"洋红出现在渐变 {pos / 1000:.0f}% 处，只允许在末端（≥50%）",
                        )
                    )
                    break

        # 8. 图表
        for ch in s.charts:
            for idx, ser in enumerate(ch["series"]):
                if idx == 0 and ser["color"] == MAGENTA and ch["type"] in AREA_CHART_TYPES:
                    findings.append(
                        Finding(
                            "FAIL",
                            "图表首序列",
                            s.number,
                            f"图表 '{ch['type']}' 第 1 序列 '{ser['name']}' 用了洋红",
                        )
                    )
                if ser["color"] == MAGENTA and ch["type"] in AREA_CHART_TYPES:
                    # 面积型图表里洋红占比粗算：图表面积 × 0.55 / 序列数
                    n = max(len(ch["series"]), 1)
                    approx = ch["area"] * 0.55 / n
                    if approx > SLIDE_AREA * MAGENTA_MAX_RATIO:
                        findings.append(
                            Finding(
                                "FAIL",
                                "洋红面积",
                                s.number,
                                f"图表 '{ch['type']}' 洋红序列 '{ser['name']}' 折算面积约 "
                                f"{approx / EMU_PER_CM / EMU_PER_CM:.1f}cm²，超过单页 5%",
                            )
                        )

        # 9. 空页
        if s.text_len == 0 and not s.has_picture and not s.charts:
            findings.append(Finding("FAIL", "空页", s.number, "页面没有任何可见内容"))

        # 10. 标题层级
        if s.layout not in TITLE_EXEMPT and s.max_size < 24:
            findings.append(
                Finding(
                    "WARN",
                    "标题层级",
                    s.number,
                    f"最大字号 {s.max_size:.0f}pt，内容页标题应 ≥24pt",
                )
            )

        # 11. 字号下限
        if 0 < s.max_size < 10:
            findings.append(
                Finding("WARN", "字号", s.number, f"最大字号只有 {s.max_size:.0f}pt")
            )

        # 12. logo 区与页脚区
        for name, (x, y, w, h) in s.shape_bounds:
            if w * h == 0:
                continue
            if x > 31.5 * EMU_PER_CM and y < 2.5 * EMU_PER_CM:
                findings.append(
                    Finding(
                        "FAIL",
                        "logo 遮挡",
                        s.number,
                        f"'{name or '未命名形状'}' 位于 logo 区（x>31.5cm, y<2.5cm）",
                    )
                )
            if (y + h) > 17.9 * EMU_PER_CM and (w * h) > 0.5 * EMU_PER_CM * EMU_PER_CM:
                findings.append(
                    Finding(
                        "WARN",
                        "页脚区",
                        s.number,
                        f"'{name or '未命名形状'}' 底边超过 17.9cm，可能压住页脚",
                    )
                )

    # 13. 图表序列跨页一致性
    by_name = {}
    for s in deck.slides:
        for ch in s.charts:
            for ser in ch["series"]:
                if not ser["name"] or not ser["color"]:
                    continue
                by_name.setdefault(ser["name"], []).append((s.number, ser["color"]))
    for name, uses in by_name.items():
        colors = {c for _, c in uses}
        if len(colors) > 1:
            detail = "、".join(f"slide {n}=#{c}" for n, c in uses)
            findings.append(
                Finding(
                    "FAIL",
                    "图表序列",
                    uses[0][0],
                    f"序列 '{name}' 跨页颜色不一致：{detail}",
                )
            )

    # 14. 母版完整性
    check_master_integrity(deck, findings, template)


def _iter_gradfills(deck: Deck, s: SlideInfo):
    root = ET.fromstring(deck.zf.read(s.part))
    for grad in root.iter(f"{{{NS['a']}}}gradFill"):
        stops = []
        for gs in grad.iter(f"{{{NS['a']}}}gs"):
            stops.append(gs)
        if stops:
            yield stops


def check_master_integrity(deck: Deck, findings: list, template: str | None = None):
    if not template or not os.path.exists(template):
        findings.append(
            Finding("WARN", "母版完整性", 0, f"未找到模板 {template!r}，跳过母版校验")
        )
        return
    def canon_hash(data: bytes) -> str:
        # officecli 保存时会重排缩进/换行/编码，按规范化 XML 比对语义
        try:
            text = ET.canonicalize(data.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return hashlib.sha256(data).hexdigest()
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    with zipfile.ZipFile(template) as tz:
        expected = {}
        for name in tz.namelist():
            if name.startswith(("ppt/slideMasters/", "ppt/slideLayouts/")) and name.endswith(
                ".xml"
            ):
                expected[name] = canon_hash(tz.read(name))
        actual = {}
        for name in deck.zf.namelist():
            if name.startswith(("ppt/slideMasters/", "ppt/slideLayouts/")) and name.endswith(
                ".xml"
            ):
                actual[name] = canon_hash(deck.zf.read(name))
    missing = sorted(set(expected) - set(actual))
    changed = sorted(k for k in expected if k in actual and expected[k] != actual[k])
    extra = sorted(set(actual) - set(expected))
    if missing or changed or extra:
        parts = []
        if changed:
            parts.append("被修改：" + ", ".join(changed[:5]))
        if missing:
            parts.append("缺失：" + ", ".join(missing[:5]))
        if extra:
            parts.append("新增：" + ", ".join(extra[:5]))
        findings.append(
            Finding("FAIL", "母版完整性", 0, "；".join(parts) + "。请从 assets/cienet_theme.pptx 重新起稿")
        )


def check_plan(deck: Deck, plan_path: str, findings: list):
    try:
        with open(plan_path, "r", encoding="utf-8") as fh:
            plan = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        findings.append(Finding("WARN", "语义色表", 0, f"无法读取 {plan_path}: {exc}"))
        return
    declared = {}
    for key in ("charts", "series"):
        for name, color in (plan.get(key) or {}).items():
            declared[name] = str(color).lstrip("#").upper()
    if not declared:
        findings.append(
            Finding("WARN", "语义色表", 0, "计划文件里没有 charts / series 声明")
        )
        return
    for s in deck.slides:
        for ch in s.charts:
            for ser in ch["series"]:
                want = declared.get(ser["name"])
                if want and ser["color"] and want != ser["color"]:
                    findings.append(
                        Finding(
                            "FAIL",
                            "语义色表",
                            s.number,
                            f"序列 '{ser['name']}' 用 #{ser['color']}，语义色表声明 #{want}",
                        )
                    )


# ---------------------------------------------------------------- CLI


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="校验 CIeNET 品牌 PPT 规范（母版/配色/字体/洋红/语义）"
    )
    parser.add_argument("deck", help="待校验的 .pptx")
    parser.add_argument(
        "--template",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets",
            "cienet_theme.pptx",
        ),
        help="母版基准文件（默认 skills 内 assets/cienet_theme.pptx）",
    )
    parser.add_argument(
        "--plan", default=None, help="语义色表 JSON（可选），校验图表序列颜色"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    if not os.path.exists(args.deck):
        print(f"错误：找不到文件 {args.deck}", file=sys.stderr)
        return 2

    try:
        deck = Deck(args.deck)
    except zipfile.BadZipFile:
        print(f"错误：{args.deck} 不是有效的 pptx（zip）", file=sys.stderr)
        return 2

    findings: list[Finding] = []
    check_deck(deck, findings, args.template)
    if args.plan:
        check_plan(deck, args.plan, findings)
    else:
        findings.append(
            Finding("WARN", "语义色表", 0, "未提供 --plan，语义一致性未自动核验")
        )

    # 母版基准：check_deck 里已带默认参数调用，这里补一次显式模板
    fails = [f for f in findings if f.level == "FAIL"]
    warns = [f for f in findings if f.level == "WARN"]

    if args.json:
        print(
            json.dumps(
                {
                    "file": args.deck,
                    "pass": not fails,
                    "slides": len(deck.slides),
                    "failures": [f.as_dict() for f in fails],
                    "warnings": [f.as_dict() for f in warns],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for f in findings:
            print(f.format(os.path.basename(args.deck)))
        print()
        print(
            f"{os.path.basename(args.deck)}：{len(deck.slides)} 页，"
            f"FAIL {len(fails)}，WARN {len(warns)}"
        )
        print("结果：" + ("PASS" if not fails else "FAIL"))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())