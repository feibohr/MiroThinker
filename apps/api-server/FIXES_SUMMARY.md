# V2 API 修复总结

## 📋 修复的问题

### 1. ✅ research_process_block 添加标题
**问题**: research_process_block 的 task_content 为空，没有显示标题

**修复**: 在 `_handle_start_of_agent` 方法中，为 research_process_block 的 message_start 添加标题

**代码变更**:
```python
# 修复前
task_content=""

# 修复后
task_content=json.dumps({"label": "正在收集和分析资料"})
```

**效果**:
```json
{
  "content_type": "research_process_block",
  "taskstat": "message_start",
  "task_content": "{\"label\": \"正在收集和分析资料\"}"
}
```

---

### 2. ✅ research_web_search 标题改为包含搜索关键词
**问题**: 搜索标题固定为"搜索完成，共{count}个匹配项"，没有显示搜索关键词

**修复**: 
1. 新增 `research_web_search_keyword` 组件显示"搜索：xxx"
2. 修改 `research_web_search` 标题为"根据用户需求搜索到相关网页：x个"

**代码变更**:
```python
# 1. 添加关键词块
if keyword:
    chunks.append(self.create_task_chunk(
        content_type="research_web_search_keyword",
        task_content=json.dumps({"label": f"搜索：{keyword}", "keyword": keyword}),
        ...
    ))

# 2. 修改搜索结果块标题
chunks.append(self.create_task_chunk(
    content_type="research_web_search",
    task_content=json.dumps({
        "label": f"根据用户需求搜索到相关网页：{len(organic)}个", 
        "count": len(organic)
    }),
    ...
))
```

**效果**:
```json
// 关键词块
{
  "content_type": "research_web_search_keyword",
  "task_content": "{\"label\": \"搜索：人工智能\", \"keyword\": \"人工智能\"}"
}

// 搜索结果块
{
  "content_type": "research_web_search",
  "task_content": "{\"label\": \"根据用户需求搜索到相关网页：5个\", \"count\": 5}"
}
```

---

### 3. ✅ 第二轮思考保持 research_think_block
**问题**: 工具调用后（如搜索后），新的思考内容 role 变成了 assistant，应该还是 research_think_block

**修复**: 在工具调用前关闭当前的 thinking 块，后续 message 事件会自动创建新的 research_think_block

**代码变更**:
```python
def _handle_search_tool(...):
    # 关闭当前的 thinking 块
    if "thinking" in self.current_task_blocks:
        think_block = self.current_task_blocks.pop("thinking")
        chunks.append(self.create_task_chunk(
            taskstat="message_result",
            content_type="research_think_block",
            taskid=think_block["taskid"],
            ...
        ))
    # 然后处理搜索...

def _handle_scrape_tool(...):
    # 同样关闭 thinking 块
    ...
```

**效果**:
```
1. 第一轮思考 → research_think_block (role=task)
2. 搜索工具 → 关闭第一个 thinking 块
3. 第二轮思考 → 新的 research_think_block (role=task) ✅
```

---

## 🧪 测试验证

### 运行测试
```bash
cd apps/api-server
python3 test_fixes.py
```

### 测试结果
```
✅ 修复1 (research_process_block 标题): 通过
✅ 修复2 (search 关键词): 通过
✅ 修复3 (thinking 块连续性): 通过
```

---

## 📊 完整流程示例

### 修复后的流程
```
1. research_process_block (message_start)
   ├─ task_content: {"label": "正在收集和分析资料"}
   
2. research_think_block (message_start)
   ├─ task_content: {"label": "思考过程"}
   
3. research_think_block (message_process)
   ├─ task_content: "我需要了解人工智能..."
   
4. research_think_block (message_result)
   ├─ 关闭第一个思考块
   
5. research_web_search_keyword (message_start)
   ├─ task_content: {"label": "搜索：人工智能", "keyword": "人工智能"}
   
6. research_web_search (message_start)
   ├─ task_content: {"label": "根据用户需求搜索到相关网页：5个", "count": 5}
   
7. research_web_search (message_process)
   ├─ task_content: JSON Lines 格式的搜索结果
   
8. research_think_block (message_start)  ← 第二轮思考（新块）
   ├─ task_content: {"label": "思考过程"}
   
9. research_think_block (message_process)
   ├─ task_content: "根据搜索结果分析..."
   
10. 最终回复 (role=assistant)
    ├─ content: "人工智能是..."
```

---

## 🔧 涉及的文件

- **修改**: `apps/api-server/services/openai_adapter_v2.py`
  - `_handle_start_of_agent()` - 添加 process_block 标题
  - `_handle_search_tool()` - 添加关键词块，修改搜索结果标题
  - `_handle_scrape_tool()` - 关闭 thinking 块

- **测试**: `apps/api-server/test_fixes.py`
  - 验证三个修复点

---

## 🚀 部署更新

### 本地测试
```bash
cd apps/api-server
python3 test_fixes.py
```

### 更新到 Docker 容器
```bash
# 复制文件到容器
docker cp apps/api-server/services/openai_adapter_v2.py mirothinker-api:/app/apps/api-server/services/openai_adapter_v2.py

# 重启容器
docker restart mirothinker-api

# 测试 API
curl -X POST http://localhost:8000/v2/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"mirothinker","messages":[{"role":"user","content":"介绍人工智能"}],"stream":true}'
```

### 重新构建镜像
```bash
cd /Users/feibohr/Documents/workspace/git/python/MiroThinker
docker compose build --no-cache api-server
docker compose up -d api-server
```

---

## ✅ 验证清单

- [x] research_process_block 显示"正在收集和分析资料"
- [x] 搜索时显示"搜索：xxx"（research_web_search_keyword）
- [x] 搜索结果显示"根据用户需求搜索到相关网页：x个"
- [x] 第二轮思考仍使用 research_think_block（role=task）
- [x] 单元测试通过
- [x] Docker 容器测试通过

---

**更新日期**: 2026-01-19  
**修复版本**: V2 API (OpenAIAdapterV2)

