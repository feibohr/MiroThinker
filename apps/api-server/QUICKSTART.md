# 🚀 快速开始指南

## 1. 安装依赖

```bash
cd apps/api-server
uv sync
```

## 2. 配置环境变量

从 miroflow-agent 复制配置：

```bash
cp ../miroflow-agent/.env .env
```

或创建新的 `.env` 文件，包含以下必需变量：

```bash
# LLM 配置
BASE_URL=http://192.168.56.66:8114/v1
API_KEY=your_api_key
DEFAULT_MODEL_NAME=mirothinker
DEFAULT_LLM_PROVIDER=qwen

# 工具 API
SERPER_API_KEY=your_serper_key
JINA_API_KEY=your_jina_key
E2B_API_KEY=your_e2b_key

# Summary LLM
SUMMARY_LLM_BASE_URL=https://your_url/v1/chat/completions
SUMMARY_LLM_MODEL_NAME=deepseek-v3
SUMMARY_LLM_API_KEY=your_key
```

## 3. 启动服务

### 方式 1：使用启动脚本（推荐）

```bash
./start.sh
```

### 方式 2：直接运行

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 方式 3：使用 Docker

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

## 4. 测试 API

### 健康检查

```bash
curl http://localhost:8000/health
```

### 流式请求

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mirothinker",
    "messages": [
      {"role": "user", "content": "2026年中国商业航天的发展态势如何？"}
    ],
    "stream": true
  }'
```

### 非流式请求

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mirothinker",
    "messages": [
      {"role": "user", "content": "What is 2+2?"}
    ],
    "stream": false
  }'
```

### 使用测试脚本

```bash
# 安装测试依赖
uv pip install httpx

# 运行测试
uv run python test_api.py
```

## 5. 访问 API 文档

服务启动后，访问以下 URL：

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## 6. 在应用中使用

### Python 示例

```python
import httpx
import json

async def chat_with_mirothinker(query: str):
    url = "http://localhost:8000/v1/chat/completions"
    
    payload = {
        "model": "mirothinker",
        "messages": [
            {"role": "user", "content": query}
        ],
        "stream": True
    }
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        async with client.stream("POST", url, json=payload) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    
                    chunk = json.loads(data)
                    content = chunk["choices"][0]["delta"].get("content", "")
                    if content:
                        print(content, end="", flush=True)
```

### JavaScript/Node.js 示例

```javascript
const response = await fetch('http://localhost:8000/v1/chat/completions', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    model: 'mirothinker',
    messages: [
      { role: 'user', content: '你好，介绍一下自己' }
    ],
    stream: true
  })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  
  const text = decoder.decode(value);
  const lines = text.split('\n');
  
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const data = line.slice(6);
      if (data === '[DONE]') break;
      
      const chunk = JSON.parse(data);
      const content = chunk.choices[0].delta.content || '';
      if (content) {
        process.stdout.write(content);
      }
    }
  }
}
```

### curl 简化命令

```bash
# 创建别名
alias mirothinker='curl -s -X POST http://localhost:8000/v1/chat/completions -H "Content-Type: application/json"'

# 使用
mirothinker -d '{"model":"mirothinker","messages":[{"role":"user","content":"你好"}],"stream":true}'
```

## 7. OpenAI SDK 兼容

MiroThinker API 完全兼容 OpenAI Python SDK：

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="dummy"  # 如果不需要认证，随便填
)

stream = client.chat.completions.create(
    model="mirothinker",
    messages=[
        {"role": "user", "content": "解释一下量子计算"}
    ],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

## 8. 生产环境部署

### 使用 systemd

创建 `/etc/systemd/system/mirothinker-api.service`：

```ini
[Unit]
Description=MiroThinker API Server
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/MiroThinker/apps/api-server
Environment="PATH=/usr/local/bin:/usr/bin"
ExecStart=/usr/local/bin/uv run uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable mirothinker-api
sudo systemctl start mirothinker-api
sudo systemctl status mirothinker-api
```

### 使用 Docker + Nginx

```bash
# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f api-server

# 重启服务
docker-compose restart api-server
```

## 9. 性能优化

### 多 worker 模式

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 使用 Gunicorn

```bash
uv pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## 10. 故障排查

### 查看日志

```bash
# 查看 API 日志
tail -f logs/*.log

# Docker 日志
docker-compose logs -f
```

### 常见问题

1. **端口被占用**
   ```bash
   # 修改端口
   PORT=8001 ./start.sh
   ```

2. **Pipeline 初始化失败**
   - 检查 `.env` 配置是否正确
   - 确保 miroflow-agent 依赖已安装

3. **LLM 连接失败**
   - 检查 `BASE_URL` 是否可访问
   - 验证 `API_KEY` 是否正确

4. **工具 API 错误**
   - 验证 SERPER/JINA/E2B API key 是否有效
   - 检查 API quota 是否充足

## 📞 获取帮助

- 📖 查看完整文档：[README.md](README.md)
- 🐛 报告问题：[GitHub Issues](https://github.com/MiroMindAI/MiroThinker/issues)
- 💬 加入社区：[Discord](https://discord.com/invite/GPqEnkzQZd)

