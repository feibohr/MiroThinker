# Docker 镜像构建指南

## 🚀 快速构建

### 方法 1: 使用 docker compose（推荐）

```bash
# 在项目根目录执行
cd /Users/feibohr/Documents/workspace/git/python/MiroThinker

# 重新构建 api-server 镜像
docker compose build api-server

# 或者构建并启动
docker compose up -d --build api-server
```

### 方法 2: 只构建不启动

```bash
# 只构建镜像
docker compose build api-server

# 之后再启动
docker compose up -d api-server
```

### 方法 3: 清理后重新构建

```bash
# 停止容器
docker compose down

# 清理旧镜像（可选）
docker rmi mirothinker-api-server

# 重新构建
docker compose up -d --build api-server
```

## 🧹 清理 Docker 空间（磁盘不足时）

### 清理未使用的资源
```bash
# 清理未使用的容器、网络、镜像
docker system prune -f

# 清理所有未使用的镜像（包括悬空镜像）
docker system prune -a -f

# 清理构建缓存
docker builder prune -f
```

### 只清理 api-server 相关
```bash
# 停止并删除容器
docker compose stop api-server
docker compose rm -f api-server

# 删除镜像
docker rmi mirothinker-api-server

# 重新构建
docker compose up -d --build api-server
```

## 📦 构建参数

### 无缓存构建（完全重新构建）
```bash
docker compose build --no-cache api-server
```

### 并行构建（构建多个服务）
```bash
# 构建所有服务
docker compose build

# 并行构建多个服务
docker compose build api-server gradio-demo
```

## 🔍 查看构建进度

### 实时查看构建日志
```bash
# 构建时显示详细输出
docker compose build --progress=plain api-server
```

### 查看镜像信息
```bash
# 查看所有镜像
docker images | grep mirothinker

# 查看镜像详情
docker inspect mirothinker-api-server
```

## ⚠️ 常见问题

### 问题 1: "no space left on device"

**原因**: Docker 磁盘空间不足

**解决方法**:
```bash
# 1. 清理 Docker 系统
docker system prune -a --volumes -f

# 2. 检查磁盘使用
docker system df

# 3. 增加 Docker 磁盘配额（Docker Desktop）
# Settings -> Resources -> Advanced -> Disk image size
```

### 问题 2: 构建失败 "userspace copy failed"

**原因**: 复制 .venv 目录导致镜像过大

**解决方法**: 
```bash
# 1. 确保 .dockerignore 存在
cat apps/api-server/.dockerignore

# 应该包含:
# .venv
# __pycache__
# *.pyc

# 2. 删除本地 .venv（如果已存在）
rm -rf apps/api-server/.venv

# 3. 重新构建
docker compose build --no-cache api-server
```

### 问题 3: 端口占用

**原因**: 8000 端口被占用

**解决方法**:
```bash
# 查看端口占用
lsof -i :8000

# 停止占用进程
kill -9 <PID>

# 或修改端口
# 编辑 docker-compose.yml:
# ports:
#   - "8001:8000"  # 改为 8001
```

### 问题 4: 构建缓存导致代码未更新

**原因**: Docker 使用了旧的构建缓存

**解决方法**:
```bash
# 无缓存重新构建
docker compose build --no-cache api-server

# 或清理构建缓存
docker builder prune -a -f
```

## 🎯 完整重建流程（推荐）

```bash
# 1. 进入项目目录
cd /Users/feibohr/Documents/workspace/git/python/MiroThinker

# 2. 停止并删除容器
docker compose down

# 3. 清理旧镜像（可选）
docker rmi mirothinker-api-server 2>/dev/null || true

# 4. 重新构建（无缓存）
docker compose build --no-cache api-server

# 5. 启动服务
docker compose up -d api-server

# 6. 查看日志
docker compose logs -f api-server

# 7. 测试服务
curl http://localhost:8000/
```

## 📊 验证构建结果

```bash
# 1. 检查容器状态
docker ps | grep api-server

# 2. 查看容器日志
docker logs mirothinker-api --tail 50

# 3. 测试 V1 API
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"mirothinker","messages":[{"role":"user","content":"hello"}],"stream":true}' \
  | head -3

# 4. 测试 V2 API
curl -X POST http://localhost:8000/v2/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"mirothinker","messages":[{"role":"user","content":"hello"}],"stream":true}' \
  | head -3
```

## 🔧 开发模式（不使用 Docker）

如果不想使用 Docker，可以直接本地运行：

```bash
# 1. 进入 api-server 目录
cd apps/api-server

# 2. 安装依赖
uv sync

# 3. 启动服务
uv run uvicorn main:app --reload --port 8000

# 4. 访问
curl http://localhost:8000/
```

## 📝 构建优化建议

### 1. 使用 .dockerignore
确保 `apps/api-server/.dockerignore` 包含：
```
.venv
__pycache__
*.pyc
*.pyo
*.pyd
.Python
*.egg-info
dist
build
*.log
.DS_Store
.git
test_*.py
logs/
```

### 2. 多阶段构建（未来优化）
```dockerfile
# 构建阶段
FROM python:3.12-slim AS builder
# ... 安装依赖

# 运行阶段
FROM python:3.12-slim
COPY --from=builder /app /app
```

### 3. 固定依赖版本
在 `pyproject.toml` 中固定版本号，避免每次构建都拉取最新版本

## 🚨 紧急修复（热更新）

如果只是修改了 Python 代码，不想重新构建：

```bash
# 方法 1: 直接复制文件到容器（临时方案）
docker cp apps/api-server/routers/chat.py mirothinker-api:/app/apps/api-server/routers/chat.py
docker restart mirothinker-api

# 方法 2: 使用卷挂载（开发模式）
# 编辑 docker-compose.yml 添加：
# volumes:
#   - ./apps/api-server:/app/apps/api-server
```

## 📱 查看构建帮助

```bash
# docker compose build 帮助
docker compose build --help

# 查看 Docker 版本
docker --version
docker compose version
```

---

**提示**: 如果遇到任何问题，可以查看详细日志：
```bash
docker compose logs api-server --tail 100 -f
```

