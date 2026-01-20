# 🚀 并发性能优化指南

## 问题诊断

### Gradio Demo 的并发瓶颈

1. **全局共享 Pipeline 组件** ⚠️
   ```python
   # 所有请求共享同一个 tool_manager
   _preload_cache["main_agent_tool_manager"]  # 全局单例
   ```
   **影响**: 工具调用可能串行化，导致请求排队

2. **LLM API 限制** ⚠️
   - 自部署模型服务器通常有并发限制
   - GPU 资源竞争
   - 如果服务器单线程处理，则完全串行

3. **E2B Sandbox 创建** ⚠️
   - 代码执行沙箱创建需要时间（2-5秒）
   - API 有速率限制
   - 并发创建可能受限

## API Server 的并发优化

### 核心改进

#### 1. Pipeline 连接池

```python
# services/concurrency_manager.py
class PipelinePool:
    """
    维护多个独立的 Pipeline 实例
    每个实例有独立的 tool_manager，避免资源竞争
    """
    def __init__(self, cfg, pool_size: int = 5):
        # 创建 5 个独立的 Pipeline 实例
        for i in range(pool_size):
            self.pool.append({
                "main_agent_tool_manager": ...,  # 独立实例
                "sub_agent_tool_managers": ...,
                "output_formatter": ...,
            })
```

**优势:**
- ✅ 每个请求获取独立的 Pipeline 实例
- ✅ 避免共享状态导致的竞争
- ✅ 支持真正的并发执行

#### 2. 并发限流

```python
class ConcurrencyLimiter:
    """
    全局并发限制，防止系统过载
    """
    def __init__(self, max_concurrent: int = 10):
        self._semaphore = asyncio.Semaphore(max_concurrent)
```

**优势:**
- ✅ 限制同时处理的请求数
- ✅ 超出限制的请求排队等待
- ✅ 防止资源耗尽

#### 3. 请求生命周期管理

```python
async def stream_research(self, task_id: str, query: str):
    # 获取 Pipeline 实例
    instance = await self.pipeline_manager.acquire_pipeline()
    
    try:
        # 使用独立的实例执行任务
        await execute_task_pipeline(
            main_agent_tool_manager=instance["main_agent_tool_manager"],
            ...
        )
    finally:
        # 释放回连接池
        self.pipeline_manager.release_pipeline(instance)
```

## 配置调优

### 环境变量

```bash
# .env

# Pipeline 连接池大小（每个实例独立处理一个请求）
PIPELINE_POOL_SIZE=5

# 最大并发请求数（超出则排队）
MAX_CONCURRENT_REQUESTS=10
```

### 推荐配置

| 场景 | PIPELINE_POOL_SIZE | MAX_CONCURRENT_REQUESTS | 说明 |
|------|-------------------|------------------------|------|
| **轻量使用** | 3 | 5 | 个人开发、测试 |
| **中等流量** | 5 | 10 | 小团队使用 |
| **高流量** | 10 | 20 | 生产环境 |
| **资源受限** | 2 | 3 | 低配服务器 |

### 调优建议

1. **PIPELINE_POOL_SIZE**:
   - 每个实例需要一定内存（~500MB-1GB）
   - 不要超过 CPU 核心数的 2 倍
   - 考虑 E2B sandbox 创建限制

2. **MAX_CONCURRENT_REQUESTS**:
   - 应该 >= PIPELINE_POOL_SIZE
   - 考虑 LLM API 的并发限制
   - 考虑 Serper/Jina API 的速率限制

## 性能测试

### 运行并发测试

```bash
cd /Users/feibohr/Documents/workspace/git/python/MiroThinker/apps/api-server

# 安装测试依赖
uv pip install httpx

# 运行并发基准测试
uv run python benchmark_concurrency.py
```

### 预期结果

**优化前（Gradio Demo）:**
```
Sequential (3 requests): 120s total
Concurrent (3 requests): 110s total
Speedup: 1.09x ❌ (几乎没有加速)
```

**优化后（API Server）:**
```
Sequential (3 requests): 120s total
Concurrent (3 requests): 45s total
Speedup: 2.67x ✅ (接近线性加速)
```

## 瓶颈分析

即使优化后，仍可能遇到以下瓶颈：

### 1. LLM API 限制 🔴

**问题:**
```bash
# 你的 LLM 服务器
BASE_URL=http://192.168.56.66:8114/v1

# 可能的限制：
- 单线程推理
- GPU 资源竞争
- vLLM/SGLang 的并发配置
```

**解决:**
```bash
# vLLM 启动时增加并发
python -m vllm.entrypoints.openai.api_server \
    --model mirothinker \
    --max-num-seqs 10  # 增加并发序列数
    
# SGLang 启动时增加并发
python -m sglang.launch_server \
    --model-path mirothinker \
    --dp 2  # 数据并行，增加吞吐
```

### 2. 工具 API 限流 🔴

**Serper API:**
- 免费版: 100 requests/day
- 付费版: 1000-5000 requests/hour

**Jina API:**
- 速率限制可能导致 429 错误

**E2B:**
- Sandbox 创建有并发限制
- 每个账户有最大 sandbox 数量

**解决:**
- 升级 API 套餐
- 使用多个 API key 轮换
- 实现请求缓存

### 3. 网络延迟 🔴

**问题:**
- 工具 API 调用串行
- 每次搜索 + 爬取 = 5-10 秒

**解决:**
```python
# 并行工具调用（需要框架支持）
results = await asyncio.gather(
    search_api.call(),
    scrape_api.call(),
    code_api.call(),
)
```

## 监控和诊断

### 1. 健康检查

```bash
curl http://localhost:8000/health
```

返回：
```json
{
  "status": "healthy",
  "active_requests": 3,
  "pool_size": 5
}
```

### 2. 实时监控

```python
# 添加 Prometheus metrics
from prometheus_client import Counter, Gauge

request_counter = Counter('mirothinker_requests_total', 'Total requests')
active_requests = Gauge('mirothinker_active_requests', 'Active requests')
pipeline_pool_usage = Gauge('mirothinker_pool_usage', 'Pipeline pool usage')
```

### 3. 日志分析

```bash
# 查看并发日志
grep "Concurrency:" logs/api-server.log

# 输出示例：
# Concurrency: 3/10 active requests
# Acquired pipeline instance 2 for task xxx
# Released pipeline instance 2 for task xxx
```

## 最佳实践

### 1. 逐步增加并发

```bash
# 从小开始
PIPELINE_POOL_SIZE=2
MAX_CONCURRENT_REQUESTS=3

# 监控性能和错误率
# 如果稳定，逐步增加
```

### 2. 使用负载均衡

```bash
# docker-compose.yml
services:
  api-server-1:
    ...
  api-server-2:
    ...
  
  nginx:
    # 负载均衡到多个实例
```

### 3. 实现请求缓存

```python
# 缓存搜索结果
from functools import lru_cache

@lru_cache(maxsize=1000)
def cached_search(query: str):
    return serper_api.search(query)
```

## 故障排查

### 问题：请求仍然很慢

**检查:**
1. 查看 active_requests 是否达到 pool_size
2. 检查 LLM API 响应时间
3. 查看工具 API 是否返回 429 错误
4. 监控 CPU/内存使用

### 问题：内存不足

**解决:**
```bash
# 减少 pool size
PIPELINE_POOL_SIZE=2

# 或增加服务器内存
```

### 问题：工具调用超时

**解决:**
```python
# 增加超时时间
@with_timeout(1800)  # 30分钟
async def execute_tool_call(...):
    ...
```

## 总结

| 优化项 | Gradio Demo | API Server | 改进 |
|--------|-------------|-----------|------|
| Pipeline 复用 | 全局单例 ⚠️ | 连接池 ✅ | 避免竞争 |
| 并发限制 | 无 ⚠️ | Semaphore ✅ | 防止过载 |
| 请求排队 | 随机 ⚠️ | 有序队列 ✅ | 公平调度 |
| 监控指标 | 无 ⚠️ | 健康检查 ✅ | 可观测性 |
| 理论加速比 | 1.0-1.2x | 2.0-3.0x | 2-3倍提升 |

**核心建议:**
- ✅ 使用 API Server 而非 Gradio Demo 用于生产环境
- ✅ 根据硬件资源调整 pool_size
- ✅ 监控 LLM API 的并发限制
- ✅ 考虑升级工具 API 套餐以提高限流阈值

