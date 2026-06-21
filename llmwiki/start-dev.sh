#!/usr/bin/env bash
# 启动 LLM-Wiki 全部后端服务(evidence/query/admin/ingest/generation/compile-worker)
# 用法: ./start-dev.sh  (在 llmwiki/ 目录下执行)
# 日志: 各服务输出写到 logs/<service>.log
# 停止: ./stop-dev.sh 或 kill $(cat logs/*.pid)

set -euo pipefail

cd "$(dirname "$0")"
mkdir -p logs

# 加载 .env
if [ -f .env ]; then
  set -a; source .env; set +a
fi

# EMBED_MOCK 默认关闭(使用真实 embedding 服务)
export EMBED_MOCK="${EMBED_MOCK:-0}"
export PYTHONUNBUFFERED=1

# 服务定义: name | module | port
SERVICES=(
  "evidence|app.evidence.service:app|8001"
  "query|app.query.gateway:app|8000"
  "admin|app.admin.service:app|8002"
  "ingest|app.ingest.service:app|8003"
  "generation|app.generation.service:app|8004"
)

start_one() {
  local name="$1" module="$2" port="$3"
  local pidfile="logs/${name}.pid"
  local logfile="logs/${name}.log"

  if [ -f "$pidfile" ] && kill -0 "$(cat $pidfile)" 2>/dev/null; then
    echo "[$name] already running (pid $(cat $pidfile))"
    return 0
  fi

  echo "[$name] starting on port $port..."
  nohup uvicorn "$module" --host 0.0.0.0 --port "$port" > "$logfile" 2>&1 &
  echo $! > "$pidfile"
  sleep 1
  if kill -0 "$(cat $pidfile)" 2>/dev/null; then
    echo "[$name] started (pid $(cat $pidfile), log: $logfile)"
  else
    echo "[$name] FAILED to start — check $logfile"
    return 1
  fi
}

# 启动 compile-worker
start_worker() {
  local pidfile="logs/compile-worker.pid"
  local logfile="logs/compile-worker.log"

  if [ -f "$pidfile" ] && kill -0 "$(cat $pidfile)" 2>/dev/null; then
    echo "[compile-worker] already running (pid $(cat $pidfile))"
    return 0
  fi

  echo "[compile-worker] starting..."
  nohup python3 -m app.compile.run_worker > "$logfile" 2>&1 &
  echo $! > "$pidfile"
  sleep 1
  if kill -0 "$(cat $pidfile)" 2>/dev/null; then
    echo "[compile-worker] started (pid $(cat $pidfile), log: $logfile)"
  else
    echo "[compile-worker] FAILED — check $logfile"
    return 1
  fi
}

echo "=== LLM-Wiki 后端服务启动 ==="
for svc in "${SERVICES[@]}"; do
  IFS='|' read -r name module port <<< "$svc"
  start_one "$name" "$module" "$port"
done
start_worker

echo ""
echo "=== 服务端口 ==="
echo "  evidence:    http://localhost:8001  (检索/导航/图谱)"
echo "  query:       http://localhost:8000  (问答网关)"
echo "  admin:       http://localhost:8002  (登录/租户管理)"
echo "  ingest:      http://localhost:8003  (文档入库)"
echo "  generation:  http://localhost:8004  (报告生成)"
echo "  frontend:    http://localhost:5173  (Vite 开发服务器)"
echo ""
echo "停止: ./stop-dev.sh"
