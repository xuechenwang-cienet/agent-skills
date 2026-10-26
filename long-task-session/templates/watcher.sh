#!/usr/bin/env bash
# 长任务监视器模板。要点：心跳写纯文本文件、终态绑真实标记、窗口可重挂、能发现死亡、能发现"假推进"。
#
# 用法：
#   RUN_ID=train-x LOG=logs/train-x.log TERMINAL_MARKER=train_runtime \
#   PROGRESS_REGEX='\| [0-9]+/[0-9]+ \[' SESSION_DIR=./sessions/2026-01-01-demo \
#   bash watcher.sh
#
# ⚠ 总步数/总量**不要写死**：不同批次的数据量不同（实例：同一训练脚本 172 步 → 207 步）。
#   PROGRESS_REGEX 只匹配形状（`| N/M [`），不要写成 `| N/172 [`。
#   上岗前先跑 `sessionctl watch --selftest-only`，它会用夹具日志验证正则真的能抓到进度。
#
# 环境变量（全部有默认值）：
#   PROGRESS_REGEX   进度抓取正则（空=不抓进度）
#   STALE_LIMIT      连续多少次心跳进度不变视为"假推进"（默认 3；0=关闭）
#   FAIL_ON_STALE    进度连续不变达到多少次后以退出码 5 结束（默认 0=只记录不退出）
#
# 退出码：0=见到终态标记 2=进程消失但无终态 3=窗口到期（可重挂） 4=用法错误 5=进度停滞
set -uo pipefail

: "${SESSION_DIR:?SESSION_DIR required}"
: "${LOG:?LOG required}"
: "${TERMINAL_MARKER:?TERMINAL_MARKER required}"
RUN_ID="${RUN_ID:-$(basename "$LOG" .log)}"
INTERVAL="${INTERVAL:-60}"          # 心跳间隔（秒）
MAX_WINDOW="${MAX_WINDOW:-7200}"    # 单次窗口（秒），默认 2 小时
PROGRESS_REGEX="${PROGRESS_REGEX:-}"
PID="${PID:-}"
STALE_LIMIT="${STALE_LIMIT:-3}"     # 连续相同进度的心跳数阈值
FAIL_ON_STALE="${FAIL_ON_STALE:-0}"

HB="$SESSION_DIR/logs/heartbeat.log"
mkdir -p "$SESSION_DIR/logs"
[[ -f "$LOG" ]] || { echo "log not found: $LOG" >&2; exit 4; }

stamp() { echo "$(date +%s) $(date '+%F %T %z')"; }

beat() { # $1=progress $2=marker(0/1) $3=note
  echo "$(stamp) run=$RUN_ID pid=${PID:--} progress=${1:--} marker=$2 ${3:-}" >> "$HB"
}

echo "$(stamp) watcher_start run=$RUN_ID interval=${INTERVAL}s window=${MAX_WINDOW}s stale_limit=${STALE_LIMIT}" >> "$HB"
start=$(date +%s)
last_progress=""
repeats=0
last_note=""

while :; do
  # 1) 终态：只认唯一字符串，不要用百分比（别的阶段也会打印同名百分比）
  # MARKER_FIXED=1 → 按原文匹配（grep -F）；默认按正则（历史行为，支持 ^batches: 这类锚点）
  if [[ "${MARKER_FIXED:-0}" == "1" ]]; then
    marker_hit=$(grep -qF -- "$TERMINAL_MARKER" "$LOG" 2>/dev/null && echo 1 || echo 0)
  else
    marker_hit=$(grep -q -- "$TERMINAL_MARKER" "$LOG" 2>/dev/null && echo 1 || echo 0)
  fi
  if [[ "$marker_hit" == "1" ]]; then
    beat "-" 1 "terminal_marker_found"
    echo "DONE: found '$TERMINAL_MARKER' in $LOG"
    exit 0
  fi

  # 2) 进度（原文抓取，便于事后判断"是否真的在推进"）
  progress="-"
  if [[ -n "$PROGRESS_REGEX" ]]; then
    # 进度必须压成单行且限长：heartbeat 的契约是"一行一条"，多行会破坏后续解析
    progress=$(tr '\r' '\n' < "$LOG" | grep -oE "$PROGRESS_REGEX" | tail -1 | tr '\n' ' ' | cut -c1-120 || true)
    [[ -z "$progress" ]] && progress="-"
  fi

  # 2.5) 失速检测：同一条进度连续出现 N 次 = 日志没在推进（或正则抓错了东西）
  note=""
  if [[ -n "$PROGRESS_REGEX" && "$STALE_LIMIT" -gt 0 ]]; then
    if [[ "$progress" == "$last_progress" ]]; then
      repeats=$((repeats + 1))
    else
      repeats=0
      last_progress="$progress"
    fi
    if (( repeats >= STALE_LIMIT )); then
      note="stale_progress(n=${repeats})"
      # 只在状态变化时打一次 stderr，避免刷屏
      if [[ "$last_note" != "stale" ]]; then
        echo "STALE: progress unchanged for ${repeats} beats: $progress" >&2
        last_note="stale"
      fi
    else
      last_note=""
    fi
  fi

  # 3) 死亡检测：给了 PID 才判
  if [[ -n "$PID" ]] && ! kill -0 "$PID" 2>/dev/null; then
    beat "$progress" 0 "process_gone"
    echo "DEAD: pid $PID gone without terminal marker" >&2
    exit 2
  fi

  beat "$progress" 0 "$note"

  # 4) 可选：失速达到阈值直接退出，让上层重挂或报警
  if [[ -n "$note" && "$FAIL_ON_STALE" -gt 0 ]] && (( repeats >= FAIL_ON_STALE )); then
    echo "STALLED: no progress for ${repeats} beats; exit 5" >&2
    exit 5
  fi

  # 5) 窗口到期：watcher 是临时工具，可无限重挂
  if (( $(date +%s) - start >= MAX_WINDOW )); then
    beat "$progress" 0 "window_expired"
    echo "WINDOW: ${MAX_WINDOW}s elapsed; re-arm with the same command" >&2
    exit 3
  fi

  sleep "$INTERVAL"
done