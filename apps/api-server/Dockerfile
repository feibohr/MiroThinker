FROM python:3.12-slim

WORKDIR /app

# Set timezone to Asia/Shanghai (UTC+8)
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager with PyPI mirror
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple uv

# Configure uv to use PyPI mirror
ENV UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# ===== 优化：先复制依赖文件，利用 Docker 缓存 =====
# 只复制依赖配置文件，这样依赖层可以被缓存
COPY apps/miroflow-agent/pyproject.toml /app/apps/miroflow-agent/
COPY apps/api-server/pyproject.toml /app/apps/api-server/
COPY libs /app/libs

# Install miroflow-agent dependencies (这层会被缓存)
WORKDIR /app/apps/miroflow-agent
RUN uv sync --no-dev || true

# Install api-server dependencies (这层会被缓存)
WORKDIR /app/apps/api-server
RUN uv sync --no-dev --no-install-project || true

# ===== 然后复制源代码 =====
# 代码变更不会导致依赖重新安装
COPY apps/miroflow-agent /app/apps/miroflow-agent
COPY apps/api-server /app/apps/api-server

# 重新同步以确保项目安装正确
WORKDIR /app/apps/miroflow-agent
RUN uv sync --no-dev

WORKDIR /app/apps/api-server
RUN uv sync --no-dev --no-install-project

# Create logs directory
RUN mkdir -p /app/logs

# Expose port
EXPOSE 8000

# Set working directory
WORKDIR /app/apps/api-server

# Run server (--no-sync to avoid rebuilding project)
CMD ["uv", "run", "--no-sync", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

