# API 双版本更新日志

## 🎉 新增功能

### 保留 V1 接口（标准 OpenAI 格式）
- **端点**: `/v1/chat/completions`
- **适配器**: `services/openai_adapter.py`
- **特点**: 完全兼容 OpenAI Chat Completions API
- **输出**: 简单的 `content` 字段流式输出

### 新增 V2 接口（扩展研究过程格式）
- **端点**: `/v2/chat/completions`  
- **适配器**: `services/openai_adapter_v2.py`
- **特点**: 带研究过程追踪的扩展格式
- **输出**: 包含 `taskstat`, `content_type`, `taskid`, `parent_taskid`, `index` 等扩展字段

## 📋 核心变更

### 1. 文件结构
```
apps/api-server/
├── services/
│   ├── openai_adapter.py      # V1 适配器（标准格式）
│   └── openai_adapter_v2.py   # V2 适配器（扩展格式）
├── routers/
│   └── chat.py                # 包含 V1 和 V2 路由
├── main.py                    # 更新根端点信息
├── API_VERSIONS.md            # 版本对比文档
├── QUICK_START.md             # 快速开始指南
└── test_v1_v2_comparison.py   # 对比测试
```

### 2. 路由配置

#### V1 路由
```python
@router.post("/v1/chat/completions")
async def create_chat_completion(...)
```

#### V2 路由
```python
@router.post("/v2/chat/completions")
async def create_chat_completion_v2(...)
```

### 3. 适配器差异

#### OpenAIAdapter (V1)
- 返回单个 `ChatCompletionChunk`
- 简单的事件到内容转换
- 只包含 `content` 字段

#### OpenAIAdapterV2 (V2)
- 返回 `List[ChatCompletionChunk]`（支持多阶段输出）
- 复杂的状态管理
- 包含扩展字段：
  - `taskstat`: 任务状态（message_start, message_process, message_result）
  - `role`: 角色（task 或 assistant）
  - `content_type`: 内容类型（research_process_block, research_think_block 等）
  - `taskid`: 任务唯一ID
  - `parent_taskid`: 父任务ID
  - `index`: 序号
  - `task_content`: 任务内容
  - `content`: 标准内容字段

### 4. 流式输出对比

#### V1 输出示例
```json
{
  "choices": [{
    "delta": {
      "content": "简单的文本内容"
    }
  }]
}
```

#### V2 输出示例
```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_start",
      "role": "task",
      "content_type": "research_process_block",
      "parent_taskid": "",
      "index": 0,
      "task_content": "",
      "content": "",
      "taskid": "1768813136443816"
    }
  }]
}
```

## 🔧 技术实现

### V2 关键特性

#### 1. 层级结构追踪
- 使用 `parent_taskid` 和 `index` 构建树形结构
- 根节点的 `parent_taskid` 为空字符串
- `index` 用于排序和定位

#### 2. 任务状态管理
```python
self.current_task_blocks = {}  # 追踪活动任务
self.root_process_taskid = None  # 根任务ID
self.root_process_chunk = None  # 延迟发送的根完成块
```

#### 3. 多阶段输出
单个事件可能生成多个 chunks：
```python
def convert_event_to_chunk(...) -> List[ChatCompletionChunk]:
    chunks = []
    chunks.append(start_chunk)
    chunks.append(process_chunk)
    chunks.append(result_chunk)
    return chunks
```

#### 4. 内容类型
- `research_process_block`: 根容器
- `research_think_block`: 思考过程
- `research_web_search_keyword`: 搜索关键词
- `research_web_search`: 搜索结果（JSON Lines）
- `research_web_browse`: 网页浏览（JSON）
- `research_text_block`: 文本块
- `research_completed`: 完成标记

#### 5. 最终回复格式
V2 的最终回复仍使用标准 OpenAI 格式：
```python
{
  "role": "assistant",
  "index": 10,
  "content": "最终回复内容"
}
```

## 📊 测试验证

### 运行测试
```bash
cd apps/api-server
python3 test_v1_v2_comparison.py
```

### 测试结果
```
✅ 所有测试通过！V1 和 V2 API 都工作正常。
```

### V1 测试
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"mirothinker","messages":[{"role":"user","content":"hello"}],"stream":true}'
```

### V2 测试
```bash
curl -X POST http://localhost:8000/v2/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"mirothinker","messages":[{"role":"user","content":"hello"}],"stream":true}'
```

## 🚀 部署说明

### Docker 部署
1. 添加 `.dockerignore` 排除 `.venv` 目录
2. 重新构建镜像：
   ```bash
   docker compose up -d --build api-server
   ```

### 开发模式
```bash
cd apps/api-server
uv run uvicorn main:app --reload --port 8000
```

## 📝 向后兼容性

- ✅ V1 接口保持不变，现有客户端无需修改
- ✅ V2 是新增接口，不影响现有功能
- ✅ 两个版本可以同时使用
- ✅ 共享相同的后端 Pipeline

## 🎯 使用建议

### 选择 V1 的场景
- 使用标准 OpenAI SDK
- 不需要展示研究过程
- 快速集成和原型开发
- 简单的聊天界面

### 选择 V2 的场景
- 需要可视化研究过程
- 需要层级化展示信息
- 需要区分不同类型内容
- 自定义前端应用

## 📚 相关文档

- **API_VERSIONS.md**: 详细的版本对比说明
- **QUICK_START.md**: 快速开始指南
- **边思考边检索.md**: V2 格式详细规范
- **test_v1_v2_comparison.py**: 对比测试脚本

## 🔮 未来计划

- [ ] 添加更多内容类型支持
- [ ] 优化 V2 性能和网络传输
- [ ] 提供前端 SDK
- [ ] 添加更多测试用例

## ✅ 验证清单

- [x] V1 接口保持原有功能
- [x] V2 接口正确实现扩展字段
- [x] 根端点显示两个版本
- [x] 单元测试通过
- [x] Docker 部署测试通过
- [x] 文档完整

---

**更新日期**: 2026-01-19  
**版本**: 0.1.0  
**贡献者**: MiroThinker Team

