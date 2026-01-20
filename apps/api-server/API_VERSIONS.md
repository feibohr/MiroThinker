# API 版本说明

## 概述

MiroThinker API 提供两个版本的接口，分别满足不同的使用场景：

- **V1 (简单格式)**: 标准 OpenAI 兼容格式，适合传统客户端和简单展示
- **V2 (扩展格式)**: 带研究过程追踪的扩展格式，适合需要可视化研究过程的前端

## V1 API - 简单格式

### 端点
```
POST /v1/chat/completions
```

### 特点
- ✅ 完全兼容 OpenAI Chat Completions API
- ✅ 简单的流式输出，只包含 `content` 字段
- ✅ 适合使用标准 OpenAI 客户端的应用
- ✅ 易于集成，无需特殊前端处理

### 响应格式
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion.chunk",
  "created": 1768812375,
  "model": "mirothinker",
  "choices": [{
    "index": 0,
    "delta": {
      "content": "响应内容"
    },
    "finish_reason": null
  }]
}
```

### 使用示例
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mirothinker",
    "messages": [
      {"role": "user", "content": "你好"}
    ],
    "stream": true
  }'
```

## V2 API - 扩展格式

### 端点
```
POST /v2/chat/completions
```

### 特点
- ✅ 扩展的 OpenAI 格式，包含研究过程元数据
- ✅ 层级关系追踪 (`parent_taskid`, `index`)
- ✅ 多种内容类型标识 (`content_type`)
- ✅ 任务状态管理 (`taskstat`)
- ✅ JSON Lines 格式的搜索结果
- ✅ 结构化的网页浏览信息

### 扩展字段说明

#### `taskstat` (任务状态)
- `message_start`: 开始渲染，包含标题信息
- `message_process`: 正在渲染，包含内容
- `message_result`: 渲染结束

#### `content_type` (内容类型)
- `research_process_block`: 研究过程容器（根节点）
- `research_think_block`: 思考过程
- `research_web_search_keyword`: 搜索关键词
- `research_web_search`: 搜索结果
- `research_web_browse`: 网页浏览
- `research_text_block`: 文本内容块
- `research_completed`: 研究完成标记

#### 层级结构
- `taskid`: 当前任务的唯一ID
- `parent_taskid`: 父任务ID（空字符串表示根节点）
- `index`: 任务的序号，用于排序

### 响应格式
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion.chunk",
  "created": 1768812375,
  "model": "mirothinker",
  "choices": [{
    "index": 0,
    "delta": {
      "taskstat": "message_start",
      "role": "task",
      "content_type": "research_process_block",
      "parent_taskid": "",
      "index": 0,
      "task_content": "{\"label\": \"正在收集和分析资料\"}",
      "content": "",
      "taskid": "1768812375756911"
    },
    "finish_reason": null
  }]
}
```

### 使用示例
```bash
curl -X POST http://localhost:8000/v2/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mirothinker",
    "messages": [
      {"role": "user", "content": "介绍一下人工智能"}
    ],
    "stream": true
  }'
```

### V2 典型流程示例

1. **开始研究过程**
   ```json
   {
     "taskstat": "message_start",
     "content_type": "research_process_block",
     "parent_taskid": "",
     "taskid": "root_001",
     "index": 0
   }
   ```

2. **思考过程**
   ```json
   {
     "taskstat": "message_start",
     "content_type": "research_think_block",
     "parent_taskid": "root_001",
     "taskid": "think_001",
     "task_content": "{\"label\": \"思考过程\"}",
     "index": 1
   }
   ```

3. **搜索关键词**
   ```json
   {
     "taskstat": "message_start",
     "content_type": "research_web_search_keyword",
     "parent_taskid": "root_001",
     "taskid": "search_kw_001",
     "task_content": "{\"label\": \"搜索\", \"keyword\": \"人工智能\"}",
     "index": 2
   }
   ```

4. **搜索结果 (JSON Lines)**
   ```json
   {
     "taskstat": "message_process",
     "content_type": "research_web_search",
     "task_content": "{\"index\":1,\"title\":\"人工智能简介\",\"link\":\"https://...\"}\n{\"index\":2,\"title\":\"AI发展历史\",\"link\":\"https://...\"}\n"
   }
   ```

5. **最终回复 (标准格式)**
   ```json
   {
     "role": "assistant",
     "content": "根据研究，人工智能是...",
     "index": 10
   }
   ```

## 版本选择建议

### 使用 V1 的场景
- 使用标准 OpenAI SDK 的应用
- 不需要展示研究过程的场景
- 快速集成和原型开发
- 简单的聊天机器人界面

### 使用 V2 的场景
- 需要展示研究过程的前端应用
- 需要可视化思考和搜索过程
- 需要层级化展示信息
- 需要区分不同类型的内容（思考、搜索、浏览）

## 代码实现

### V1 适配器
文件：`services/openai_adapter.py`
- 简单的事件到内容转换
- 标准 OpenAI 格式输出
- 直接返回单个 chunk

### V2 适配器
文件：`services/openai_adapter_v2.py`
- 复杂的状态管理
- 扩展字段支持
- 层级关系追踪
- 可能返回多个 chunks

## 测试

运行对比测试：
```bash
cd apps/api-server
python3 test_v1_v2_comparison.py
```

## 迁移指南

### 从 V1 迁移到 V2

如果你的前端需要更丰富的展示效果，可以从 V1 迁移到 V2：

1. **更新 API 端点**
   ```javascript
   // 从
   const url = '/v1/chat/completions';
   // 改为
   const url = '/v2/chat/completions';
   ```

2. **解析扩展字段**
   ```javascript
   // V2 响应处理
   const delta = chunk.choices[0].delta;
   
   if (delta.role === 'task') {
     // 处理研究过程
     const contentType = delta.content_type;
     const taskStat = delta.taskstat;
     const taskId = delta.taskid;
     const parentTaskId = delta.parent_taskid;
     
     if (taskStat === 'message_start') {
       // 开始新的内容块
       const label = JSON.parse(delta.task_content).label;
     } else if (taskStat === 'message_process') {
       // 追加内容
       const content = delta.task_content;
     } else if (taskStat === 'message_result') {
       // 结束内容块
     }
   } else if (delta.role === 'assistant') {
     // 最终回复（标准格式）
     const finalAnswer = delta.content;
   }
   ```

3. **构建 UI 层级**
   使用 `parent_taskid` 和 `index` 构建树形结构：
   ```javascript
   const taskTree = {};
   
   if (delta.parent_taskid === '') {
     // 根节点
     taskTree[delta.taskid] = { children: [] };
   } else {
     // 子节点
     taskTree[delta.parent_taskid].children.push(delta.taskid);
   }
   ```

## 注意事项

1. **向后兼容**: V1 会持续维护，不会被废弃
2. **性能**: V2 生成的 chunks 数量更多，网络传输量略大
3. **解析复杂度**: V2 需要更复杂的前端逻辑来处理
4. **最终回复**: V2 中最终回复仍使用标准 OpenAI 格式 (`role: "assistant"`)

