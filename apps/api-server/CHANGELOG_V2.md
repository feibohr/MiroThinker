# API 格式变更日志 V2

## 更新日期
2026-01-19

## 更新概述

基于 `apps/api-server/边思考边检索.md` 参考文档，完全重构了 API 流式输出格式，以支持层级化的研究过程展示。

## 主要变更

### 1. 移除外层包装
- ❌ 移除了之前的 `{type, messageId, chatResp}` 外层包装
- ✅ 直接输出标准 OpenAI Chat Completion Chunk 格式

**之前的格式：**
```json
{
  "type": "chat",
  "messageId": "uuid",
  "chatResp": {
    "id": "chatcmpl-xxx",
    "choices": [...]
  }
}
```

**现在的格式：**
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion.chunk",
  "created": 1737315571,
  "model": "mirothinker",
  "choices": [...]
}
```

### 2. 添加层级关系字段

在 `delta` 对象中添加了 `parent_taskid` 和 `index` 字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `parent_taskid` | string | 父任务ID，建立树形层级关系 |
| `index` | number | 消息序号，用于排序 |

**示例：**
```json
{
  "delta": {
    "taskstat": "message_start",
    "role": "task",
    "content_type": "research_think_block",
    "parent_taskid": "research-process-root",
    "index": 1,
    "task_content": "{\"label\":\"思考过程\"}",
    "taskid": "research-think-001"
  }
}
```

### 3. 修正 content_type 名称

- ❌ `research_htink_block` （拼写错误）
- ✅ `research_think_block` （正确拼写）

### 4. 新增 research_text_block 类型

添加了新的内容类型用于显示结构化文本内容：

```json
{
  "content_type": "research_text_block",
  "task_content": "## 标题\n\nMarkdown 格式的内容..."
}
```

用途：
- 显示从网页提取的关键信息
- 展示分析结果和总结
- 支持 Markdown 格式渲染

### 5. 搜索结果改为 JSON Lines 格式

**之前的格式**（多个独立块）：
```json
// 多个 chunk，每个结果一个
{
  "task_content": "{\"label\": \"网页标题\"}"
}
{
  "task_content": "https://example.com"
}
```

**现在的格式**（JSON Lines）：
```json
{
  "task_content": "{\"index\":1,\"title\":\"网页标题\",\"link\":\"URL\"}\n{\"index\":2,\"title\":\"标题2\",\"link\":\"URL2\"}\n"
}
```

优势：
- 减少消息数量
- 更容易解析和批处理
- 更高效的网络传输

### 6. 网页浏览改为 JSON 格式

**之前**：
```json
{
  "task_content": "https://example.com"
}
```

**现在**：
```json
{
  "task_content": "{\"index\":1,\"title\":\"网页标题\",\"link\":\"URL\",\"snippet\":\"摘要\",\"sitename\":\"网站名\"}"
}
```

包含更丰富的元数据。

### 7. 实现根节点延迟完成

引入了 `research_process_block` 作为根容器节点，其 `message_result` 在所有子节点完成后才发送。

**消息顺序：**
```
1. research_process_block: message_start
2. research_process_block: message_process
3. [子节点1: 思考过程]
4. [子节点2: 搜索结果]
5. [子节点3: 浏览网页]
6. ...
7. research_completed: 完整生命周期
8. research_process_block: message_result  <-- 延迟到最后
9. 最终回复 (role: assistant)
```

### 8. 最终回复添加 index 字段

```json
{
  "delta": {
    "role": "assistant",
    "index": 8,
    "content": "回复内容..."
  }
}
```

## 文件变更

### 修改的文件

1. **`services/openai_adapter.py`**
   - 添加 `root_process_taskid` 和 `current_index` 状态追踪
   - 重构所有事件处理方法以添加 `parent_taskid` 和 `index`
   - 实现 `_create_text_block()` 方法
   - 修改搜索结果输出为 JSON Lines 格式
   - 修改网页浏览输出为 JSON 格式
   - 实现根节点延迟完成逻辑

2. **`routers/chat.py`**
   - 移除外层包装逻辑
   - 直接输出 OpenAI 格式
   - 使用 `model_dump_json(exclude_none=True)` 清理输出

### 新增文件

1. **`API_FORMAT_V2.md`** - 完整的格式说明文档
2. **`test_new_format_v2.py`** - 全面的单元测试
3. **`CHANGELOG_V2.md`** - 本文档

### 删除/废弃文件

- `API_FORMAT.md` - 被 `API_FORMAT_V2.md` 替代
- `API_RESPONSE_EXAMPLE.json` - 示例格式已过时，参考 `边思考边检索.md`
- `test_wrapped_format.py` - 被 `test_new_format_v2.py` 替代

## 测试结果

所有测试通过：

```bash
$ python3 test_new_format_v2.py

Testing new API format (边思考边检索.md compatible)...

Test 1: Start of agent (root research_process_block)
✓ Root process block created: taskid=1768811445705569, index=0
✓ Think block created as child: parent_taskid=1768811445705569

Test 2: Message streaming (thinking content)
✓ Message streaming works: taskstat=message_process

Test 3: Google search with JSON Lines format
✓ Found JSON Line: {"index": 1, "title": "测试结果1", "link": "https://ex...
✓ Search results in JSON Lines format

Test 4: End of agent (root completion delayed)
✓ Root completion block sent at end: taskid=1768811445705569

Test 5: Show text (final answer with index)
✓ Final answer format correct: role=assistant, index=8

✅ All tests passed!
```

## 迁移指南

### 前端变更

1. **移除外层包装解析**
   ```javascript
   // 之前
   const chatResp = data.chatResp;
   const delta = chatResp.choices[0].delta;
   
   // 现在
   const delta = data.choices[0].delta;
   ```

2. **添加层级结构管理**
   ```javascript
   // 使用 parent_taskid 和 index 构建树形结构
   function buildTree(chunks) {
     const nodes = {};
     const roots = [];
     
     chunks.forEach(chunk => {
       const delta = chunk.choices[0].delta;
       if (delta.role === "task") {
         const { taskid, parent_taskid, index } = delta;
         
         if (!nodes[taskid]) {
           nodes[taskid] = { ...delta, children: [] };
         }
         
         if (parent_taskid) {
           if (!nodes[parent_taskid]) {
             nodes[parent_taskid] = { children: [] };
           }
           nodes[parent_taskid].children.push(nodes[taskid]);
         } else {
           roots.push(nodes[taskid]);
         }
       }
     });
     
     // 按 index 排序
     roots.forEach(root => sortByIndex(root));
     return roots;
   }
   ```

3. **解析 JSON Lines 搜索结果**
   ```javascript
   function parseSearchResults(task_content) {
     return task_content
       .trim()
       .split('\n')
       .filter(line => line)
       .map(line => JSON.parse(line));
   }
   ```

4. **解析 JSON 网页信息**
   ```javascript
   function parseBrowseInfo(task_content) {
     return JSON.parse(task_content);
   }
   ```

### 后端变更

如果您有自定义的中间件或处理逻辑，请注意：

1. 响应格式已从嵌套结构改为扁平结构
2. 所有 `task` 类型消息现在包含 `parent_taskid` 和 `index`
3. `research_htink_block` 已更名为 `research_think_block`
4. 新增了 `research_text_block` 类型

## 兼容性说明

### 向后兼容
- ❌ **不兼容**之前的外层包装格式
- ❌ 字段名称变更（`research_htink_block` → `research_think_block`）
- ❌ 搜索结果格式完全不同

### OpenAI API 兼容
- ✅ 保持标准 OpenAI Chat Completion Chunk 格式
- ✅ 最终回复完全兼容
- ✅ 扩展字段仅在 `role: "task"` 消息中出现

## 性能改进

1. **减少消息数量**：JSON Lines 格式将多个搜索结果合并为更少的消息
2. **更高效的解析**：直接输出 OpenAI 格式，减少了一层序列化/反序列化
3. **更好的流式体验**：通过 `index` 字段支持乱序处理和重排序

## 下一步

- [ ] 前端实现层级结构渲染
- [ ] 添加更多 content_type 支持（如代码执行、图表等）
- [ ] 实现消息缓存和重放功能
- [ ] 优化长内容的分段策略

## 参考文档

- `apps/api-server/边思考边检索.md` - 完整流数据示例
- `apps/api-server/API_FORMAT_V2.md` - 格式说明文档
- `apps/api-server/test_new_format_v2.py` - 测试用例

