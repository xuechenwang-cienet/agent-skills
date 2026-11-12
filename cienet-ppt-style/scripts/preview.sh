#!/usr/bin/env bash
# 生成整份材料的缩略总览 + 逐页 PNG，供人工/视觉模型检查。
set -euo pipefail

usage() {
  cat <<'EOF'
用法: preview.sh DECK.pptx [--out DIR] [--grid N]

--out   输出目录（默认 preview/）
--grid  总览图的列数（默认 2）
EOF
}

die() { echo "错误：$*" >&2; exit 1; }

DECK=""
OUT_DIR="preview"
GRID=2

while [ $# -gt 0 ]; do
  case "$1" in
    --out)  [ $# -ge 2 ] || die "--out 缺少值"; OUT_DIR="$2"; shift 2 ;;
    --grid) [ $# -ge 2 ] || die "--grid 缺少值"; GRID="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    -*) die "未知参数 $1" ;;
    *)  [ -z "$DECK" ] || die "只能指定一个 pptx"; DECK="$1"; shift ;;
  esac
done

[ -n "$DECK" ] || { usage; exit 2; }
[ -f "$DECK" ] || die "找不到文件 $DECK"
command -v officecli >/dev/null 2>&1 || die "找不到 officecli"

mkdir -p "$OUT_DIR"

count="$(officecli view "$DECK" outline 2>/dev/null \
  | head -1 | sed -n 's/.*| *\([0-9][0-9]*\) slide.*/\1/p')"
[ -n "$count" ] || die "无法读取页数"

echo "共 $count 页，输出到 $OUT_DIR/"

officecli view "$DECK" screenshot --grid "$GRID" -o "$OUT_DIR/overview.png" >/dev/null
echo "  总览：$OUT_DIR/overview.png"

i=1
while [ "$i" -le "$count" ]; do
  out="$OUT_DIR/slide-$i.png"
  if officecli view "$DECK" screenshot --page "$i" -o "$out" >/dev/null 2>&1; then
    echo "  第 $i 页：$out"
  else
    echo "  第 $i 页：渲染失败（用 officecli view \"$DECK\" screenshot --page $i 单独排查）" >&2
  fi
  i=$((i + 1))
done

echo "完成。逐页核对 references/qa.md 的看图清单。"