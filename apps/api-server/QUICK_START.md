# MiroThinker API 快速开始

## 🚀 两个版本，两种选择

### V1 - 简单格式（标准 OpenAI 兼容）
**适合**: 快速集成、标准客户端、简单界面

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mirothinker",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": true
  }'
```

**输出格式**:
```json
{
  "choices": [{
    "delta": {
      "content": "简单的文本内容"
    }
  }]
}
```

---

### V2 - 扩展格式（研究过程可视化）
**适合**: 需要展示思考过程、搜索结果、层级结构的前端

```bash
curl -X POST http://localhost:8000/v2/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mirothinker",
    "messages": [{"role": "user", "content": "介绍人工智能"}],
    "stream": true
  }'
```

**输出格式**:
```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_start",
      "role": "task",
      "content_type": "research_think_block",
      "parent_taskid": "root_id",
      "index": 1,
      "task_content": "{\"label\": \"思考过程\"}",
      "taskid": "task_id"
    }
  }]
}
```

---

## 📋 V2 内容类型速查

| content_type | 说明 | 示例 |
|-------------|------|------|
| `research_process_block` | 研究过程容器（根节点） | 整个研究流程 |
| `research_think_block` | 思考过程 | AI 的推理内容 |
| `research_web_search_keyword` | 搜索关键词 | "搜索：人工智能" |
| `research_web_search` | 搜索结果（JSON Lines） | 网页列表 |
| `research_web_browse` | 网页浏览 | 访问的网页 |
| `research_text_block` | 文本内容块 | 摘要或说明 |
| `research_completed` | 研究完成标记 | "即将开始回复" |

---

## 🔄 V2 任务状态流程

```
message_start    →    message_process    →    message_result
    (开始)              (内容输出)               (结束)
     ↓                     ↓                      ↓
  显示标题             追加内容                关闭块
```

---

## 🧪 测试命令

```bash
# 运行对比测试
cd apps/api-server
python3 test_v1_v2_comparison.py

# 测试服务器健康状态
curl http://localhost:8000/health

# 查看所有端点
curl http://localhost:8000/
```

---

## 📦 启动服务

```bash
# Docker 方式
docker compose up -d api-server

# 本地开发
cd apps/api-server
uv run uvicorn main:app --reload --port 8000
```

---

## 💡 前端集成示例（V2）

```javascript
// 创建任务树
const tasks = {};

const processChunk = (chunk) => {
  const delta = chunk.choices[0].delta;
  
  if (delta.role === 'task') {
    const { taskid, parent_taskid, taskstat, content_type, task_content, index } = delta;
    
    // 初始化任务
    if (taskstat === 'message_start') {
      tasks[taskid] = {
        type: content_type,
        parent: parent_taskid,
        index: index,
        label: task_content ? JSON.parse(task_content).label : '',
        content: ''
      };
      renderTaskStart(taskid);
    }
    
    // 追加内容
    else if (taskstat === 'message_process') {
      tasks[taskid].content += task_content;
      updateTaskContent(taskid, task_content);
    }
    
    // 结束任务
    else if (taskstat === 'message_result') {
      finishTask(taskid);
    }
  }
  
  // 最终回复（标准格式）
  else if (delta.role === 'assistant') {
    displayFinalAnswer(delta.content);
  }
};
```

---

## 📚 完整文档

- **详细说明**: `API_VERSIONS.md`
- **V1 格式**: `API_FORMAT_V1.md`（标准 OpenAI）
- **V2 格式**: `边思考边检索.md`（扩展格式）
- **示例响应**: `API_RESPONSE_EXAMPLE.json`

---

## ⚡ 性能对比

| 指标 | V1 | V2 |
|-----|----|----|
| Chunk 数量 | 较少 | 较多 |
| 网络流量 | 小 | 中 |
| 解析复杂度 | 低 | 中 |
| 展示效果 | 简单 | 丰富 |
| 兼容性 | OpenAI 完全兼容 | 需要自定义处理 |

---

**建议**: 
- 🟢 **初次使用**: 先用 V1 快速验证功能
- 🟡 **定制需求**: 需要可视化时切换到 V2
- 🔵 **混合使用**: 可以同时提供两个端点供不同客户端选择

