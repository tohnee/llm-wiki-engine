#!/usr/bin/env bash
# =============================================================================
# LLM-Wiki Engine — 一键启动脚本(Unix / macOS / Linux)
# -----------------------------------------------------------------------------
# 功能:
#   1. 检查必备依赖(docker / python3 / node / npm)
#   2. 缺失则提示安装命令(不强制装,避免破坏用户环境)
#   3. 检查 .env 是否存在,缺则从 .env.template 复制并提示填值
#   4. 三种启动模式:
#        ./start.sh docker  → docker-compose 全栈(默认)
#        ./start.sh mock    → 纯前端 + Mock 后端(零外部依赖)
#        ./start.sh dev     → 本地 Python + npm dev(需手动起 PG/Redis)
#
# 用法:
#   chmod +x start.sh
#   ./start.sh                # 等价于 ./start.sh docker
#   ./start.sh mock           # 启动 Mock 模式(推荐首次体验)
# =============================================================================

set -e

# ---- 颜色 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ---- 路径 ----
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# ---- 日志辅助 ----
log_info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ---- 依赖检查 ----
check_cmd() {
    local cmd="$1"
    local hint="$2"
    if command -v "$cmd" >/dev/null 2>&1; then
        local ver
        ver=$("$cmd" --version 2>&1 | head -1 || echo "unknown")
        log_ok "$cmd 已安装 ($ver)"
        return 0
    else
        log_error "$cmd 未安装。建议: $hint"
        return 1
    fi
}

ensure_env_file() {
    if [ ! -f ".env" ]; then
        log_warn ".env 文件不存在"
        if [ -f ".env.template" ]; then
            cp .env.template .env
            log_ok "已从 .env.template 复制创建 .env"
            log_warn "请编辑 .env 填入真实 API 凭证后重新运行:"
            log_warn "  vim .env  (或用你喜欢的编辑器)"
            log_warn "关键字段: OPENAI_API_KEY / OPENAI_BASE_URL / EMBED_API_KEY / JWT_SECRET"
            exit 1
        else
            log_error ".env.template 也不存在,无法继续。请从仓库拉取最新模板。"
            exit 1
        fi
    fi
    log_ok ".env 已就绪"
}

# ---- 模式分发 ----
MODE="${1:-docker}"

print_banner() {
    echo ""
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║         LLM-Wiki Engine — 一键启动 (Unix)                 ║"
    echo "║         Mode: $MODE"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo ""
}

print_banner

case "$MODE" in
    # =========== 模式 1: docker-compose 全栈 ===========
    docker)
        log_info "[1/4] 检查 docker 依赖..."
        check_cmd docker "https://docs.docker.com/get-docker/" || exit 1
        if ! docker compose version >/dev/null 2>&1; then
            log_error "docker compose 子命令不可用(需要 Docker Desktop 4.0+ 或独立 docker-compose-plugin)"
            exit 1
        fi
        log_ok "docker compose 可用"

        log_info "[2/4] 检查 .env..."
        ensure_env_file

        log_info "[3/4] 启动 docker-compose 全栈..."
        cd llmwiki
        docker compose -f deploy/docker-compose.yml up -d --build

        log_info "[4/4] 等待服务就绪..."
        sleep 5
        for port in 8000 8001 8002 8003 8004; do
            if curl -fsS "http://localhost:$port/health" >/dev/null 2>&1; then
                log_ok "服务 :$port 健康"
            else
                log_warn "服务 :$port 暂不可达(可能仍在启动)"
            fi
        done

        echo ""
        log_ok "全栈启动完成。查日志: docker compose -f llmwiki/deploy/docker-compose.yml logs -f"
        log_ok "前端开发: cd llmwiki/frontend && npm run dev"
        ;;

    # =========== 模式 2: Mock 后端(零外部依赖)===========
    mock)
        log_info "[1/3] 检查 node 依赖..."
        check_cmd node "https://nodejs.org/(建议 ≥ 18)" || exit 1
        check_cmd npm  "随 node 自带" || exit 1

        log_info "[2/3] 启动 Mock 后端(端口 8000)..."
        if [ -d "mock-backend" ]; then
            cd mock-backend
            if [ ! -d "node_modules" ]; then
                log_info "首次启动,安装依赖..."
                npm install --no-audit --no-fund
            fi
            log_ok "启动 Mock 后端 → http://localhost:8000"
            log_ok "可用接口: GET /api/health  POST /api/query/ask  ..."
            log_ok "停止: Ctrl+C"
            node server.js
        else
            log_error "mock-backend/ 目录不存在,无法启动 mock 模式"
            exit 1
        fi
        ;;

    # =========== 模式 3: 本地 Python + npm dev ===========
    dev)
        log_info "[1/5] 检查 python3/pip/node 依赖..."
        check_cmd python3 "https://www.python.org/downloads/(≥ 3.11)" || exit 1
        check_cmd pip3 "随 python 自带" || exit 1
        check_cmd node "https://nodejs.org/(≥ 18)" || exit 1

        log_info "[2/5] 检查 .env..."
        ensure_env_file

        log_info "[3/5] 安装 Python 依赖..."
        cd llmwiki
        pip3 install -q -r requirements.txt
        log_ok "Python 依赖就绪"

        log_info "[4/5] 安装前端依赖..."
        cd frontend
        if [ ! -d "node_modules" ]; then
            npm install --no-audit --no-fund
        fi
        log_ok "前端依赖就绪"

        log_info "[5/5] 提示手动起服务..."
        echo ""
        log_warn "请在不同终端分别启动以下服务(假设你已自行起好 PG + Redis):"
        echo "  终端 1: cd llmwiki && uvicorn app.evidence.service:app --port 8001"
        echo "  终端 2: cd llmwiki && uvicorn app.query.gateway:app    --port 8000"
        echo "  终端 3: cd llmwiki && uvicorn app.admin.service:app    --port 8002"
        echo "  终端 4: cd llmwiki && uvicorn app.ingest.service:app   --port 8003"
        echo "  终端 5: cd llmwiki && uvicorn app.generation.service:app --port 8004"
        echo "  终端 6: cd llmwiki && python -m app.compile.run_worker"
        echo "  终端 7: cd llmwiki/frontend && npm run dev"
        ;;

    help|-h|--help)
        cat <<EOF
用法: ./start.sh [MODE]

MODE:
  docker  (默认)  用 docker-compose 起后端全栈 + 前端 dev
  mock           启动 Mock 后端(零外部依赖,适合 demo)
  dev            本地 Python + npm,需自备 PG/Redis
  help           显示本帮助

示例:
  ./start.sh                 # docker 全栈
  ./start.sh mock            # 仅 mock 后端,体验 UI
  ./start.sh dev             # 本地开发模式
EOF
        ;;

    *)
        log_error "未知模式: $MODE"
        log_info "使用 ./start.sh help 查看用法"
        exit 1
        ;;
esac
