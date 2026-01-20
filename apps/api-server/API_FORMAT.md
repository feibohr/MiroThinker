# API 格式说明

## 响应格式概览

所有流式响应都包装在以下外层结构中：

```json
{
  "type": "chat",
  "messageId": "唯一的消息会话ID",
  "chatResp": {
    // OpenAI Chat Completion Chunk 格式
  }
}
```

## 新增字段

在原有的 OpenAI Chat Completions 格式基础上，新增以下字段以支持更丰富的前端渲染：

### 外层包装字段

- **type**: 固定值 "chat"，标识这是聊天消息
- **messageId**: UUID 格式的消息会话ID，同一次对话中保持不变
- **chatResp**: OpenAI Chat Completion Chunk 对象

### Delta 字段扩展（在 chatResp.choices[0].delta 中）

```json
{
  "delta": {
    "taskstat": "message_start | message_process | message_result",
    "role": "task",
    "content_type": "研究任务内容类型",
    "task_content": "任务内容",
    "content": "",
    "taskid": "唯一任务ID"
  }
}
```

### 字段说明

- **taskstat**: 任务状态
  - `message_start`: 标题信息，通知前端开始渲染新的内容块
  - `message_process`: 正文信息，包含实际内容流
  - `message_result`: 通知前端该内容块渲染结束

- **role**: 消息角色
  - `task`: 表示这是一个任务相关的消息（研究过程）
  - `assistant`: 标准助手回复（最终答案）

- **content_type**: 内容类型，用于前端区分渲染样式
  - `research_process_block`: 研究过程块（固定标题）
  - `research_htink_block`: 思考块（反思内容）
  - `research_web_search_keyword`: 搜索关键字
  - `research_web_search`: 搜索结果
  - `research_web_browse`: 浏览网页内容
  - `research_completed`: 研究完成（固定标题）

- **task_content**: 任务内容
  - 当 `taskstat` 为 `message_start` 时，包含 JSON 格式的标题信息：`{"label": "标题文本"}`
  - 当 `taskstat` 为 `message_process` 时，包含实际的文本内容
  - 当 `taskstat` 为 `message_result` 时，为空字符串

- **taskid**: 唯一任务块 ID，用于前端追踪同一个内容块的不同状态

## 交互流程示例

### 1. 研究开始

```json
{
  "type": "chat",
  "messageId": "uuid",
  "chatResp": {
    "model": "mirothinker",
    "id": "chatcmpl-xxx",
    "choices": [{
      "delta": {
        "taskstat": "message_start",
        "role": "task",
        "content_type": "research_process_block",
        "task_content": "{\"label\": \"正在收集和分析资料\"}",
        "content": "",
        "taskid": "1737123456789000"
      },
      "index": 0
    }],
    "object": "chat.completion.chunk"
  }
}
```

```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_result",
      "role": "task",
      "content_type": "research_process_block",
      "task_content": "",
      "content": "",
      "taskid": "1737123456789000"
    }
  }]
}
```

### 2. 思考块

**开始思考：**
```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_start",
      "role": "task",
      "content_type": "research_htink_block",
      "task_content": "{\"label\": \"正在理解用户的提问\"}",
      "content": "",
      "taskid": "1737123456789001"
    }
  }]
}
```

**思考内容流：**
```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_process",
      "role": "task",
      "content_type": "research_htink_block",
      "task_content": "用户想要了解",
      "content": "",
      "taskid": "1737123456789001"
    }
  }]
}
```

```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_process",
      "role": "task",
      "content_type": "research_htink_block",
      "task_content": "商业航天的发展历程...",
      "content": "",
      "taskid": "1737123456789001"
    }
  }]
}
```

**结束思考：**
```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_result",
      "role": "task",
      "content_type": "research_htink_block",
      "task_content": "",
      "content": "",
      "taskid": "1737123456789001"
    }
  }]
}
```

### 3. 搜索关键字

```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_start",
      "role": "task",
      "content_type": "research_web_search_keyword",
      "task_content": "{\"label\": \"搜索\"}",
      "content": "",
      "taskid": "1737123456789002"
    }
  }]
}
```

```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_process",
      "role": "task",
      "content_type": "research_web_search_keyword",
      "task_content": "商业航天发展历程 2026",
      "content": "",
      "taskid": "1737123456789002"
    }
  }]
}
```

```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_result",
      "role": "task",
      "content_type": "research_web_search_keyword",
      "task_content": "",
      "content": "",
      "taskid": "1737123456789002"
    }
  }]
}
```

### 4. 搜索结果

**结果数量：**
```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_start",
      "role": "task",
      "content_type": "research_web_search",
      "task_content": "{\"label\": \"根据用户需求搜索到相关网页：5个\"}",
      "content": "",
      "taskid": "1737123456789003"
    }
  }]
}
```

**每个搜索结果：**
```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_start",
      "role": "task",
      "content_type": "research_web_search",
      "task_content": "{\"label\": \"商业航天发展报告 - 官方网站\"}",
      "content": "",
      "taskid": "1737123456789004"
    }
  }]
}
```

```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_process",
      "role": "task",
      "content_type": "research_web_search",
      "task_content": "https://example.com/space-report",
      "content": "",
      "taskid": "1737123456789004"
    }
  }]
}
```

```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_result",
      "role": "task",
      "content_type": "research_web_search",
      "task_content": "",
      "content": "",
      "taskid": "1737123456789004"
    }
  }]
}
```

### 5. 浏览网页

**浏览标题：**
```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_start",
      "role": "task",
      "content_type": "research_web_browse",
      "task_content": "{\"label\": \"浏览网页\"}",
      "content": "",
      "taskid": "1737123456789005"
    }
  }]
}
```

**网页内容：**
```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_start",
      "role": "task",
      "content_type": "research_web_browse",
      "task_content": "{\"label\": \"https://example.com/space-report\"}",
      "content": "",
      "taskid": "1737123456789006"
    }
  }]
}
```

```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_process",
      "role": "task",
      "content_type": "research_web_browse",
      "task_content": "网页内容摘要...",
      "content": "",
      "taskid": "1737123456789006"
    }
  }]
}
```

```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_result",
      "role": "task",
      "content_type": "research_web_browse",
      "task_content": "",
      "content": "",
      "taskid": "1737123456789006"
    }
  }]
}
```

### 6. 研究完成

```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_start",
      "role": "task",
      "content_type": "research_completed",
      "task_content": "{\"label\": \"已收集充分的信息，即将开始回复\"}",
      "content": "",
      "taskid": "1737123456789007"
    }
  }]
}
```

```json
{
  "choices": [{
    "delta": {
      "taskstat": "message_result",
      "role": "task",
      "content_type": "research_completed",
      "task_content": "",
      "content": "",
      "taskid": "1737123456789007"
    }
  }]
}
```

### 7. 最终回复

最终回复使用标准的 OpenAI 格式：

```json
{
  "choices": [{
    "delta": {
      "role": "assistant",
      "content": "根据收集到的资料，商业航天..."
    },
    "index": 0
  }]
}
```

## 前端实现建议

1. **根据 taskid 追踪内容块**：
   - 使用 `taskid` 来识别同一个内容块的开始、处理和结束事件
   - 在 `message_start` 时创建新的 UI 容器
   - 在 `message_process` 时更新内容
   - 在 `message_result` 时标记完成

2. **根据 content_type 应用不同样式**：
   - `research_process_block`: 显示为进度指示器
   - `research_htink_block`: 显示为思考气泡或展开面板
   - `research_web_search_keyword`: 显示为搜索框样式
   - `research_web_search`: 显示为搜索结果列表项
   - `research_web_browse`: 显示为网页预览卡片
   - `research_completed`: 显示为完成标记

3. **处理 task_content**：
   - `message_start` 时，解析 JSON 格式的 `{"label": "xxx"}` 作为标题
   - `message_process` 时，直接显示文本内容
   - 支持流式追加文本（多个 `message_process` 事件）

4. **兼容标准回复**：
   - 当 `role` 为 `assistant` 且没有 `taskstat` 字段时，按标准 OpenAI 格式处理
   - 使用 `content` 字段而不是 `task_content`

## 兼容性说明

- 所有新字段都在 `delta` 对象内，不影响现有的 OpenAI 客户端解析
- 不支持新格式的客户端可以忽略 `task` 角色的消息，只显示最终的 `assistant` 回复
- 保持与 OpenAI Chat Completions API 的基本兼容性

