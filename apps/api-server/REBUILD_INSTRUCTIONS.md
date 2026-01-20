# 完整重新构建指南

## 🎯 三个问题的修复总结

### 问题1: ✅ research_process_block 标题
**状态**: 已修复并验证通过  
**显示**: "正在收集和分析资料"

### 问题2: ⚠️ 搜索关键词块
**状态**: 代码已修复但需要重新构建
- 关键词提取成功（日志显示: "AI 是什么 定义"）
- 但 `research_web_search_keyword` 块没有输出
- **需要重新构建镜像**

### 问题3: ✅ 思考内容和最终正文
**状态**: 已修复并验证通过
- `<think>` 标签内容正确转换为 `research_think_block`
- 最终正文在 `research_completed` 之后输出为 `role="assistant"`

---

## 📦 重新构建步骤

### 方法1: 完整重新构建（推荐）

```bash
cd /Users/feibohr/Documents/workspace/git/python/MiroThinker

# 停止容器
docker compose down

# 清理旧镜像
docker rmi mirothinker-api-server

# 无缓存重新构建
docker compose build --no-cache api-server

# 启动服务
docker compose up -d api-server

# 等待启动
sleep 30

# 测试
curl -X POST http://localhost:8000/v2/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"mirothinker","messages":[{"role":"user","content":"什么是人工智能"}],"stream":true}' \
  --no-buffer | head -100
```

### 方法2: 快速重新构建

```bash
cd /Users/feibohr/Documents/workspace/git/python/MiroThinker

# 重新构建并启动
docker compose up -d --build api-server

# 等待启动
sleep 30
```

---

## ✅ 验证检查清单

### 1. research_process_block
```bash
curl ... | grep "research_process_block" | grep "message_start"
# 应该包含: "正在收集和分析资料"
```

### 2. research_web_search_keyword
```bash
curl ... | grep "research_web_search_keyword"  
# 应该包含: "搜索：xxx"
```

### 3. research_web_search
```bash
curl ... | grep "research_web_search\"" | grep "message_start"
# 应该包含: "根据用户需求搜索到相关网页：x个"
```

### 4. research_think_block
```bash
curl ... | grep "research_think_block"
# <think> 内容应该在这里，不在 role="assistant" 中
```

### 5. research_completed
```bash
curl ... | grep "research_completed"
# 应该包含: "已收集充分的信息，即将开始回复"
```

### 6. 最终正文
```bash
curl ... | grep '"role":"assistant"' | grep "content"
# 应该在 research_completed 之后
# 不应该包含 <think> 标签
```

---

## 🐛 如果仍有问题

### 问题: research_web_search_keyword 不显示

**原因**: 关键词提取失败  
**解决**: 
1. 检查 `tool_input` 的实际结构
2. 可能需要修改 `_handle_search_tool` 中的关键词提取逻辑

**临时解决方案**: 
修改 `openai_adapter_v2.py` 的第 511-534 行，强制从 `q` 字段提取：

```python
# Extract search keyword from various possible locations
keyword = ""
if isinstance(tool_input, dict):
    # Priority order for keyword extraction
    keyword = (
        tool_input.get("keyword") or 
        tool_input.get("query") or 
        tool_input.get("q") or 
        ""
    )
    
    # If still no keyword, try from nested result
    if not keyword and "result" in tool_input:
        try:
            result_dict = json.loads(tool_input["result"]) if isinstance(tool_input["result"], str) else tool_input["result"]
            keyword = result_dict.get("searchParameters", {}).get("q", "")
        except:
            pass

logger.info(f"Search tool - keyword: '{keyword}', tool_input keys: {list(tool_input.keys())}")

# Only generate keyword block if we have a keyword
if keyword:
    # ... generate research_web_search_keyword blocks
```

---

## 📝 已修改的关键文件

1. **`services/openai_adapter_v2.py`** (主要)
   - `_handle_start_of_agent()` - 添加 process_block 标题
   - `_handle_search_tool()` - 添加 keyword 块，修改关键词提取
   - `_convert_tool_call()` - 区分 `<think>` 和最终答案

2. **`routers/chat.py`** (次要)
   - `_stream_chat_completion_v2()` - 添加 `<think>` 过滤逻辑

3. **`services/openai_adapter.py`** (V1保持简单)
   - 恢复为标准 OpenAI 格式

---

## 🎯 预期完整流程

```
1. research_process_block (message_start) - "正在收集和分析资料"
2. research_process_block (message_process)
3. research_think_block (message_start) - "思考过程"
4. research_think_block (message_process) - <think>内容</think>
5. research_think_block (message_result)
6. research_web_search_keyword (message_start) - "搜索：人工智能"
7. research_web_search_keyword (message_process)
8. research_web_search_keyword (message_result)
9. research_web_search (message_start) - "根据用户需求搜索到相关网页：10个"
10. research_web_search (message_process) - JSON Lines 搜索结果
11. research_web_search (message_result)
12. ... (可能有更多搜索和思考)
13. research_completed (message_start) - "已收集充分的信息，即将开始回复"
14. research_completed (message_process)
15. research_completed (message_result)
16. research_process_block (message_result) - 根块完成
17. role="assistant" - 最终正文（无 <think> 标签）
18. [DONE]
```

---

**建议**: 现在就执行"方法1: 完整重新构建"以确保所有修改生效！

