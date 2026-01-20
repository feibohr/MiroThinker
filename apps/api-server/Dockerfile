FROM python:3.12-slim

WORKDIR /app

# Use Tsinghua mirror for faster downloads in China
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager with PyPI mirror
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple uv

# Configure uv to use PyPI mirror
ENV UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# Copy project files
COPY apps/miroflow-agent /app/apps/miroflow-agent
COPY apps/api-server /app/apps/api-server
COPY libs /app/libs

# Install dependencies
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

