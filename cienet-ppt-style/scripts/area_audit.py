#!/usr/bin/env python3
"""洋红与面积审计：逐页打印洋红占比和超限元素。

和 check_style.py 共用同一套解析与面积算法，避免两处口径不一致。
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_style as cs  # noqa: E402


def cm2(area_emu: int) -> float:
    return area_emu / cs.EMU_PER_CM / cs.EMU_PER_CM


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CIeNET PPT 洋红与面积审计")
    parser.add_argument("deck", help="待审计的 .pptx")
    parser.add_argument(
        "--top", type=int, default=3, help="每页列出最大的 N 个洋红元素（默认 3）"
    )
    args = parser.parse_args(argv)

    if not os.path.exists(args.deck):
        print(f"错误：找不到文件 {args.deck}", file=sys.stderr)
        return 2

    deck = cs.Deck(args.deck)
    slide_area_cm2 = cs.SLIDE_AREA / cs.EMU_PER_CM / cs.EMU_PER_CM
    print(f"{os.path.basename(args.deck)}：{len(deck.slides)} 页，页面积 {slide_area_cm2:.1f}cm²")
    print(f"洋红 #{cs.MAGENTA} 上限 {cs.MAGENTA_MAX_RATIO * 100:.0f}% = "
          f"{slide_area_cm2 * cs.MAGENTA_MAX_RATIO:.1f}cm²/页")
    print()

    over = 0
    total_magenta = 0
    for s in deck.slides:
        ratio = s.area_magenta / cs.SLIDE_AREA if cs.SLIDE_AREA else 0
        total_magenta += s.area_magenta
        flag = "FAIL" if ratio > cs.MAGENTA_MAX_RATIO else "ok  "
        if ratio > cs.MAGENTA_MAX_RATIO:
            over += 1
        label = f"slide {s.number:>2} [{flag}] 洋红 {ratio * 100:5.1f}%  {cm2(s.area_magenta):6.1f}cm²"
        if s.magenta_items:
            items = sorted(s.magenta_items, key=lambda x: -x[1])[: args.top]
            extra = "；".join(f"{n} {cm2(a):.1f}cm²" for n, a in items)
            print(f"{label}  ← {extra}")
        else:
            print(label)

    print()
    print(f"合计：{len(deck.slides)} 页，超限 {over} 页，"
          f"洋红总面积 {cm2(total_magenta):.1f}cm²")

    # 颜色使用分布，帮助发现"色卡外颜色"
    colors = Counter()
    for s in deck.slides:
        colors.update(s.colors)
    if colors:
        print("\n显式色值使用分布（前 10）：")
        for color, count in colors.most_common(10):
            mark = "" if color in cs.ALLOWED_COLORS else "  ← 不在允许集合"
            print(f"  #{color}  {count} 次{mark}")

    return 1 if over else 0


if __name__ == "__main__":
    sys.exit(main())