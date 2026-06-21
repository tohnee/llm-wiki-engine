#!/usr/bin/env bash
# 停止 LLM-Wiki 全部后端服务
cd "$(dirname "$0")"

for pidfile in logs/*.pid; do
  [ -f "$pidfile" ] || continue
  name=$(basename "$pidfile" .pid)
  pid=$(cat "$pidfile")
  if kill -0 "$pid" 2>/dev/null; then
    echo "[$name] stopping (pid $pid)..."
    kill "$pid"
  fi
  rm -f "$pidfile"
done
echo "All services stopped."
