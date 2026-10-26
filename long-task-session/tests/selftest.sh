#!/usr/bin/env bash
# sessionctl 自测（18 条）。用法：bash tests/selftest.sh
# 所有产物落在 $TMP，不污染技能仓库，也不依赖真实项目数据。
set -uo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
CTL="python3 $HERE/scripts/sessionctl.py"
TMP="${SELFTEST_ROOT:-/tmp/opencode/lts-selftest}"
rm -rf "$TMP"; mkdir -p "$TMP"

pass=0; fail=0
ok()   { printf '  \033[32mPASS\033[0m %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31mFAIL\033[0m %s — %s\n' "$1" "${2:-}"; fail=$((fail+1)); }
check(){ # name expected_code actual_code detail
  if [[ "$2" == "$3" ]]; then ok "$1"; else bad "$1" "expected exit $2, got $3 ${4:-}"; fi
}

fill_plan() { # $1 = session dir
  python3 - "$1/SESSION_PLAN.md" <<'PY'
import re, sys
p = sys.argv[1]
t = open(p, encoding='utf-8').read()
t = re.sub(r'TODO:[^\n]*', '已完成（示意）', t)
open(p, 'w', encoding='utf-8').write(t)
PY
}
fill_acceptance() { # $1 = session dir
  python3 - "$1/SESSION_LOG.md" <<'PY'
import re, sys
p = sys.argv[1]
t = open(p, encoding='utf-8').read()
t = re.sub(r'^\s*(?:- )?TODO:[^\n]*$', lambda m: (m.group(0).lstrip()[:2] if m.group(0).lstrip().startswith('- ') else '') + '无', t, flags=re.M)
open(p, 'w', encoding='utf-8').write(t)
PY
}

echo "== 1. new (full) + 幂等"
$CTL new demo --root "$TMP" >/dev/null 2>&1
d="$TMP/$(ls "$TMP" | head -1)"
[[ -f "$d/state.json" && -f "$d/SESSION_PLAN.md" && -f "$d/SESSION_LOG.md" && -f "$d/NEXT_PLAN.md" && -d "$d/logs" ]] \
  && ok "生成四份文档 + state.json + logs/" || bad "生成四份文档 + state.json + logs/" "$d"
[[ "$(python3 -c "import json;print(json.load(open('$d/state.json'))['stage'])")" == "S0" ]] && ok "stage=S0" || bad "stage=S0"
$CTL new demo --root "$TMP" >/dev/null 2>&1; check "同名重复 new 幂等（不覆盖）" 0 $?

echo "== 2. lite 模式"
$CTL new lite-demo --lite --root "$TMP" >/dev/null 2>&1
ld=$(ls -td "$TMP"/*lite-demo | head -1)
[[ -f "$ld/SESSION_PLAN.md" && ! -d "$ld/logs" ]] && ok "lite 只生成文档与 state" || bad "lite 只生成文档与 state"
$CTL verify --session "$ld" >/dev/null 2>&1; check "lite verify 跳过并返回 0" 0 $?

echo "== 3. status 门槛"
$CTL status --session "$d" >/dev/null 2>&1; check "空 plan → status=1" 1 $?
fill_plan "$d"
$CTL status --session "$d" >/dev/null 2>&1; check "plan 填满但 gates 空 → 仍 1" 1 $?
$CTL state gates.demo.threshold ">=1" --session "$d" >/dev/null 2>&1
$CTL state gates.demo.verdict pass --session "$d" >/dev/null 2>&1
fill_acceptance "$d"
$CTL status --session "$d" >/dev/null 2>&1; check "全部填满 → status=0" 0 $?

echo "== 4/5. ckpt 与 verify"
echo "hello" > "$d/artifacts/a.txt"
$CTL ckpt art-a --artifact artifacts/a.txt --session "$d" >/dev/null 2>&1; check "ckpt 登记本地产物" 0 $?
$CTL verify --session "$d" >/dev/null 2>&1; check "verify 通过" 0 $?
echo "tampered" > "$d/artifacts/a.txt"
$CTL verify --session "$d" >/dev/null 2>&1; check "篡改后 verify=1" 1 $?
echo "hello" > "$d/artifacts/a.txt"
$CTL ckpt remote-art --artifact /nonexistent/remote.bin --sha256 deadbeef --session "$d" >/dev/null 2>&1
check "ckpt 远端产物（--sha256）" 0 $?
$CTL verify --session "$d" 2>&1 | grep -q "调用方哈希" && ok "远端产物标注未本地校验" || bad "远端产物标注未本地校验"

echo "== 6. note / resume"
$CTL note "第一条记录" --key k1 --session "$d" >/dev/null 2>&1; check "note 写入" 0 $?
$CTL note "重复记录" --key k1 --session "$d" 2>&1 | grep -q "skip" && ok "note --key 去重" || bad "note --key 去重"
$CTL resume --session "$d" >/dev/null 2>&1; check "resume 正常（产物完好）" 0 $?
out=$($CTL resume --session "$d" --prompt 2>&1)
for kw in "不要重新评估" "不要改动 gold" "不要用单条样本"; do
  echo "$out" | grep -q "$kw" && ok "resume --prompt 含禁止项：$kw" || bad "resume --prompt 含禁止项：$kw"
done

echo "== N1. resume 会主动校验产物"
cp "$d/artifacts/a.txt" /tmp/keep-a.txt
echo "broken" > "$d/artifacts/a.txt"
$CTL resume --session "$d" >/dev/null 2>&1; check "产物被改后 resume=1" 1 $?
cp /tmp/keep-a.txt "$d/artifacts/a.txt"

echo "== 7. close / backup"
d2="$ld"
$CTL close --session "$d2" >/dev/null 2>&1; check "lite 未填验收 → close=1" 1 $?
fill_plan "$d2"; fill_acceptance "$d2"
$CTL state gates.x.threshold ">=1" --session "$d2" >/dev/null 2>&1
$CTL state gates.x.verdict pass --session "$d2" >/dev/null 2>&1
$CTL close --session "$d2" --backup "$TMP/backups" >/dev/null 2>&1; check "验收填满 → close=0" 0 $?
pkg=$(ls "$TMP/backups"/*.tar.* 2>/dev/null | head -1)
[[ -n "$pkg" && -f "$pkg.sha256" ]] && ok "生成备份包 + sha256" || bad "生成备份包 + sha256"
grep -q "备份：" "$d2/ARTIFACTS.md" && ok "备份路径写回 ARTIFACTS.md" || bad "备份路径写回 ARTIFACTS.md"

echo "== N2. close 校验每条 gate 有判定"
$CTL new gates --root "$TMP" >/dev/null 2>&1
g3=$(ls -td "$TMP"/*-gates | head -1)
fill_plan "$g3"
fill_acceptance "$g3"
$CTL state gates.a.threshold ">=1" --session "$g3" >/dev/null 2>&1
$CTL close --session "$g3" --backup "$TMP/backups" >/dev/null 2>&1; check "gate 无 verdict → close=1" 1 $?
$CTL state gates.a.verdict neutral --session "$g3" >/dev/null 2>&1
$CTL close --session "$g3" --backup "$TMP/backups" >/dev/null 2>&1; check "gate 有 verdict → close=0" 0 $?

echo "== 8. list / reconcile"
$CTL list --root "$TMP" | tail -n +2 | awk '{print $1}' > "$TMP/_list.txt"
sort "$TMP/_list.txt" > "$TMP/_sorted.txt"
diff -q "$TMP/_list.txt" "$TMP/_sorted.txt" >/dev/null && ok "list 按目录名排序" || bad "list 按目录名排序"
$CTL reconcile --root "$TMP" 2>&1 | grep -q "最新会话" && ok "reconcile 摘要" || bad "reconcile 摘要"

echo "== 9. 心跳判活"
mkdir -p "$d/logs"; echo "$(date +%s) x" > "$d/logs/heartbeat.log"
hb1=$($CTL status --session "$d" 2>&1 | grep "心跳")
echo "$hb1" | grep -q "running" && ok "新鲜心跳 → running" || bad "新鲜心跳 → running" "[$hb1]"
touch -d "40 minutes ago" "$d/logs/heartbeat.log"
hb2=$($CTL status --session "$d" 2>&1 | grep "心跳")
echo "$hb2" | grep -q "stale" && ok "过期心跳 → stale" || bad "过期心跳 → stale" "[$hb2]"

echo "== 10. state 白名单"
$CTL state gates.newg.measured 42 --session "$d" >/dev/null 2>&1; check "接受 gates.*.measured" 0 $?
$CTL state bogus.key 1 --session "$d" >/dev/null 2>&1; check "拒绝未知键（exit 2）" 2 $?
$CTL state stage S9 --session "$d" >/dev/null 2>&1; check "拒绝非法 stage（exit 2）" 2 $?

echo "== 11. slug 冲突"
$CTL new demo --suffix --root "$TMP" >/dev/null 2>&1; check "--suffix 生成新目录" 0 $?
ls "$TMP" | grep -q -- "-demo-2" && ok "目录名为 -demo-2" || bad "目录名为 -demo-2"

echo "== 12. 编译与 stdlib"
python3 -m py_compile "$HERE/scripts/sessionctl.py" 2>/dev/null; check "py_compile 通过" 0 $?
grep -qE "^(import|from) (requests|yaml|numpy|pandas)" "$HERE/scripts/sessionctl.py" && bad "仅使用 stdlib" || ok "仅使用 stdlib"

echo "== N5. TZ=UTC 复跑"
TZ=UTC $CTL new tzcase --root "$TMP/tz" >/dev/null 2>&1; check "TZ=UTC 下 new 正常" 0 $?
grep -q "+00:00" "$TMP/tz/$(ls "$TMP/tz" | head -1)/state.json" && ok "时间戳带 +00:00 偏移" || bad "时间戳带 +00:00 偏移"

echo "== N6. README 安装命令可执行性（owner 拼写）"
if [[ -f "$HERE/../README.md" ]]; then
  grep -q "xuechenwang-cienet/agent-skills" "$HERE/../README.md" && ok "README owner 正确" || bad "README owner 正确"
  grep -q "xuechen.xin" "$HERE/../README.md" && bad "README 无错误 owner" || ok "README 无错误 owner"
else
  ok "README 检查跳过（安装副本无仓库根 README）"
fi

echo "== T1. 目录产物不崩（B1）"
$CTL new d1 --root "$TMP/t" >/dev/null 2>&1; s1=$(ls -td "$TMP/t"/*-d1 | head -1)
mkdir -p "$s1/artifacts/sub" && echo x > "$s1/artifacts/sub/x.txt"
$CTL ckpt dir-art --artifact artifacts/sub --session "$s1" >/dev/null 2>&1; check "ckpt 目录产物" 0 $?
v=$($CTL verify --session "$s1" 2>&1); rc=$?
check "verify 目录产物不崩" 0 $rc "$v"
echo "$v" | grep -q "目录产物" && ok "verify 标注目录产物" || bad "verify 标注目录产物"
$CTL status --session "$s1" >/dev/null 2>&1; rc=$?
{ [[ $rc -eq 0 || $rc -eq 1 ]]; } && ok "status 目录产物不崩（退出码 0/1）" || bad "status 目录产物不崩" "exit=$rc"

echo "== T2. close --backup 不带值（B2）"
$CTL new d2 --root "$TMP/t" >/dev/null 2>&1; s2=$(ls -td "$TMP/t"/*-d2 | head -1)
fill_plan "$s2"; fill_acceptance "$s2"
$CTL state gates.g.threshold ">=1" --session "$s2" >/dev/null 2>&1
$CTL state gates.g.verdict pass --session "$s2" >/dev/null 2>&1
SESSION_BACKUP_DIR="$TMP/t/bk2" $CTL close --backup --session "$s2" >/dev/null 2>&1; check "close --backup（无值）" 0 $?
ls "$TMP/t/bk2"/*.tar.* >/dev/null 2>&1 && ok "备份落在 SESSION_BACKUP_DIR" || bad "备份落在 SESSION_BACKUP_DIR"

echo "== T3/T4. launcher 模板实跑（B3/B4）"
s3="$TMP/t/launchcase"; mkdir -p "$s3/logs"
out=$(SESSION_DIR="$s3" NAME=lt CMD="sleep 1; echo started" TERMINAL_MARKER=started \
      EARLY_SIGNAL=started EARLY_WAIT=5 bash "$HERE/templates/launcher.sh" 2>&1); rc=$?
check "launcher 正常退出" 0 $rc "$out"
echo "$out" | grep -q "bad substitution" && bad "launcher 无 bad substitution" "$out" || ok "launcher 无 bad substitution"
[[ -f "$s3/logs/lt.pid" ]] && ok "PIDFILE 生成" || bad "PIDFILE 生成"
NAME=lt4 CMD="sleep 5" SESSION_DIR="$s3" TERMINAL_MARKER=never bash "$HERE/templates/launcher.sh" >/dev/null 2>&1
out2=$(NAME=lt4 CMD="sleep 5" SESSION_DIR="$s3" TERMINAL_MARKER=never bash "$HERE/templates/launcher.sh" 2>&1); rc2=$?
echo "$out2" | grep -q "already running" && ok "二次启动被拒（幂等）" || bad "二次启动被拒" "$out2"
check "二次启动退出码 0" 0 $rc2

echo "== T5. ckpt 去重（S1）"
$CTL ckpt dup --artifact artifacts/sub --session "$s1" >/dev/null 2>&1
before=$(python3 -c "import json;print(len(json.load(open('$s1/state.json'))['runs']))")
rows_before=$(grep -c '^| `' "$s1/ARTIFACTS.md")
$CTL ckpt dup --artifact artifacts/sub --session "$s1" 2>&1 | grep -q "skip" && ok "同名同产物 skip" || bad "同名同产物 skip"
after=$(python3 -c "import json;print(len(json.load(open('$s1/state.json'))['runs']))")
rows_after=$(grep -c '^| `' "$s1/ARTIFACTS.md")
[[ "$before" == "$after" && "$rows_before" == "$rows_after" ]] && ok "runs/ARTIFACTS 未重复" || bad "runs/ARTIFACTS 未重复" "$before/$after $rows_before/$rows_after"
$CTL ckpt dup --artifact artifacts/sub/x.txt --session "$s1" >/dev/null 2>&1; check "同名异产物 → 退出 2" 2 $?

echo "== T6. close 推进 stage（S3）"
python3 -c "import json,sys;d=json.load(open('$s2/state.json'));sys.exit(0 if d['stage']=='S5' and d['status']=='done' else 1)"
check "close 后 stage=S5 / status=done" 0 $?

echo "== T7. blockers 类型校验（S4）"
$CTL state blockers "等待" --session "$s1" >/dev/null 2>&1; check "字符串 blockers 被拒（exit 2）" 2 $?
$CTL state blockers '["等待用户拍板"]' --json --session "$s1" >/dev/null 2>&1; check "JSON 数组 blockers 通过" 0 $?
$CTL resume --session "$s1" 2>&1 | grep -q "等待用户拍板" && ok "blockers 正常渲染（不拆字符）" || bad "blockers 正常渲染"

echo "== T8. 正文含 {{ 不误报（S7）"
cp "$s2/SESSION_PLAN.md" "$s2/plan.bak"
printf '\n示例代码：\n```\n{{ 不是占位符 }}\n```\n' >> "$s2/SESSION_PLAN.md"
$CTL status --session "$s2" 2>&1 | grep -A1 "plan 七件硬内容" | grep -q "✅" && ok "含 {{ 的正文不误报" || bad "含 {{ 的正文不误报"
mv "$s2/plan.bak" "$s2/SESSION_PLAN.md"

echo "== T9. close 因 plan 未填被拒（N1）"
$CTL new d9 --root "$TMP/t" >/dev/null 2>&1; s9=$(ls -td "$TMP/t"/*-d9 | head -1)
fill_acceptance "$s9"
$CTL state gates.g.threshold ">=1" --session "$s9" >/dev/null 2>&1
$CTL state gates.g.verdict pass --session "$s9" >/dev/null 2>&1
$CTL close --backup --session "$s9" >/dev/null 2>&1; check "plan 有 TODO → close=1" 1 $?
$CTL close --backup --force --session "$s9" >/dev/null 2>&1; check "--force 可强制归档" 0 $?

echo "== N2. watcher 进度消毒"
mkdir -p "$TMP/t/hb/logs"
printf 'a\nPROG 1/9 [x]\n' > "$TMP/t/hb/logs/w.log"
SESSION_DIR="$TMP/t/hb" LOG="$TMP/t/hb/logs/w.log" TERMINAL_MARKER=nope \
  PROGRESS_REGEX='[0-9]+/[0-9]+ \[' INTERVAL=1 MAX_WINDOW=2 \
  timeout 8 bash "$HERE/templates/watcher.sh" >/dev/null 2>&1
lines=$(wc -l < "$TMP/t/hb/logs/heartbeat.log" 2>/dev/null || echo 0)
[[ "$lines" -ge 1 ]] && ok "watcher 写出心跳" || bad "watcher 写出心跳"
awk '/progress=/{c++} END{exit (c>0?0:1)}' "$TMP/t/hb/logs/heartbeat.log" && ok "心跳行含 progress 字段" || bad "心跳行含 progress 字段"
grep -q "progress=1/9" "$TMP/t/hb/logs/heartbeat.log" && ok "进度被抓取为单行" || bad "进度被抓取为单行"

echo "== T10. resume --prompt 退出码（S6）"
$CTL new d10 --root "$TMP/t" >/dev/null 2>&1; s10=$(ls -td "$TMP/t"/*-d10 | head -1)
echo ok > "$s10/artifacts/f.txt"
$CTL ckpt f --artifact artifacts/f.txt --session "$s10" >/dev/null 2>&1
$CTL resume --session "$s10" --prompt >/dev/null 2>&1; check "产物完好 → resume --prompt=0" 0 $?
echo broken > "$s10/artifacts/f.txt"
$CTL resume --session "$s10" --prompt >/dev/null 2>&1; check "产物损坏 → resume --prompt=1" 1 $?

echo
echo "==== 结果：PASS=$pass FAIL=$fail ===="
[[ $fail -eq 0 ]]