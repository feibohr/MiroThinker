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
COPY apps/gradio-demo/pyproject.toml apps/gradio-demo/uv.lock apps/gradio-demo/README.md /app/apps/gradio-demo/
COPY libs /app/libs

# Install miroflow-agent dependencies (this layer will be cached if dependencies don't change)
WORKDIR /app/apps/miroflow-agent
RUN uv sync --no-dev

# Install gradio-demo dependencies
WORKDIR /app/apps/gradio-demo
RUN uv sync --no-dev

# Copy application code (after dependencies are installed)
COPY apps/miroflow-agent/src /app/apps/miroflow-agent/src
COPY apps/miroflow-agent/conf /app/apps/miroflow-agent/conf
COPY apps/gradio-demo/*.py /app/apps/gradio-demo/

# Create logs directory
RUN mkdir -p /app/logs

# Expose Gradio port
EXPOSE 7860

# Set working directory
WORKDIR /app/apps/gradio-demo

# Run Gradio app
CMD ["uv", "run", "python", "main.py"]

