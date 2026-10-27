#!/usr/bin/env bash
# inventory_docx.sh — docx 机器盘点（officecli）
# 用法: inventory_docx.sh FILE OUTDIR
#
# 注意：officecli 驻留在访问后会重写文件的 OfficeCLI.* 自定义属性（包括只读访问
# 触发的空闲刷新）。因此：先建快照（diff_snapshot.py snap），再跑本脚本；
# 交付前必须再跑 final_clean.py 清残留。
set -euo pipefail
FILE="$1"; OUT="$2"
mkdir -p "$OUT"

officecli view "$FILE" outline > "$OUT/outline.txt" 2>&1 || true
officecli view "$FILE" stats   > "$OUT/stats.txt"   2>&1 || true
officecli view "$FILE" issues  > "$OUT/issues.txt"  2>&1 || true
officecli view "$FILE" text    > "$OUT/text.txt"    2>&1 || true

{
  echo "== docx 结构断言 =="
  echo "-- 标题层级分布 --"
  grep -oE '\((heading [0-9]|Title|Subtitle)\)' "$OUT/outline.txt" | sort | uniq -c || true
  echo "-- 章节编号连续性（outline 中的数字标题）--"
  grep -oE '\[[0-9]+\] "[^"]*" \(heading 1\)' "$OUT/outline.txt" | wc -l | xargs echo "heading1 数:"
  echo "-- TOC 域 --"
  officecli raw "$FILE" /document 2>/dev/null | grep -o 'TOC [^"<]*' | head -2 || echo "(无 TOC 域)"
  echo "-- updateFields --"
  officecli raw "$FILE" word/settings.xml 2>/dev/null | grep -o '<w:updateFields[^/]*/>' || echo "(未设置)"
  echo "-- 自定义属性 --"
  officecli raw "$FILE" docProps/custom.xml 2>/dev/null | grep -oE 'name="[^"]*"' || echo "(无)"
  echo "-- 页眉/页脚文本 --"
  for p in /header[1] /footer[1] /footer[2] /footer[3]; do
    runs=$(officecli raw "$FILE" "$p" 2>/dev/null | grep -oE '<w:t[^>]*>[^<]*</w:t>' | sed 's/<[^>]*>//g' | tr '\n' '|' || true)
    if [ -n "$runs" ]; then echo "  $p: $runs"; fi
  done
  echo "-- issues 摘要 --"
  grep -E '^Found|^[A-Za-z]+ Issues' "$OUT/issues.txt" || echo "(无)"
} > "$OUT/assertions.txt" 2>&1

echo "inventory written to $OUT"
grep -E '^Found' "$OUT/issues.txt" || true
