#!/bin/bash

# MiroThinker 一键启动脚本（本地模式）

set -e

echo "============================================"
echo "   🚀 MiroThinker 启动器"
echo "============================================"
echo ""

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# 检查环境变量配置
if [ ! -f "$PROJECT_ROOT/apps/miroflow-agent/.env" ]; then
    echo "❌ 错误：找不到配置文件 apps/miroflow-agent/.env"
    echo ""
    echo "请先配置环境变量："
    echo "  cp apps/miroflow-agent/env.txt apps/miroflow-agent/.env"
    echo "  # 然后编辑 .env 文件"
    exit 1
fi

# 加载环境变量
source "$PROJECT_ROOT/apps/miroflow-agent/.env" 2>/dev/null || true

# 如果没有 BASE_URL，从 .env 读取
if [ -z "$BASE_URL" ]; then
    if [ -f "$PROJECT_ROOT/.env" ]; then
        export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
    fi
fi

# 显示菜单
echo "请选择要启动的服务："
echo ""
echo "1) API Server (OpenAI 兼容 API)"
echo "2) Gradio Demo (Web UI)"
echo "3) 同时启动两个服务"
echo "4) 退出"
echo ""
read -p "请输入选择 [1-4]: " choice

case $choice in
    1)
        echo ""
        echo "🚀 启动 API Server..."
        echo "访问地址: http://localhost:8000"
        echo "API 文档: http://localhost:8000/docs"
        echo ""
        cd "$PROJECT_ROOT/apps/api-server"
        ./start.sh
        ;;
    2)
        echo ""
        echo "🚀 启动 Gradio Demo..."
        echo "访问地址: http://localhost:7860"
        echo ""
        cd "$PROJECT_ROOT/apps/gradio-demo"
        
        # 设置环境变量
        export BASE_URL="${BASE_URL:-http://192.168.56.66:8114/v1}"
        export API_KEY="${API_KEY}"
        export DEFAULT_MODEL_NAME="${DEFAULT_MODEL_NAME:-mirothinker}"
        export DEFAULT_LLM_PROVIDER="${DEFAULT_LLM_PROVIDER:-qwen}"
        
        uv run python main.py
        ;;
    3)
        echo ""
        echo "🚀 同时启动两个服务..."
        echo ""
        echo "API Server: http://localhost:8000"
        echo "Gradio Demo: http://localhost:7860"
        echo ""
        echo "按 Ctrl+C 停止所有服务"
        echo ""
        
        # 启动 API Server（后台）
        cd "$PROJECT_ROOT/apps/api-server"
        nohup ./start.sh > /tmp/mirothinker-api.log 2>&1 &
        API_PID=$!
        echo "✓ API Server 已启动 (PID: $API_PID)"
        
        # 等待 API Server 启动
        sleep 5
        
        # 启动 Gradio Demo（前台）
        cd "$PROJECT_ROOT/apps/gradio-demo"
        export BASE_URL="${BASE_URL:-http://192.168.56.66:8114/v1}"
        export API_KEY="${API_KEY}"
        export DEFAULT_MODEL_NAME="${DEFAULT_MODEL_NAME:-mirothinker}"
        
        # 捕获退出信号，停止 API Server
        trap "echo ''; echo '停止服务...'; kill $API_PID 2>/dev/null; exit" INT TERM
        
        uv run python main.py
        ;;
    4)
        echo "再见！"
        exit 0
        ;;
    *)
        echo "❌ 无效选择"
        exit 1
        ;;
esac

