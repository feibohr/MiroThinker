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
COPY apps/gradio-demo /app/apps/gradio-demo
COPY libs /app/libs

# Install miroflow-agent dependencies
WORKDIR /app/apps/miroflow-agent
RUN uv sync --no-dev

# Install gradio-demo dependencies
WORKDIR /app/apps/gradio-demo
RUN uv sync --no-dev

# Create logs directory
RUN mkdir -p /app/logs

# Expose Gradio port
EXPOSE 7860

# Set working directory
WORKDIR /app/apps/gradio-demo

# Run Gradio app
CMD ["uv", "run", "python", "main.py"]

