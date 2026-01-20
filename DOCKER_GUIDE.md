# MiroThinker Docker 快速启动指南

## 🚀 快速开始

### 1. 准备环境变量

首次使用时，脚本会自动创建 `.env` 文件：

```bash
cd /Users/feibohr/Documents/workspace/git/python/MiroThinker

# 运行启动脚本（会提示编辑 .env）
./docker-launch.sh up
```

编辑 `.env` 文件，配置你的 API 密钥：

```bash
# LLM 配置
BASE_URL=http://192.168.56.66:8114/v1
API_KEY=your-api-key-here
DEFAULT_MODEL_NAME=mirothinker

# 工具 API Keys
SERPER_API_KEY=your-serper-key
JINA_API_KEY=your-jina-key
E2B_API_KEY=your-e2b-key
```

### 2. 启动所有服务

```bash
# 启动 API Server + Gradio Demo
./docker-launch.sh up

# 或者带 Nginx 反向代理
./docker-launch.sh up --with-nginx
```

### 3. 访问服务

启动后会显示：

```
✓ API Server:    http://localhost:8000
  - Health:       http://localhost:8000/health
  - API Docs:     http://localhost:8000/docs

✓ Gradio Demo:   http://localhost:7860

✓ Nginx:         http://localhost (if enabled)
```

## 📋 完整命令列表

### 基础命令

```bash
# 启动所有服务
./docker-launch.sh up

# 停止所有服务
./docker-launch.sh down

# 重启所有服务
./docker-launch.sh restart

# 查看日志（实时）
./docker-launch.sh logs

# 查看服务状态
./docker-launch.sh ps

# 构建镜像
./docker-launch.sh build

# 清理所有容器、卷和镜像
./docker-launch.sh clean
```

### 单服务操作

```bash
# 只启动 API Server
./docker-launch.sh up api-server

# 只启动 Gradio Demo
./docker-launch.sh up gradio-demo

# 重启 API Server
./docker-launch.sh restart api-server

# 查看 Gradio 日志
./docker-launch.sh logs gradio-demo
```

### 带 Nginx

```bash
# 启动所有服务 + Nginx
./docker-launch.sh up --with-nginx

# 重启 Nginx
./docker-launch.sh restart nginx
```

## 🏗️ 服务架构

```
┌─────────────────────────────────────────────┐
│           Nginx (Optional)                  │
│         http://localhost:80                 │
│                                             │
│  /v1/*    → API Server                      │
│  /         → Gradio Demo                    │
└─────────────────────────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        │                           │
        ▼                           ▼
┌───────────────┐           ┌───────────────┐
│  API Server   │           │ Gradio Demo   │
│  Port: 8000   │           │  Port: 7860   │
│               │           │               │
│ - OpenAI API  │           │ - Web UI      │
│ - Streaming   │           │ - Real-time   │
│ - Multi-turn  │           │               │
└───────────────┘           └───────────────┘
```

## 🔧 配置选项

### 端口配置（.env）

```bash
API_PORT=8000              # API Server 端口
GRADIO_PORT=7860           # Gradio Demo 端口
NGINX_HTTP_PORT=80         # Nginx HTTP 端口
NGINX_HTTPS_PORT=443       # Nginx HTTPS 端口
```

### 并发配置

```bash
PIPELINE_POOL_SIZE=5           # Pipeline 池大小
MAX_CONCURRENT_REQUESTS=10     # 最大并发请求数
```

### 上下文管理

```bash
CONTEXT_COMPRESSION_ENABLED=true    # 启用智能压缩
MAX_HISTORY_TOKENS=30000            # 压缩阈值
SUMMARY_LLM_MODEL_NAME=gpt-4o-mini  # 总结模型
```

## 📊 监控和调试

### 查看实时日志

```bash
# 所有服务
./docker-launch.sh logs

# 指定服务
./docker-launch.sh logs api-server
./docker-launch.sh logs gradio-demo
```

### 进入容器

```bash
# 进入 API Server 容器
docker exec -it mirothinker-api bash

# 进入 Gradio 容器
docker exec -it mirothinker-gradio bash
```

### 健康检查

```bash
# API Server 健康检查
curl http://localhost:8000/health

# Gradio 健康检查
curl http://localhost:7860
```

### 查看日志文件

日志会持久化到 Docker 卷中：

```bash
# 查看日志卷
docker volume ls | grep mirothinker

# 挂载日志卷查看
docker run --rm -v mirothinker-api-logs:/logs alpine ls -la /logs
```

## 🐛 故障排查

### 服务无法启动

```bash
# 1. 检查 Docker 是否运行
docker info

# 2. 检查端口是否被占用
lsof -i :8000
lsof -i :7860

# 3. 查看详细错误日志
./docker-launch.sh logs

# 4. 重新构建镜像
./docker-launch.sh build
./docker-launch.sh up
```

### 容器频繁重启

```bash
# 查看容器状态
docker compose ps

# 查看容器日志
docker logs mirothinker-api
docker logs mirothinker-gradio

# 检查环境变量配置
docker exec -it mirothinker-api env | grep API_KEY
```

### API 调用失败

```bash
# 1. 检查 API Server 健康状态
curl http://localhost:8000/health

# 2. 测试 API 调用
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mirothinker",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": false
  }'

# 3. 检查日志
./docker-launch.sh logs api-server
```

### 清理并重新开始

```bash
# 完全清理
./docker-launch.sh clean

# 重新构建并启动
./docker-launch.sh build
./docker-launch.sh up
```

## 🔒 生产环境部署

### 启用 HTTPS

1. 准备 SSL 证书：

```bash
mkdir -p nginx/ssl
# 将证书文件放入 nginx/ssl/
# - cert.pem
# - key.pem
```

2. 编辑 `nginx/nginx.conf`，取消注释 HTTPS server 部分

3. 启动服务：

```bash
./docker-launch.sh up --with-nginx
```

### 环境隔离

```bash
# 开发环境
cp .env.docker.example .env.dev
# 编辑 .env.dev

# 生产环境
cp .env.docker.example .env.prod
# 编辑 .env.prod

# 使用指定环境
docker compose --env-file .env.prod up -d
```

### 资源限制

编辑 `docker-compose.yml` 添加资源限制：

```yaml
services:
  api-server:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
```

## 📈 性能优化

### 并发调优

根据你的硬件调整：

```bash
# 8核16G 服务器
PIPELINE_POOL_SIZE=8
MAX_CONCURRENT_REQUESTS=16

# 4核8G 服务器
PIPELINE_POOL_SIZE=4
MAX_CONCURRENT_REQUESTS=8
```

### 日志管理

限制日志大小：

```yaml
services:
  api-server:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## 🌐 外部访问

### 局域网访问

修改 `.env` 中的端口即可：

```bash
API_PORT=8000
GRADIO_PORT=7860
```

其他设备访问：`http://你的IP:8000`

### 反向代理（推荐）

使用 Nginx 统一入口：

```bash
./docker-launch.sh up --with-nginx
```

访问：
- API: `http://你的IP/v1/chat/completions`
- Demo: `http://你的IP/`

## 💾 数据持久化

### 日志卷

日志自动持久化到 Docker 卷：

```bash
# 查看卷
docker volume ls | grep mirothinker

# 备份日志
docker run --rm -v mirothinker-api-logs:/logs -v $(pwd):/backup \
  alpine tar czf /backup/api-logs-$(date +%Y%m%d).tar.gz -C /logs .
```

### 挂载本地目录

修改 `docker-compose.yml`：

```yaml
volumes:
  - ./data:/app/data  # 挂载本地 data 目录
```

## 🔄 更新服务

```bash
# 1. 拉取最新代码
git pull

# 2. 重新构建镜像
./docker-launch.sh build

# 3. 重启服务
./docker-launch.sh restart
```

## 📚 相关文档

- [API 文档](./apps/api-server/README.md)
- [快速开始](./apps/api-server/QUICKSTART.md)
- [上下文管理](./apps/api-server/CONTEXT_MANAGEMENT.md)
- [并发优化](./apps/api-server/CONCURRENCY.md)

