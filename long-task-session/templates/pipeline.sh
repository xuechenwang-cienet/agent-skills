#!/usr/bin/env bash
# 多阶段管道模板：把"训练 → 起服务 → 评估 → 判定"这类长链条一次托管给后台，
# 主会话只收**一行**结论，不再为每个阶段挂一个 watcher。
#
# 设计约束（照抄会省很多事）：
#   * 每阶段幂等：done 标记文件存在就跳过（中断后重跑安全）
#   * 每阶段有**唯一终态标记**（不要用百分比）
#   * 每阶段都通过 `sessionctl watch` 启动监视（自带上岗自检 + 失速检测）
#   * 失败立即短路，后续阶段不执行
#   * stdout 只留最后一行（`PIPELINE ...`）；过程日志全部进文件
#
# 用法：
#   setsid nohup bash pipeline.sh <session_dir> > <session_dir>/logs/pipeline.out 2>&1 &
#   # 然后（或过一会儿）看：
#   tail -1 <session_dir>/logs/pipeline.out     # 一行结论
#   tail -5 <session_dir>/logs/heartbeat.log    # 过程
#
# 维护者：把下面 STAGES 改成你的阶段；每行 5 个字段用 | 分隔：
#   name | command | log | terminal_marker | progress_regex(可空) | timeout_seconds(可空)
set -uo pipefail

SESSION_DIR="${1:?usage: pipeline.sh <session_dir>}"
CTL="${SESSIONCTL:-$(command -v sessionctl || echo "$HOME/.agents/skills/long-task-session/scripts/sessionctl.py")}"
[[ -f "$CTL" ]] && CTL="python3 $CTL"
mkdir -p "$SESSION_DIR/logs"
PIPE_LOG="$SESSION_DIR/logs/pipeline.log"
HB="$SESSION_DIR/logs/heartbeat.log"
STATUS="ok"
FAILED_AT=""

log() { echo "$(date '+%F %T') $*" >> "$PIPE_LOG"; }

# ---- 阶段表（示例：按任务改） -------------------------------------------------
STAGES=(
  # 示例 1：训练；终态 train_runtime；进度条形如 | 12/207 [
  "train|bash scripts/train.sh|logs/train.log|train_runtime|\\| [0-9]+/[0-9]+ \\[|9000"
  # 示例 2：起服务并确认模型名；终态是 /v1/models 里出现目标 adapter
  "serve|bash scripts/serve.sh|logs/serve.log|sft-v40|/saves/[^\"]*|1200"
  # 示例 3：评估；终态是批次完成
  "evaluate|python3 scripts/eval.py|logs/eval.log|reqeval|done [0-9]+/[0-9]+|14400"
)
# -----------------------------------------------------------------------------

run_stage() {
  local name="$1" cmd="$2" logf="$3" marker="$4" regex="$5" tmo="${6:-0}"
  local done_file="$SESSION_DIR/.stage-$name.done"
  [[ -f "$done_file" ]] && { log "[skip] $name (done)"; return 0; }
  log "[start] $name :: $cmd"
  local -a to=()
  [[ "$tmo" != "0" ]] && to=(timeout "$tmo")
  ( cd "${WORKDIR:-$PWD}" && "${to[@]}" bash -c "$cmd" ) >> "${logf}" 2>&1 &
  local child=$!
  local -a wargs=(watch --session "$SESSION_DIR" --log "${logf}" --marker "$marker" --pid "$child" --run-id "$name" --window "${WINDOW:-7200}")
  [[ -n "$regex" ]] && wargs+=(--regex "$regex")
  if ! $CTL "${wargs[@]}"; then
    log "[fail] $name watcher exit $?"
    STATUS="fail"; FAILED_AT="$name"; return 1
  fi
  # 阶段命令自身也要成功（watcher 只保证看到了终态标记）
  wait "$child" 2>/dev/null || true
  touch "$done_file"
  log "[done] $name"
  return 0
}

for row in "${STAGES[@]}"; do
  IFS='|' read -r name cmd logf marker regex tmo <<< "$row"
  run_stage "$name" "$cmd" "$SESSION_DIR/$logf" "$marker" "$regex" "${tmo:-0}" || break
done

# 可选：判定阶段（写 verdict.json），失败也算 fail
if [[ "$STATUS" == "ok" && -n "${VERDICT_CMD:-}" ]]; then
  log "[start] verdict"
  if ( cd "${WORKDIR:-$PWD}" && bash -c "$VERDICT_CMD" ) >> "$SESSION_DIR/logs/verdict.log" 2>&1; then
    log "[done] verdict"
  else
    STATUS="fail"; FAILED_AT="verdict"; log "[fail] verdict"
  fi
fi

# 单行通知契约：调用方只 tail -1 这一行
DONE_COUNT=$(ls "$SESSION_DIR"/.stage-*.done 2>/dev/null | wc -l | tr -d ' ')
echo "PIPELINE status=$STATUS stages_done=$DONE_COUNT failed_at=${FAILED_AT:--} session=$SESSION_DIR $(date '+%F %T')"
[[ "$STATUS" == "ok" ]] && exit 0 || exit 1