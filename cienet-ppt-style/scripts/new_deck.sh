#!/usr/bin/env bash
# 从 CIeNET 母版生成一份 0 页、16:9 的空稿。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$SCRIPT_DIR/../assets/cienet_theme.pptx"

usage() {
  cat <<'EOF'
用法: new_deck.sh OUT.pptx [--title "标题"] [--author "作者"] [--force]

从 assets/cienet_theme.pptx 复制母版，删除 3 页样张，写文档属性。
默认拒绝覆盖已存在的文件，加 --force 才覆盖。
EOF
}

die() { echo "错误：$*" >&2; exit 1; }

slide_count() {
  officecli view "$1" outline 2>/dev/null \
    | head -1 \
    | sed -n 's/.*| *\([0-9][0-9]*\) slide.*/\1/p'
}

OUT=""
TITLE=""
AUTHOR=""
FORCE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --title)  [ $# -ge 2 ] || die "--title 缺少值"; TITLE="$2"; shift 2 ;;
    --author) [ $# -ge 2 ] || die "--author 缺少值"; AUTHOR="$2"; shift 2 ;;
    --force)  FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*)       die "未知参数 $1" ;;
    *)
      [ -z "$OUT" ] || die "只能指定一个输出文件"
      OUT="$1"; shift ;;
  esac
done

[ -n "$OUT" ] || { usage; exit 2; }
case "$OUT" in *.pptx) ;; *) die "输出文件必须以 .pptx 结尾" ;; esac

command -v officecli >/dev/null 2>&1 \
  || die "找不到 officecli。安装：curl -fsSL https://d.officecli.ai/install.sh | bash（不要改用 python-pptx）"
[ -s "$TEMPLATE" ] || die "找不到或读不到母版：$TEMPLATE"

if [ -e "$OUT" ] && [ "$FORCE" -ne 1 ]; then
  die "$OUT 已存在；确认覆盖请加 --force"
fi

mkdir -p "$(dirname "$OUT")"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/cienet-deck-XXXXXX")"
TMP="$TMP_DIR/deck.pptx"
trap 'rm -rf "$TMP_DIR"' EXIT

cp "$TEMPLATE" "$TMP"

count="$(slide_count "$TMP")"
[ -n "$count" ] || die "无法读取母版页数（officecli view outline 输出异常）"

while [ "$count" -gt 0 ]; do
  officecli remove "$TMP" "/slide[1]" >/dev/null
  count=$((count - 1))
done

if [ -n "$TITLE" ] || [ -n "$AUTHOR" ]; then
  props=()
  [ -n "$TITLE" ] && props+=(--prop "title=$TITLE")
  [ -n "$AUTHOR" ] && props+=(--prop "author=$AUTHOR")
  officecli set "$TMP" / "${props[@]}" >/dev/null
fi

officecli save "$TMP" >/dev/null

remaining="$(slide_count "$TMP")"
[ "$remaining" = "0" ] || die "删除样张失败，仍有 $remaining 页"

size="$(officecli get "$TMP" / | tr ' ' '\n' | grep '^slideSize=' || true)"
[ "$size" = "slideSize=widescreen" ] || die "画布不是 16:9（$size）"

mv "$TMP" "$OUT"
trap - EXIT

echo "已创建：$OUT"
[ -n "$TITLE" ] && echo "  标题：$TITLE"
echo
echo "下一步："
echo "  officecli add \"$OUT\" / --type slide --prop \"layout=TITLE PAGE 1\""
echo "  # 按 references/layouts.md 的坐标加 textbox"
echo "  bash \"$SCRIPT_DIR/preview.sh\" \"$OUT\" --out preview/"
echo "  python3 \"$SCRIPT_DIR/check_style.py\" \"$OUT\""