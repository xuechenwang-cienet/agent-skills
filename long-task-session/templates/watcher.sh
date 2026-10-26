#!/usr/bin/env bash
# 长任务监视器模板。要点：心跳写纯文本文件、终态绑真实标记、窗口可重挂、能发现死亡。
#
# 用法：
#   RUN_ID=train-x LOG=logs/train-x.log TERMINAL_MARKER=train_runtime \
#   PROGRESS_REGEX='\| [0-9]+/[0-9]+ \[' SESSION_DIR=./sessions/2026-01-01-demo \
#   bash watcher.sh
#
# 退出码：0=见到终态标记 2=进程消失但无终态 3=窗口到期（可重挂） 4=用法错误
set -uo pipefail

: "${SESSION_DIR:?SESSION_DIR required}"
: "${LOG:?LOG required}"
: "${TERMINAL_MARKER:?TERMINAL_MARKER required}"
RUN_ID="${RUN_ID:-$(basename "$LOG" .log)}"
INTERVAL="${INTERVAL:-60}"        # 心跳间隔（秒）
MAX_WINDOW="${MAX_WINDOW:-7200}"  # 单次窗口（秒），默认 2 小时
PROGRESS_REGEX="${PROGRESS_REGEX:-}"
PID="${PID:-}"

HB="$SESSION_DIR/logs/heartbeat.log"
mkdir -p "$SESSION_DIR/logs"
[[ -f "$LOG" ]] || { echo "log not found: $LOG" >&2; exit 4; }

stamp() { echo "$(date +%s) $(date '+%F %T %z')"; }

beat() { # $1=progress $2=marker(0/1) $3=note
  echo "$(stamp) run=$RUN_ID pid=${PID:--} progress=${1:--} marker=$2 ${3:-}" >> "$HB"
}

echo "$(stamp) watcher_start run=$RUN_ID interval=${INTERVAL}s window=${MAX_WINDOW}s" >> "$HB"
start=$(date +%s)

while :; do
  # 1) 终态：只认唯一字符串，不要用百分比（别的阶段也会打印同名百分比）
  if grep -q "$TERMINAL_MARKER" "$LOG" 2>/dev/null; then
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

  # 3) 死亡检测：给了 PID 才判
  if [[ -n "$PID" ]] && ! kill -0 "$PID" 2>/dev/null; then
    beat "$progress" 0 "process_gone"
    echo "DEAD: pid $PID gone without terminal marker" >&2
    exit 2
  fi

  beat "$progress" 0 ""

  # 4) 窗口到期：watcher 是临时工具，可无限重挂
  if (( $(date +%s) - start >= MAX_WINDOW )); then
    beat "$progress" 0 "window_expired"
    echo "WINDOW: ${MAX_WINDOW}s elapsed; re-arm with the same command" >&2
    exit 3
  fi

  sleep "$INTERVAL"
done