# API 格式说明 V2

## 概览

本文档描述了 MiroThinker API 的流式输出格式，该格式基于 OpenAI Chat Completions API，并添加了用于前端渲染研究过程的扩展字段。

参考文档：`apps/api-server/边思考边检索.md`

## 响应格式

所有流式响应都是标准的 OpenAI Chat Completion Chunk 格式，不包含额外的外层包装：

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion.chunk",
  "created": 1737315571,
  "model": "mirothinker",
  "choices": [{
    "index": 0,
    "delta": {
      // Delta 内容
    },
    "finish_reason": null
  }]
}
```

## 扩展字段

### 研究过程消息（role = "task"）

研究过程中的所有消息都在 `delta` 中包含以下扩展字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `taskstat` | string | 消息状态：`message_start`, `message_process`, `message_result` |
| `role` | string | 固定值 `"task"` |
| `content_type` | string | 内容类型，见下文 |
| `parent_taskid` | string | 父任务ID，用于建立层级关系 |
| `index` | number | 消息序号，用于排序 |
| `task_content` | string | 任务内容 |
| `content` | string | 固定为空字符串 `""` |
| `taskid` | string | 唯一任务ID |

### 最终回复（role = "assistant"）

最终回复使用标准 OpenAI 格式，但添加了 `index` 字段：

```json
{
  "delta": {
    "role": "assistant",
    "index": 8,
    "content": "回复内容..."
  }
}
```

## 内容类型（content_type）

### 1. research_process_block（研究过程根节点）

顶层容器节点，所有研究活动都是它的子节点。

- `parent_taskid`: 空字符串 `""`
- `task_content`: 空字符串 `""`
- **特殊行为**: `message_result` 在研究结束时才发送（延迟完成）

示例：
```json
{
  "taskstat": "message_start",
  "role": "task",
  "content_type": "research_process_block",
  "parent_taskid": "",
  "index": 0,
  "task_content": "",
  "content": "",
  "taskid": "research-process-root"
}
```

### 2. research_think_block（思考过程）

显示 AI 的思考和推理过程。

- `task_content` (message_start): JSON 格式 `{"label": "思考过程"}`
- `task_content` (message_process): 思考内容文本（流式输出）

示例：
```json
// message_start
{
  "taskstat": "message_start",
  "content_type": "research_think_block",
  "task_content": "{\"label\":\"思考过程\"}",
  "parent_taskid": "research-process-root",
  "index": 1,
  "taskid": "research-think-001"
}

// message_process (可以有多个)
{
  "taskstat": "message_process",
  "content_type": "research_think_block",
  "task_content": "正在分析用户问题...\n\n",
  "parent_taskid": "research-process-root",
  "index": 1,
  "taskid": "research-think-001"
}
```

### 3. research_web_search（网络搜索结果）

搜索结果列表，使用 **JSON Lines** 格式。

- `task_content` (message_start): JSON 格式 `{"label": "搜索完成，共 {count} 个匹配项", "count": 5}`
- `task_content` (message_process): JSON Lines 格式，每行一个搜索结果

JSON Lines 格式：
```json
{"index":1,"title":"标题","link":"URL"}
{"index":2,"title":"标题","link":"URL"}
```

示例：
```json
// message_process
{
  "taskstat": "message_process",
  "content_type": "research_web_search",
  "task_content": "{\"index\":1,\"title\":\"WHO-人工智能在医疗保健中的应用\",\"link\":\"https://www.who.int/health-topics/artificial-intelligence\"}\n{\"index\":2,\"title\":\"Nature Medicine-AI医疗诊断研究\",\"link\":\"https://www.nature.com/nm/\"}\n",
  "parent_taskid": "research-process-root",
  "index": 2,
  "taskid": "research-search-001"
}
```

### 4. research_web_browse（网页浏览）

浏览网页获取的详细信息。

- `task_content` (message_start): JSON 格式 `{"label": "正在浏览网页"}`
- `task_content` (message_process): JSON 格式的网页信息

网页信息 JSON 格式：
```json
{
  "index": 1,
  "title": "网页标题",
  "link": "URL",
  "snippet": "内容摘要...",
  "sitename": "网站名称"
}
```

示例：
```json
{
  "taskstat": "message_process",
  "content_type": "research_web_browse",
  "task_content": "{\"index\":1,\"title\":\"WHO-人工智能在医疗保健中的应用\",\"link\":\"https://www.who.int/health-topics/artificial-intelligence\",\"snippet\":\"世界卫生组织关于AI在医疗保健领域应用的权威指南，涵盖伦理、监管和实施建议。\",\"sitename\":\"世界卫生组织\"}",
  "parent_taskid": "research-process-root",
  "index": 3,
  "taskid": "research-browse-001"
}
```

### 5. research_text_block（文本内容块）

从网页或其他来源提取的结构化文本内容。

- `task_content` (message_start): JSON 格式 `{"label": "标题"}`
- `task_content` (message_process): Markdown 格式的文本内容（流式输出）

示例：
```json
// message_start
{
  "taskstat": "message_start",
  "content_type": "research_text_block",
  "task_content": "{\"label\":\"WHO 关键发现\"}",
  "parent_taskid": "research-process-root",
  "index": 4,
  "taskid": "research-text-001"
}

// message_process
{
  "taskstat": "message_process",
  "content_type": "research_text_block",
  "task_content": "## 人工智能在医疗领域的应用\n\n根据世界卫生组织的报告...\n",
  "parent_taskid": "research-process-root",
  "index": 4,
  "taskid": "research-text-001"
}
```

### 6. research_completed（研究完成标识）

标记研究阶段完成，即将开始最终回复。

- `task_content` (message_start): JSON 格式 `{"label": "已收集充分的信息，即将开始回复"}`
- 其他阶段 `task_content` 为空

示例：
```json
{
  "taskstat": "message_start",
  "content_type": "research_completed",
  "task_content": "{\"label\":\"已收集充分的信息，即将开始回复\"}",
  "parent_taskid": "research-process-root",
  "index": 7,
  "taskid": "research-completed-001"
}
```

## 消息状态（taskstat）

### message_start
- 开始一个新的内容块
- `task_content` 通常包含 JSON 格式的标题信息：`{"label": "标题文本"}`
- 前端应创建新的 UI 容器

### message_process
- 流式输出内容
- `task_content` 包含实际的文本、JSON 或 JSON Lines 数据
- 同一 `taskid` 可能有多个 `message_process` 消息
- 前端应追加内容到对应容器

### message_result
- 结束内容块
- `task_content` 为空字符串
- 前端应标记该容器完成

## 层级结构

使用 `parent_taskid` 和 `index` 建立层级关系：

```
research_process_block (index=0, parent_taskid="")
├── research_think_block (index=1, parent_taskid=root_taskid)
├── research_web_search (index=2, parent_taskid=root_taskid)
├── research_web_browse (index=3, parent_taskid=root_taskid)
├── research_text_block (index=4, parent_taskid=root_taskid)
├── research_web_browse (index=5, parent_taskid=root_taskid)
├── research_text_block (index=6, parent_taskid=root_taskid)
└── research_completed (index=7, parent_taskid=root_taskid)

最终回复 (index=8, role="assistant")
```

## 消息顺序

1. **根节点开始**: `research_process_block` 的 `message_start` 和 `message_process`
2. **研究过程**: 各种子节点（思考、搜索、浏览、文本块等）
3. **研究完成**: `research_completed` 的完整生命周期
4. **根节点结束**: `research_process_block` 的 `message_result`（延迟发送）
5. **最终回复**: 标准 OpenAI 格式的 `role: "assistant"` 消息

**重要**: 根节点的 `message_result` 在所有子节点完成后才发送，这允许前端正确管理层级关系。

## 前端实现建议

### 1. 数据结构

建议使用树形结构存储消息：

```typescript
interface TaskNode {
  taskid: string;
  parent_taskid: string;
  content_type: string;
  index: number;
  title: string;  // 从 message_start 的 task_content JSON 解析
  task_content: string;  // 累积的内容
  isComplete: boolean;  // message_result 已收到
  children: TaskNode[];
}
```

### 2. 处理流程

```javascript
function handleChunk(chunk) {
  const delta = chunk.choices[0].delta;
  
  if (delta.role === "task") {
    const { taskstat, taskid, parent_taskid, content_type, task_content, index } = delta;
    
    if (taskstat === "message_start") {
      // 创建新节点
      const node = {
        taskid,
        parent_taskid,
        content_type,
        index,
        title: parseTitle(task_content),
        task_content: "",
        isComplete: false,
        children: []
      };
      
      // 添加到父节点的 children 或根列表
      addNode(node, parent_taskid);
      
    } else if (taskstat === "message_process") {
      // 追加内容
      const node = findNode(taskid);
      node.task_content += task_content;
      updateUI(node);
      
    } else if (taskstat === "message_result") {
      // 标记完成
      const node = findNode(taskid);
      node.isComplete = true;
      updateUI(node);
    }
    
  } else if (delta.role === "assistant") {
    // 最终回复
    appendFinalAnswer(delta.content);
  }
}

function parseTitle(task_content) {
  if (task_content) {
    try {
      const obj = JSON.parse(task_content);
      return obj.label || "";
    } catch {
      return "";
    }
  }
  return "";
}
```

### 3. 渲染样式

根据 `content_type` 应用不同样式：

- `research_process_block`: 容器/折叠面板
- `research_think_block`: 思考气泡/展开面板
- `research_web_search`: 搜索结果列表（解析 JSON Lines）
- `research_web_browse`: 网页卡片（解析 JSON）
- `research_text_block`: Markdown 渲染
- `research_completed`: 完成标记/分隔线

## 完整示例

参见 `apps/api-server/边思考边检索.md` 获取完整的流数据示例。

## 测试

运行测试验证格式：

```bash
cd apps/api-server
python3 test_new_format_v2.py
```

## 与 OpenAI API 的兼容性

- ✅ 保持标准 OpenAI Chat Completion Chunk 格式
- ✅ 最终回复（`role: "assistant"`）完全兼容
- ✅ 不支持扩展字段的客户端可以忽略 `role: "task"` 的消息
- ✅ 可以直接使用 OpenAI 客户端库解析基础结构

