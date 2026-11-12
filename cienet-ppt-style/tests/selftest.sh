#!/usr/bin/env bash
# cienet-ppt-style 自测：正向流程 + 6 类必须被拦下的违规。
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$SKILL_DIR/scripts"
ASSETS="$SKILL_DIR/assets"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/cienet-selftest-XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

PASS=0
FAIL=0
SKIP=0

ok()   { PASS=$((PASS + 1)); echo "  PASS  $1"; }
bad()  { FAIL=$((FAIL + 1)); echo "  FAIL  $1"; [ -n "${2:-}" ] && echo "        $2"; }
skip() { SKIP=$((SKIP + 1)); echo "  SKIP  $1"; }

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "缺少依赖：$1" >&2
    exit 2
  fi
}

require python3
require officecli

new_deck() { # new_deck <out> [extra args...]
  local out="$1"; shift
  bash "$SCRIPTS/new_deck.sh" "$out" "$@" >/dev/null 2>&1
}

finish_deck() {
  officecli save "$1" >/dev/null 2>&1
  officecli close "$1" >/dev/null 2>&1 || true
}

# run_check <deck> [args] → 退出码写入 CHECK_RC，输出留在 $WORK/check.log
run_check() {
  local deck="$1"; shift
  python3 "$SCRIPTS/check_style.py" "$deck" "$@" >"$WORK/check.log" 2>&1
  CHECK_RC=$?
}

expect_pass() { # expect_pass <name> <deck> [args]
  local name="$1" deck="$2"; shift 2
  run_check "$deck" "$@"
  if [ "$CHECK_RC" -eq 0 ]; then
    ok "$name"
  else
    bad "$name" "$(grep -m3 FAIL "$WORK/check.log" | tr '\n' ' ')"
  fi
}

expect_fail() { # expect_fail <name> <deck> <keyword>
  local name="$1" deck="$2" keyword="${3:-FAIL}"
  run_check "$deck"
  if [ "$CHECK_RC" -ne 1 ]; then
    bad "$name" "期望退出码 1，实际 $CHECK_RC"
  elif ! grep -q "$keyword" "$WORK/check.log"; then
    bad "$name" "报告里没有出现关键字 '$keyword'"
  else
    ok "$name"
  fi
}

echo "== 1. 建稿 =="

D1="$WORK/deck1.pptx"
if new_deck "$D1" --title "自测标题" --author "自测作者"; then
  n="$(officecli view "$D1" outline | head -1 | sed -n 's/.*| *\([0-9][0-9]*\) slide.*/\1/p')"
  meta="$(officecli get "$D1" / | tr ' ' '\n' | grep -E '^(title|author|slideSize)=' | tr '\n' ' ')"
  if [ "$n" = "0" ]; then ok "空稿 0 页"; else bad "空稿 0 页" "实际 $n 页"; fi
  if echo "$meta" | grep -q 'title=自测标题' && echo "$meta" | grep -q 'author=自测作者'; then
    ok "文档属性写入"
  else
    bad "文档属性写入" "$meta"
  fi
  if echo "$meta" | grep -q 'slideSize=widescreen'; then
    ok "16:9 画布"
  else
    bad "16:9 画布" "$meta"
  fi
else
  bad "建稿" "new_deck.sh 失败"
fi

if new_deck "$D1" >/dev/null 2>&1; then
  bad "拒绝覆盖已存在文件"
else
  ok "拒绝覆盖已存在文件"
fi

if new_deck "$D1" --force >/dev/null 2>&1; then
  ok "--force 允许覆盖"
else
  bad "--force 允许覆盖"
fi

finish_deck "$D1"

echo "== 2. 合规样张 =="

DEMO="$WORK/demo.pptx"
new_deck "$DEMO" --title "合规样张" --author "自测" || bad "demo 建稿"

# 封面
officecli add "$DEMO" / --type slide --prop "layout=TITLE PAGE 1" >/dev/null
officecli add "$DEMO" "/slide[last()]" --type textbox --prop name=CoverTitle \
  --prop x=4.0cm --prop y=6.6cm --prop w=25.87cm --prop h=2.7cm \
  --prop "text=CIeNET 交付平台改造方案" --prop font=Calibri --prop size=54 --prop bold=true \
  --prop color=#FFFFFF --prop align=center >/dev/null
officecli add "$DEMO" "/slide[last()]" --type textbox --prop name=CoverSub \
  --prop x=4.0cm --prop y=9.1cm --prop w=25.87cm --prop h=1.4cm \
  --prop "text=2026 年 Q4 技术路线" --prop font=Calibri --prop size=24 \
  --prop color=#FFFFFF --prop align=center >/dev/null

# 目录
officecli add "$DEMO" / --type slide --prop "layout=AGENDA 1" >/dev/null
officecli add "$DEMO" "/slide[last()]" --type textbox --prop name=AgendaBody \
  --prop x=15.76cm --prop y=2.85cm --prop w=15.36cm --prop h=14.5cm \
  --prop "text=01  现状与问题\n02  改造目标\n03  技术方案" --prop font=Calibri \
  --prop size=22 --prop color=#1A1A1A --prop lineSpacing=1.8x >/dev/null

# 内容页
officecli add "$DEMO" / --type slide --prop "layout=Title and Content" >/dev/null
officecli add "$DEMO" "/slide[last()]" --type textbox --prop name=Title \
  --prop x=0.68cm --prop y=0.64cm --prop w=30.62cm --prop h=1.75cm \
  --prop "text=构建等待从 42 分钟降到 22 分钟" --prop font=Calibri --prop size=32 \
  --prop bold=true --prop color=#1A1A1A >/dev/null
officecli add "$DEMO" "/slide[last()]" --type textbox --prop name=Eyebrow \
  --prop x=0.68cm --prop y=2.45cm --prop w=30.62cm --prop h=1.2cm \
  --prop "text=现状分析" --prop font=Calibri --prop size=20 --prop bold=true \
  --prop color=#6D97D2 >/dev/null
officecli add "$DEMO" "/slide[last()]" --type textbox --prop name=Body \
  --prop x=1.26cm --prop y=4.09cm --prop w=31.39cm --prop h=13.07cm \
  --prop "text=全量构建 38 分钟，依赖下载占 21 分钟\n缓存命中率 34%\nCPU 峰值利用率 18%" \
  --prop font=Calibri --prop size=22 --prop color=#1A1A1A --prop lineSpacing=1.5x >/dev/null
for p in 1 2 3; do
  officecli set "$DEMO" "/slide[3]/shape[@name=Body]/paragraph[$p]" --prop list=bullet >/dev/null
done
officecli add "$DEMO" "/slide[3]" --type notes --prop text="先给基线数字。" >/dev/null

# 图表页（合规：蓝 + 紫，洋红只作小点）
officecli add "$DEMO" / --type slide --prop "layout=Title and Content" >/dev/null
officecli add "$DEMO" "/slide[last()]" --type textbox --prop name=Title \
  --prop x=0.68cm --prop y=0.64cm --prop w=30.62cm --prop h=1.75cm \
  --prop "text=目标方案命中率提升到 78%" --prop font=Calibri --prop size=32 \
  --prop bold=true --prop color=#1A1A1A >/dev/null
officecli add "$DEMO" "/slide[last()]" --type chart --prop chartType=column \
  --prop series1.name="现状" --prop series1.values="38,34" --prop series1.color=2453B3 \
  --prop series2.name="目标" --prop series2.values="22,78" --prop series2.color=5230A2 \
  --prop categories="构建耗时,命中率" --prop x=1.26cm --prop y=4.5cm --prop w=19cm --prop h=12cm >/dev/null
officecli add "$DEMO" "/slide[last()]" --type shape --prop preset=ellipse \
  --prop x=28cm --prop y=6cm --prop w=0.6cm --prop h=0.6cm --prop fill=#932193 --prop line=none >/dev/null

# 致谢
officecli add "$DEMO" / --type slide --prop "layout=Acknowledgements" >/dev/null
officecli add "$DEMO" "/slide[last()]" --type textbox \
  --prop x=4.0cm --prop y=10.2cm --prop w=25.87cm --prop h=1.0cm \
  --prop "text=Questions & Discussion" --prop font=Calibri --prop size=18 \
  --prop color=#E8EEF8 --prop align=center >/dev/null

finish_deck "$DEMO"
expect_pass "4 页合规样张 PASS" "$DEMO"

if python3 "$SCRIPTS/area_audit.py" "$DEMO" >"$WORK/area.log" 2>&1; then
  ok "area_audit 合规样张通过"
else
  bad "area_audit 合规样张通过" "$(tail -2 "$WORK/area.log" | tr '\n' ' ')"
fi

echo "== 3. 洋红面积 =="

BIG="$WORK/big_magenta.pptx"
new_deck "$BIG" >/dev/null
officecli add "$BIG" / --type slide --prop "layout=DEFAULT_1" >/dev/null
officecli add "$BIG" /slide[1] --type shape --prop preset=rect --prop x=3cm --prop y=5cm \
  --prop w=12cm --prop h=8cm --prop fill=#932193 --prop line=none >/dev/null
officecli add "$BIG" /slide[1] --type textbox --prop x=2cm --prop y=2cm --prop w=25cm --prop h=1.2cm \
  --prop "text=大面积洋红" --prop font=Calibri --prop size=32 --prop bold=true \
  --prop color=#FFFFFF >/dev/null
finish_deck "$BIG"
expect_fail "大面积洋红 FAIL" "$BIG" "洋红面积"

echo "== 4. 洋红渐变方向 =="

GRAD="$WORK/grad.pptx"
new_deck "$GRAD" >/dev/null
officecli add "$GRAD" / --type slide --prop "layout=DEFAULT_1" \
  --prop "background=932193-2453B3-0" >/dev/null
officecli add "$GRAD" /slide[1] --type textbox --prop x=2cm --prop y=2cm --prop w=25cm --prop h=1.2cm \
  --prop "text=反向渐变" --prop font=Calibri --prop size=32 --prop bold=true --prop color=#FFFFFF >/dev/null
finish_deck "$GRAD"
expect_fail "洋红作渐变起点 FAIL" "$GRAD" "洋红渐变"

GRAD_OK="$WORK/grad_ok.pptx"
new_deck "$GRAD_OK" >/dev/null
officecli add "$GRAD_OK" / --type slide --prop "layout=DEFAULT_1" \
  --prop "background=2453B3-932193-0" >/dev/null
officecli add "$GRAD_OK" /slide[1] --type textbox --prop x=2cm --prop y=2cm --prop w=25cm --prop h=1.2cm \
  --prop "text=正确渐变" --prop font=Calibri --prop size=32 --prop bold=true --prop color=#FFFFFF >/dev/null
finish_deck "$GRAD_OK"
expect_pass "洋红在末端的渐变 PASS" "$GRAD_OK"

echo "== 5. 图表 =="

CHART_BAD="$WORK/chart_bad.pptx"
new_deck "$CHART_BAD" >/dev/null
officecli add "$CHART_BAD" / --type slide --prop "layout=Title and Content" >/dev/null
officecli add "$CHART_BAD" /slide[1] --type textbox --prop x=1cm --prop y=1cm --prop w=25cm --prop h=1.2cm \
  --prop "text=感官进度" --prop font=Calibri --prop size=32 --prop bold=true --prop color=#1A1A1A >/dev/null
officecli add "$CHART_BAD" /slide[1] --type chart --prop chartType=column \
  --prop series1.name="风险" --prop series1.values="10,20" --prop series1.color=932193 \
  --prop series2.name="正常" --prop series2.values="15,25" --prop series2.color=2453B3 \
  --prop categories="A,B" --prop x=2cm --prop y=3cm --prop w=25cm --prop h=12cm >/dev/null
finish_deck "$CHART_BAD"
expect_fail "洋红作图表第 1 序列 FAIL" "$CHART_BAD" "图表首序列"

CHART_MIX="$WORK/chart_mix.pptx"
new_deck "$CHART_MIX" >/dev/null
for i in 1 2; do
  officecli add "$CHART_MIX" / --type slide --prop "layout=Title and Content" >/dev/null
  officecli add "$CHART_MIX" "/slide[$i]" --type textbox --prop x=1cm --prop y=1cm --prop w=25cm --prop h=1.2cm \
    --prop "text=图表页 $i" --prop font=Calibri --prop size=32 --prop bold=true --prop color=#1A1A1A >/dev/null
done
officecli add "$CHART_MIX" /slide[1] --type chart --prop chartType=column \
  --prop series1.name="方案A" --prop series1.values="10,20" --prop series1.color=2453B3 \
  --prop series2.name="方案B" --prop series2.values="12,22" --prop series2.color=5230A2 \
  --prop categories="Q1,Q2" --prop x=2cm --prop y=3cm --prop w=28cm --prop h=12cm >/dev/null
officecli add "$CHART_MIX" /slide[2] --type chart --prop chartType=column \
  --prop series1.name="方案A" --prop series1.values="10,20" --prop series1.color=5230A2 \
  --prop series2.name="方案B" --prop series2.values="12,22" --prop series2.color=2453B3 \
  --prop categories="Q1,Q2" --prop x=2cm --prop y=3cm --prop w=28cm --prop h=12cm >/dev/null
finish_deck "$CHART_MIX"
expect_fail "同名序列跨页异色 FAIL" "$CHART_MIX" "图表序列"

echo "== 6. 字体与色值 =="

FONT="$WORK/font.pptx"
new_deck "$FONT" >/dev/null
officecli add "$FONT" / --type slide --prop "layout=Title and Content" >/dev/null
officecli add "$FONT" /slide[1] --type textbox --prop x=1cm --prop y=1cm --prop w=25cm --prop h=1.2cm \
  --prop "text=字体违规" --prop font=Arial --prop size=32 --prop bold=true --prop color=#1A1A1A >/dev/null
finish_deck "$FONT"
expect_fail "非 Calibri 字体 FAIL" "$FONT" "字体"

COLOR="$WORK/color.pptx"
new_deck "$COLOR" >/dev/null
officecli add "$COLOR" / --type slide --prop "layout=Title and Content" >/dev/null
officecli add "$COLOR" /slide[1] --type shape --prop preset=rect --prop x=20cm --prop y=10cm \
  --prop w=3cm --prop h=2cm --prop fill=#FF0000 --prop line=none >/dev/null
officecli add "$COLOR" /slide[1] --type textbox --prop x=1cm --prop y=1cm --prop w=25cm --prop h=1.2cm \
  --prop "text=色值违规" --prop font=Calibri --prop size=32 --prop bold=true --prop color=#1A1A1A >/dev/null
finish_deck "$COLOR"
expect_fail "色卡外颜色 FAIL" "$COLOR" "色值"

echo "== 7. logo 遮挡 =="

LOGO="$WORK/logo.pptx"
new_deck "$LOGO" >/dev/null
officecli add "$LOGO" / --type slide --prop "layout=Title and Content" >/dev/null
officecli add "$LOGO" /slide[1] --type shape --prop preset=rect --prop x=32cm --prop y=1cm \
  --prop w=1.5cm --prop h=1cm --prop fill=#DAE6FB --prop line=none >/dev/null
officecli add "$LOGO" /slide[1] --type textbox --prop x=1cm --prop y=1cm --prop w=25cm --prop h=1.2cm \
  --prop "text=遮挡 logo" --prop font=Calibri --prop size=32 --prop bold=true --prop color=#1A1A1A >/dev/null
finish_deck "$LOGO"
expect_fail "遮挡 logo FAIL" "$LOGO" "logo 遮挡"

echo "== 8. 母版完整性 =="

TAMPER="$WORK/tamper.pptx"
new_deck "$TAMPER" >/dev/null
officecli add "$TAMPER" / --type slide --prop "layout=DEFAULT_1" >/dev/null
officecli add "$TAMPER" /slide[1] --type textbox --prop x=2cm --prop y=2cm --prop w=25cm --prop h=1.2cm \
  --prop "text=母版篡改" --prop font=Calibri --prop size=32 --prop bold=true --prop color=#1A1A1A >/dev/null
finish_deck "$TAMPER"
python3 - "$TAMPER" <<'EOF'
import sys, zipfile, shutil
path = sys.argv[1]
tmp = path + ".tmp"
with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename == "ppt/slideLayouts/slideLayout8.xml":
            data = data.replace(b'sz="900"', b'sz="1200"')
        zout.writestr(item, data)
shutil.move(tmp, path)
EOF
expect_fail "母版被改动 FAIL" "$TAMPER" "母版完整性"

echo "== 9. 语义色表（--plan） =="

PLAN="$WORK/plan.json"
printf '{"charts":{"现状":"#5230A2"}}' >"$PLAN"
run_check "$DEMO" --plan "$PLAN"
if [ "$CHECK_RC" -eq 1 ] && grep -q "语义色表" "$WORK/check.log"; then
  ok "--plan 与实稿不符 FAIL"
else
  bad "--plan 与实稿不符 FAIL" "$(tail -2 "$WORK/check.log" | tr '\n' ' ')"
fi

PLAN_OK="$WORK/plan_ok.json"
printf '{"charts":{"现状":"#2453B3","目标":"#5230A2"}}' >"$PLAN_OK"
expect_pass "--plan 一致 PASS" "$DEMO" --plan "$PLAN_OK"

echo "== 10. 预览脚本 =="

if bash "$SCRIPTS/preview.sh" "$DEMO" --out "$WORK/preview" >"$WORK/preview.log" 2>&1; then
  count_png="$(find "$WORK/preview" -name '*.png' | wc -l | tr -d ' ')"
  if [ "$count_png" -ge 5 ]; then
    ok "preview.sh 出图（$count_png 个 PNG）"
  else
    bad "preview.sh 出图" "只有 $count_png 个 PNG"
  fi
else
  bad "preview.sh 出图" "$(tail -3 "$WORK/preview.log" | tr '\n' ' ')"
fi

echo "== 11. 静态检查 =="

if python3 -m compileall -q "$SCRIPTS" >/dev/null 2>&1; then
  ok "Python 脚本可编译"
else
  bad "Python 脚本可编译"
fi

for f in "$SCRIPTS"/*.sh "$SKILL_DIR/tests/selftest.sh"; do
  if bash -n "$f"; then continue; else bad "bash -n $(basename "$f")"; fi
done
ok "bash 语法"

for f in SKILL.md references/palette.md references/layouts.md references/recipes.md \
         references/qa.md assets/cienet_theme.pptx assets/cienet_color_style.png \
         assets/layout-preview.png; do
  [ -s "$SKILL_DIR/$f" ] || bad "缺少 $f"
done
ok "文件齐全"

if head -1 "$SKILL_DIR/SKILL.md" | grep -q '^---$' \
  && grep -q '^name: cienet-ppt-style$' "$SKILL_DIR/SKILL.md"; then
  ok "SKILL.md frontmatter"
else
  bad "SKILL.md frontmatter"
fi

REPO_README="$(cd "$SKILL_DIR/.." && pwd)/README.md"
if [ -f "$REPO_README" ]; then
  if grep -q 'cienet-ppt-style' "$REPO_README"; then
    ok "仓库 README 已登记"
  else
    bad "仓库 README 已登记"
  fi
else
  skip "仓库 README 已登记（安装副本无仓库根）"
fi

echo
echo "==== 结果：PASS=$PASS FAIL=$FAIL SKIP=$SKIP ===="
[ "$FAIL" -eq 0 ]