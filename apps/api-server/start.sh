#!/bin/bash
# MiroThinker API Server Startup Script

set -e

echo "🚀 Starting MiroThinker API Server..."
echo ""

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found!"
    echo "📝 Please copy from ../miroflow-agent/.env or create your own"
    echo "   Example: cp ../miroflow-agent/.env .env"
    exit 1
fi

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ Error: uv is not installed!"
    echo "📦 Install uv: pip install uv"
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies..."
uv sync

# Create logs directory
mkdir -p logs

# Get configuration
PORT=${PORT:-8000}
echo ""
echo "✅ Configuration:"
echo "   - Port: $PORT"
echo "   - LLM Provider: ${DEFAULT_LLM_PROVIDER:-qwen}"
echo "   - Model: ${DEFAULT_MODEL_NAME:-mirothinker}"
echo "   - Base URL: ${BASE_URL:-http://localhost:11434/v1}"
echo ""

# Start server
echo "🌐 Starting server at http://0.0.0.0:$PORT"
echo "📚 API documentation: http://0.0.0.0:$PORT/docs"
echo "❤️  Health check: http://0.0.0.0:$PORT/health"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

uv run uvicorn main:app --host 0.0.0.0 --port $PORT --reload

