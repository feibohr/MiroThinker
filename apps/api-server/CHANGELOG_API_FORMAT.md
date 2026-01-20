# API 格式更新说明

## 更新日期
2026-01-19

## 更新概述
为 api-server 的聊天接口添加了扩展字段支持，使前端能够以不同样式渲染研究过程的各个阶段。

## 主要变更

### 1. 新增外层包装格式

所有流式响应都包装在以下结构中：

```json
{
  "type": "chat",
  "messageId": "唯一的消息会话ID（UUID）",
  "chatResp": {
    // OpenAI Chat Completion Chunk 对象
  }
}
```

- **type**: 固定值 "chat"
- **messageId**: UUID 格式，同一次对话保持不变
- **chatResp**: 包含标准 OpenAI 格式的响应数据

### 2. 新增扩展字段

在 OpenAI Chat Completions 格式的 `delta` 对象中新增以下字段：

- **taskstat**: 任务状态（message_start / message_process / message_result）
- **role**: 新增 "task" 角色，用于标识研究过程消息
- **content_type**: 内容类型，区分不同的研究阶段
- **task_content**: 任务内容，存放实际文本
- **taskid**: 唯一任务块ID，用于追踪内容块的生命周期

### 2. 支持的内容类型

- `research_process_block`: 研究过程开始标题
- `research_htink_block`: 思考/反思内容
- `research_web_search_keyword`: 搜索关键字
- `research_web_search`: 搜索结果
- `research_web_browse`: 浏览网页内容
- `research_completed`: 研究完成标题

### 3. 文件修改清单

#### 修改的文件

1. **`services/openai_adapter.py`**
   - 添加 `create_task_chunk()` 方法，创建扩展格式的消息块
   - 重构 `convert_event_to_chunk()` 方法，返回 `List[ChatCompletionChunk]` 以支持多阶段发送
   - 添加状态管理器 `current_task_blocks` 追踪活跃的内容块
   - 实现针对不同事件类型的处理方法：
     - `_handle_start_of_agent()`: 处理研究开始
     - `_handle_end_of_agent()`: 处理研究结束
     - `_handle_search_tool()`: 处理搜索工具
     - `_handle_scrape_tool()`: 处理网页抓取工具
     - `_convert_message()`: 处理思考内容流
     - `_convert_tool_call()`: 处理工具调用

2. **`routers/chat.py`**
   - 更新 `ChatMessage` 模型，支持 "task" 角色
   - 修改 `_stream_chat_completion()` 方法，处理返回的 chunk 列表

#### 新增的文件

1. **`API_FORMAT.md`**
   - 详细的 API 格式说明文档
   - 包含各个字段的含义和使用方法
   - 提供完整的交互流程示例
   - 前端实现建议

2. **`API_RESPONSE_EXAMPLE.json`**
   - 完整的 API 响应示例
   - 展示从研究开始到最终回复的完整流程
   - 包含所有内容类型的示例

3. **`test_new_format.py`**
   - 单元测试，验证新格式的正确性
   - 测试所有事件类型的转换
   - 测试状态管理和内容块追踪

## 兼容性说明

### 向后兼容
- 保持与 OpenAI Chat Completions API 的基本兼容性
- 新字段仅在研究过程中使用，不影响最终回复格式
- 不支持新格式的客户端可以忽略 `task` 角色的消息

### 最终回复格式
最终回复（show_text 工具）仍然使用标准的 OpenAI 格式，但也包装在外层结构中：
```json
{
  "type": "chat",
  "messageId": "同一次对话的UUID",
  "chatResp": {
    "id": "chatcmpl-xxx",
    "object": "chat.completion.chunk",
    "created": 1737300000,
    "model": "mirothinker",
    "choices": [{
      "index": 0,
      "delta": {
        "role": "assistant",
        "content": "回复内容..."
      },
      "finish_reason": null
    }]
  }
}
```

## 测试

运行以下命令进行测试：

```bash
cd apps/api-server
python3 test_new_format.py
```

所有测试应该通过：
- ✓ Adapter initialization test passed
- ✓ Task chunk creation test passed
- ✓ Start of agent event test passed
- ✓ Message event test passed
- ✓ Search tool event test passed
- ✓ Show text event test passed
- ✓ End of agent event test passed

## 前端集成建议

1. **监听 taskid**：使用 taskid 追踪同一内容块的开始、处理和结束
2. **区分 taskstat**：
   - `message_start`: 创建新的 UI 容器，解析 task_content 中的 JSON 标题
   - `message_process`: 追加内容到容器
   - `message_result`: 标记容器完成
3. **应用样式**：根据 content_type 应用不同的渲染样式
4. **处理最终回复**：当 role 为 "assistant" 且无 taskstat 字段时，显示最终答案

## 示例流程

```
1. 正在收集和分析资料 (research_process_block)
2. 正在理解用户的提问 (research_htink_block) 
   └─ 思考内容... (流式输出)
3. 搜索: xxx (research_web_search_keyword)
4. 根据用户需求搜索到相关网页：N个 (research_web_search)
   ├─ 网页1 标题 + URL
   ├─ 网页2 标题 + URL
   └─ ...
5. 浏览网页 (research_web_browse)
   └─ URL + 内容摘要
6. 已收集充分的信息，即将开始回复 (research_completed)
7. [最终回复] (标准 OpenAI 格式)
```

## 注意事项

1. **taskid 生成**：使用微秒级时间戳确保唯一性
2. **内容长度**：网页内容超过 2000 字符会被截断
3. **搜索结果**：默认显示前 10 个搜索结果
4. **错误处理**：错误也会以 research_htink_block 格式展示
5. **心跳事件**：heartbeat 事件被过滤，不会发送到客户端

## 下一步

- 前端实现对应的渲染组件
- 根据实际使用情况调整内容类型和标题文案
- 考虑添加更多内容类型以支持其他工具
- 优化长内容的分段和显示策略

