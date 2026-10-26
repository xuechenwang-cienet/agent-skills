#!/usr/bin/env bash
# 长任务启动器模板。要点：幂等、前置自检、日志固定、脱离会话、失败可见。
#
# 用法（先复制到项目里再按需修改，不要直接执行模板）：
#   NAME=train-x TERMINAL_MARKER=train_runtime CMD="python3 train.py" bash launcher.sh
#
# 环境变量：
#   NAME             必填，run id
#   CMD              必填，要执行的命令
#   TERMINAL_MARKER  必填，完成时才会出现的唯一字符串（用于 watcher/判定，不要用百分比）
#   SESSION_DIR      必填，会话目录（含 logs/）
#   PREFLIGHT        可选，前置自检命令（失败即中止）
#   EARLY_SIGNAL     可选，出现即视为"正常启动"的正则（默认取日志非空）
#   EARLY_WAIT       可选，启动后等待秒数（默认 60）
#
# 幂等只认 PIDFILE。不要用 NAME 做 pgrep：NAME 会出现在调用方 shell 的 env 前缀里
# （`NAME=x bash launcher.sh`），任何 `pgrep -f <NAME>` 都会自匹配。
set -euo pipefail

: "${NAME:?NAME required}"
: "${CMD:?CMD required}"
: "${TERMINAL_MARKER:?TERMINAL_MARKER required (must be a unique completion marker)}"
: "${SESSION_DIR:?SESSION_DIR required}"
PREFLIGHT="${PREFLIGHT:-}"
EARLY_SIGNAL="${EARLY_SIGNAL:-.}"
EARLY_WAIT="${EARLY_WAIT:-60}"

LOG="$SESSION_DIR/logs/$NAME.log"
PIDFILE="$SESSION_DIR/logs/$NAME.pid"
mkdir -p "$SESSION_DIR/logs"

# 1) 幂等：同一个 run 只允许一个实例
if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "already running: $NAME (pid $(cat "$PIDFILE"))"; exit 0
fi
# 2) 前置自检
if [[ -n "$PREFLIGHT" ]]; then
  echo "+ preflight: $PREFLIGHT"
  eval "$PREFLIGHT" || { echo "preflight failed"; exit 1; }
fi

# 3) 启动（脱离会话）
echo "=== START $NAME $(date '+%F %T %z') epoch=$(date +%s) cmd=$CMD" >> "$LOG"
setsid nohup bash -c "$CMD" >> "$LOG" 2>&1 < /dev/null &
PID=$!
echo "$PID" > "$PIDFILE"
echo "launched $NAME pid=$PID log=$LOG"

# 4) 早期信号：确认真的开始干活，而不是立刻退出
for i in $(seq 1 "$EARLY_WAIT"); do
  sleep 1
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "process exited within ${EARLY_WAIT}s; tail of log:"; tail -20 "$LOG"; exit 2
  fi
  if grep -qE "$EARLY_SIGNAL" "$LOG" 2>/dev/null; then
    echo "early signal matched after ${i}s"
    break
  fi
done

# 5) 登记到会话状态（由调用方执行，避免 launcher 依赖 python）
cat <<EOF
next:
  python3 <skill>/scripts/sessionctl.py state stage S4
  python3 <skill>/scripts/sessionctl.py ckpt "$NAME" --artifact "$LOG"   # 里程碑完成后再登记真正的产物
  TERMINAL_MARKER=$TERMINAL_MARKER bash <skill>/templates/watcher.sh
EOF