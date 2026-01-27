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

# Copy only dependency files first (for better layer caching)
COPY apps/miroflow-agent/pyproject.toml apps/miroflow-agent/uv.lock apps/miroflow-agent/README.md /app/apps/miroflow-agent/
COPY apps/api-server/pyproject.toml apps/api-server/uv.lock apps/api-server/README.md /app/apps/api-server/
COPY libs /app/libs

# Install dependencies (this layer will be cached if dependencies don't change)
WORKDIR /app/apps/miroflow-agent
RUN uv sync --no-dev

WORKDIR /app/apps/api-server
RUN uv sync --no-dev --no-install-project

# Copy application code (after dependencies are installed)
COPY apps/miroflow-agent/src /app/apps/miroflow-agent/src
COPY apps/miroflow-agent/conf /app/apps/miroflow-agent/conf
COPY apps/api-server/*.py /app/apps/api-server/

# Create logs directory
RUN mkdir -p /app/logs

# Expose port
EXPOSE 8000

# Set working directory
WORKDIR /app/apps/api-server

# Run server (--no-sync to avoid rebuilding project)
CMD ["uv", "run", "--no-sync", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

