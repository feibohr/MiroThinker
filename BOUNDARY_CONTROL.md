# MiroFlow Agent 边界控制机制详解

> 在 ReAct (边搜边思考) 模式下，如何判断是否继续搜索？如何控制循环边界？

---

## 🎯 核心问题

在 Agent 执行过程中，需要解决以下关键问题：
1. **何时停止搜索？** - 避免无限循环
2. **何时生成答案？** - 判断信息是否足够
3. **何时重试？** - 识别错误并恢复
4. **如何防止重复？** - 避免浪费资源

---

## 🔒 七大边界控制机制

### 1. 轮次限制（Max Turns）⭐

**最硬的边界条件**

```python
# 配置示例
max_turns = 20  # 主Agent最多20轮
```

**控制逻辑：**
```python
while turn_count < max_turns and total_attempts < max_attempts:
    turn_count += 1
    total_attempts += 1
    
    # ... 执行LLM调用和工具 ...
    
    if turn_count >= max_turns:
        break  # 强制退出
```

**退出后行为：**
- 触发最终总结流程
- 根据 `context_compress_limit` 决定是否生成失败总结
- 如果是失败，会提取 `failure_experience_summary` 用于重试

**配置位置：**
```yaml
# conf/agent/quick_demo.yaml
main_agent:
  max_turns: 20  # 快速Demo使用20轮

# conf/agent/mirothinker_v1.5_keep5_max200.yaml
main_agent:
  max_turns: 200  # 复杂任务使用200轮
```

**关键代码：**
```python
# src/core/orchestrator.py (line 799-802)
max_turns = self.cfg.agent.main_agent.max_turns
turn_count = 0
total_attempts = 0
max_attempts = max_turns + EXTRA_ATTEMPTS_BUFFER  # 额外200次缓冲
```

---

### 2. 无工具调用检测（No Tool Calls）⭐⭐

**自然停止条件 - LLM主动结束**

当LLM的响应中**不包含任何工具调用**时，框架认为任务已完成。

**检测逻辑：**
```python
# 1. LLM返回响应
assistant_response_text = llm_response.content

# 2. 解析工具调用
tool_calls = parse_llm_response_for_tool_calls(assistant_response_text)

# 3. 检查是否为空
if not tool_calls:
    # 进一步检查：是否是格式错误？
    if any(mcp_tag in assistant_response_text for mcp_tag in mcp_tags):
        # 格式错误 -> 回滚
        rollback()
    elif any(keyword in assistant_response_text for keyword in refusal_keywords):
        # 拒绝回答 -> 回滚
        rollback()
    else:
        # 正常结束 -> 退出循环
        break
```

**LLM如何知道该停止？**

通过系统提示词引导：
```
You accomplish a given task iteratively, breaking it down into 
clear steps and working through them methodically.
```

LLM在以下情况下会停止调用工具：
1. **任务已完成** - 收集到足够信息
2. **已有明确答案** - 在之前的工具结果中找到
3. **无法继续** - 工具无法提供更多帮助

**关键代码：**
```python
# src/core/orchestrator.py (line 867-898)
if not tool_calls:
    (
        should_continue,
        should_break_loop,
        turn_count,
        consecutive_rollbacks,
        message_history,
    ) = await self._handle_response_format_issues(
        assistant_response_text,
        message_history,
        turn_count,
        consecutive_rollbacks,
        total_attempts,
        max_attempts,
        "Main Agent",
    )
    if should_break_loop:
        self.task_log.log_step(
            "info",
            f"Main Agent | Turn: {turn_count} | LLM Call",
            "LLM did not request tool usage, ending process.",
        )
        break
```

---

### 3. 回滚限制（Rollback Limit）⭐⭐

**防止错误无限循环**

当连续发生错误时，限制回滚次数。

```python
MAX_CONSECUTIVE_ROLLBACKS = 5
```

**触发回滚的条件：**
1. **格式错误** - 响应中包含 MCP 标签
2. **重复查询** - 检测到相同的搜索
3. **工具执行错误** - 工具返回特定错误
4. **拒绝回答** - LLM拒绝执行任务

**回滚逻辑：**
```python
if error_detected:
    if consecutive_rollbacks < MAX_CONSECUTIVE_ROLLBACKS - 1:
        message_history.pop()  # 移除最后一条消息
        turn_count -= 1        # 回退轮次
        consecutive_rollbacks += 1
        continue  # 重试
    else:
        # 超过限制，强制退出
        self.task_log.log_step(
            "warning",
            "Agent | Max Rollbacks Reached",
            f"Reached {consecutive_rollbacks} consecutive rollbacks, breaking loop."
        )
        break
```

**成功后重置：**
```python
# 工具执行成功后
if consecutive_rollbacks > 0:
    self.task_log.log_step(
        "info",
        f"Agent | Recovery",
        f"Successfully recovered after {consecutive_rollbacks} consecutive rollbacks"
    )
consecutive_rollbacks = 0  # 重置计数
```

**关键代码：**
```python
# src/core/orchestrator.py (line 206-226)
if consecutive_rollbacks < self.MAX_CONSECUTIVE_ROLLBACKS - 1:
    turn_count -= 1
    consecutive_rollbacks += 1
    message_history.pop()
    return True, False, turn_count, consecutive_rollbacks, message_history
else:
    return False, True, turn_count, consecutive_rollbacks, message_history
```

---

### 4. 上下文长度检测（Context Length）⭐⭐⭐

**防止超出模型上下文窗口**

在每次工具调用后，检查对话历史长度。

**检测逻辑：**
```python
# 1. 估算当前token数
estimated_tokens = (
    last_prompt_tokens +          # 上次LLM调用
    last_completion_tokens +       # 上次LLM输出
    last_user_tokens +             # 最新的用户消息
    summary_tokens +               # 假设要生成总结
    max_tokens +                   # 预留响应空间
    1000                           # 安全缓冲
)

# 2. 与上下文长度限制比较
if estimated_tokens >= max_context_length:
    # 超出限制 -> 回退并触发总结
    message_history.pop()  # 移除最后的用户消息（工具结果）
    message_history.pop()  # 移除倒数第二条助手消息（工具调用）
    turn_count = max_turns  # 设置为最大值，触发总结
    break
```

**Token估算方法：**
```python
def _estimate_tokens(self, text: str) -> int:
    """使用 tiktoken 估算 token 数量"""
    if not hasattr(self, "encoding"):
        self.encoding = tiktoken.get_encoding("o200k_base")
    
    return len(self.encoding.encode(text))
```

**三种应对策略：**

#### 策略A：无上下文管理 (`keep_tool_result = -1`)
- 保留完整历史
- 检测到超长时回退最后一对消息
- 触发总结流程

#### 策略B：保留最近N个 (`keep_tool_result = 5`)
- 只保留最近5个工具结果
- 自动删除旧的工具输出
- 保持系统提示词和基本对话

#### 策略C：周期性压缩 (`context_compress_limit > 0`)
- 每N轮生成一次中间总结
- 压缩历史为简短摘要
- 重新开始新的循环

**关键代码：**
```python
# src/llm/providers/openai_client.py (line 384-444)
def ensure_summary_context(self, message_history: list, summary_prompt: str):
    """检查是否会超出上下文长度"""
    estimated_total = (
        last_prompt_tokens +
        last_completion_tokens +
        last_user_tokens +
        summary_tokens +
        self.max_tokens +
        1000
    )
    
    if estimated_total >= self.max_context_length:
        # 移除最后一对 assistant-user 消息
        if message_history[-1]["role"] == "user":
            message_history.pop()
        if message_history[-1]["role"] == "assistant":
            message_history.pop()
        
        return False, message_history  # 表示需要总结
    
    return True, message_history  # 可以继续
```

---

### 5. 重复查询检测（Duplicate Query）⭐⭐

**避免浪费API调用和时间**

跟踪已执行过的查询，防止重复搜索相同内容。

**查询缓存结构：**
```python
used_queries = {
    "main_google_search": {
        "2026年股市行情": 2,    # 查询过2次
        "明日板块预测": 1,      # 查询过1次
    },
    "main_search_and_browse": {
        "Tesla stock price": 1,
    }
}
```

**查询字符串提取：**
```python
def get_query_str_from_tool_call(tool_name: str, arguments: dict) -> Optional[str]:
    """从工具调用参数中提取查询字符串"""
    
    # Google搜索
    if tool_name in ["google_search", "sogou_search"]:
        return arguments.get("q")  # 返回搜索关键词
    
    # 网页抓取
    elif tool_name == "scrape_website":
        return arguments.get("url")  # 返回URL
    
    # 子Agent调用
    elif tool_name == "search_and_browse":
        return arguments.get("subtask")  # 返回子任务描述
    
    # 其他工具不检测重复
    return None
```

**检测逻辑：**
```python
# 1. 提取查询字符串
query_str = get_query_str_from_tool_call(tool_name, arguments)

if query_str:
    # 2. 检查缓存
    cache_name = f"{agent_name}_{tool_name}"
    count = used_queries[cache_name].get(query_str, 0)
    
    # 3. 判断是否重复
    if count > 0:
        if consecutive_rollbacks < MAX_CONSECUTIVE_ROLLBACKS - 1:
            # 回滚，让LLM尝试不同的查询
            message_history.pop()
            turn_count -= 1
            consecutive_rollbacks += 1
            log("Duplicate query detected, rolling back")
            continue
        else:
            # 回滚次数用尽，允许重复查询
            log("Allowing duplicate query after max rollbacks")
    
    # 4. 执行工具后更新计数
    execute_tool(...)
    used_queries[cache_name][query_str] += 1
```

**为什么有时允许重复？**
- 回滚次数达到上限时
- 避免因重复检测导致死循环
- 有时需要重新验证信息

**关键代码：**
```python
# src/core/orchestrator.py (line 257-316)
async def _check_duplicate_query(self, tool_name, arguments, cache_name, ...):
    query_str = self.tool_executor.get_query_str_from_tool_call(
        tool_name, arguments
    )
    
    if not query_str:
        return False, False, turn_count, consecutive_rollbacks, message_history
    
    self.used_queries.setdefault(cache_name, defaultdict(int))
    count = self.used_queries[cache_name][query_str]
    
    if count > 0:
        if consecutive_rollbacks < self.MAX_CONSECUTIVE_ROLLBACKS - 1:
            message_history.pop()
            turn_count -= 1
            consecutive_rollbacks += 1
            return True, True, turn_count, consecutive_rollbacks, message_history
    
    return False, False, turn_count, consecutive_rollbacks, message_history
```

---

### 6. 拒绝关键词检测（Refusal Keywords）⭐

**识别LLM拒绝执行**

当LLM明确表示无法完成任务时，触发回滚。

**检测关键词：**
```python
refusal_keywords = [
    "time constraint",           # 时间限制
    "I'm sorry, but I can't",   # 礼貌拒绝
    "I'm sorry, I cannot solve", # 明确无法解决
]
```

**检测逻辑：**
```python
if any(keyword in assistant_response_text for keyword in refusal_keywords):
    matched_keywords = [
        kw for kw in refusal_keywords if kw in assistant_response_text
    ]
    
    if consecutive_rollbacks < MAX_CONSECUTIVE_ROLLBACKS - 1:
        message_history.pop()
        turn_count -= 1
        consecutive_rollbacks += 1
        log(f"LLM refused: {matched_keywords}, rolling back")
        continue
    else:
        log(f"Max rollbacks reached with refusals: {matched_keywords}")
        break
```

**为什么要回滚？**
- LLM可能误判任务难度
- 给LLM重新尝试的机会
- 调整对话上下文可能改变结果

**关键代码：**
```python
# src/utils/prompt_utils.py (line 78-82)
refusal_keywords = [
    "time constraint",
    "I'm sorry, but I can't",
    "I'm sorry, I cannot solve",
]

# src/core/orchestrator.py (line 228-252)
if any(keyword in assistant_response_text for keyword in refusal_keywords):
    matched_keywords = [kw for kw in refusal_keywords 
                       if kw in assistant_response_text]
    if consecutive_rollbacks < self.MAX_CONSECUTIVE_ROLLBACKS - 1:
        turn_count -= 1
        consecutive_rollbacks += 1
        message_history.pop()
        return True, False, turn_count, consecutive_rollbacks, message_history
```

---

### 7. 格式错误检测（Format Error）⭐

**检测MCP标签泄露**

LLM有时会在不应该出现的地方输出MCP标签。

**检测标签：**
```python
mcp_tags = [
    "<use_mcp_tool>",
    "</use_mcp_tool>",
    "<server_name>",
    "</server_name>",
    "<arguments>",
    "</arguments>",
]
```

**检测场景：**

#### 场景1：最终总结中出现工具调用
```python
# 在总结阶段，LLM不应该调用工具
summary_prompt = """
... 
You must absolutely not perform any MCP tool call...
"""

# 但LLM可能误解，输出了：
"""
根据搜索结果，答案是...

<use_mcp_tool>
<server_name>tool-google-search</server_name>
...  # ← 这是错误！
</use_mcp_tool>
"""
```

#### 场景2：无工具调用但包含标签
```python
# LLM想结束，但格式错误
"""
任务已完成，答案是42。

但我还想说明一下使用了 <use_mcp_tool> 这个功能...  # ← 错误
"""
```

**检测和处理：**
```python
if not tool_calls:  # 没有解析到工具调用
    # 但响应中包含MCP标签
    if any(mcp_tag in assistant_response_text for mcp_tag in mcp_tags):
        if consecutive_rollbacks < MAX_CONSECUTIVE_ROLLBACKS - 1:
            message_history.pop()
            turn_count -= 1
            consecutive_rollbacks += 1
            log("Format error: MCP tags found, rolling back")
            continue
        else:
            log("Max rollbacks reached with format errors")
            break
```

**关键代码：**
```python
# src/utils/prompt_utils.py (line 69-76)
mcp_tags = [
    "<use_mcp_tool>",
    "</use_mcp_tool>",
    "<server_name>",
    "</server_name>",
    "<arguments>",
    "</arguments>",
]

# src/core/orchestrator.py (line 205-226)
if any(mcp_tag in assistant_response_text for mcp_tag in mcp_tags):
    if consecutive_rollbacks < self.MAX_CONSECUTIVE_ROLLBACKS - 1:
        turn_count -= 1
        consecutive_rollbacks += 1
        message_history.pop()
        return True, False, turn_count, consecutive_rollbacks, message_history
```

---

## 📊 边界控制流程图

```
开始任务
  │
  ├─→ turn_count < max_turns? ──否──→ [退出] 生成最终总结
  │          │
  │         是
  │          ↓
  ├─→ consecutive_rollbacks < 5? ──否──→ [退出] 过多错误
  │          │
  │         是
  │          ↓
  ├─→ LLM调用 + 工具解析
  │          │
  │          ↓
  ├─→ 有工具调用? ──否──→ 检查格式/拒绝 ──有问题──→ 回滚
  │          │                    │
  │         是                    无问题
  │          │                    │
  │          ↓                    ↓
  ├─→ 检查重复查询? ──是──→ 回滚    [退出] 正常结束
  │          │
  │         否
  │          ↓
  ├─→ 执行工具
  │          │
  │          ↓
  ├─→ 工具成功? ──否──→ 回滚
  │          │
  │         是
  │          ↓
  ├─→ 更新对话历史
  │          │
  │          ↓
  ├─→ 上下文超长? ──是──→ [退出] 回退并总结
  │          │
  │         否
  │          │
  └──────────┘ 继续循环
```

---

## 🎮 实际运行示例

### 示例1：正常完成（最理想）

```
Turn 1: LLM → google_search("2026年股市")
Turn 2: LLM → scrape_website("https://finance.example.com")
Turn 3: LLM → execute_python("分析数据...")
Turn 4: LLM → [无工具调用] "根据分析，答案是..."
        ↓
     [退出] 正常结束 (4轮完成)
```

### 示例2：达到轮次上限

```
Turn 1-19: 各种搜索和分析...
Turn 20: LLM → google_search("更多信息")
        ↓
     turn_count >= max_turns (20)
        ↓
     [退出] 强制总结 (可能生成failure_summary)
```

### 示例3：重复查询被阻止

```
Turn 1: google_search("2026年股市") ✓
Turn 2: scrape_website(...) ✓
Turn 3: google_search("2026年股市") ← 重复！
        ↓
     检测到重复 → 回滚
        ↓
Turn 3 (重试): google_search("明日板块预测") ✓
```

### 示例4：连续错误后放弃

```
Turn 1: 格式错误 → 回滚 (rollback 1/5)
Turn 2: 格式错误 → 回滚 (rollback 2/5)
Turn 3: 重复查询 → 回滚 (rollback 3/5)
Turn 4: 工具失败 → 回滚 (rollback 4/5)
Turn 5: 格式错误 → 回滚 (rollback 5/5)
Turn 6: 任何错误 → [退出] 达到回滚上限
```

### 示例5：上下文超长

```
Turn 1-15: 大量搜索和抓取，累积了很多内容
Turn 16: execute_python(长代码) → 大量输出
        ↓
     estimated_tokens = 195,000 (接近200K限制)
        ↓
     上下文检查失败 → 回退最后一对消息
        ↓
     [退出] 触发总结 (设置 turn_count = max_turns)
```

---

## ⚙️ 配置建议

### 快速任务（Demo/测试）
```yaml
main_agent:
  max_turns: 10-20
  tools: [tool-google-search, tool-python]
```
- 轮次少，快速结束
- 工具少，减少复杂度

### 中等任务（常规问题）
```yaml
main_agent:
  max_turns: 50-100
  tools: [tool-google-search, tool-python, tool-vqa]
keep_tool_result: 5
```
- 适中的轮次
- 保留最近5个工具结果

### 复杂任务（Research/Benchmark）
```yaml
main_agent:
  max_turns: 200-600
  tools: [所有工具]
keep_tool_result: 5
context_compress_limit: 50
```
- 大轮次支持深度探索
- 上下文管理防止超长
- 周期性压缩

---

## 🔍 调试技巧

### 如何知道为什么停止？

查看日志：
```bash
grep "Main Agent | Turn:" logs/debug/main.log

# 可能的输出：
"Main Agent | Turn: 15 | LLM Call: LLM did not request tool usage, ending process."  # 正常结束
"Main Agent | Max Turns Reached"  # 达到上限
"Main Agent | Too Many Rollbacks"  # 错误过多
"Main Agent | Context Limit Reached"  # 上下文超长
```

### 如何调整边界？

1. **增加探索深度** → 提高 `max_turns`
2. **减少内存占用** → 设置 `keep_tool_result`
3. **支持超长任务** → 启用 `context_compress_limit`
4. **降低错误容忍** → 减少 `MAX_CONSECUTIVE_ROLLBACKS`

---

## 💡 设计哲学

### 为什么需要多层边界？

1. **硬边界（max_turns）** - 防止无限循环
2. **软边界（无工具调用）** - 允许提前结束
3. **错误边界（回滚限制）** - 防止错误传播
4. **资源边界（上下文长度）** - 防止超出物理限制
5. **效率边界（重复检测）** - 避免浪费

### 灵活性 vs 确定性

- **灵活** - LLM可以自主决定何时停止
- **确定** - 硬性限制保证一定会结束
- **平衡** - 多层机制互相补充

### 从失败中学习

```python
if reached_max_turns and context_management_enabled:
    # 生成失败总结
    failure_summary = generate_failure_summary(...)
    # 下次重试时注入这个经验
    # 避免重复相同的错误路径
```

---

## 📚 相关文件

| 文件 | 关键函数/变量 |
|------|---------------|
| `orchestrator.py` | `run_main_agent()`, `_check_duplicate_query()` |
| `answer_generator.py` | `generate_and_finalize_answer()` |
| `openai_client.py` | `ensure_summary_context()` |
| `prompt_utils.py` | `mcp_tags`, `refusal_keywords` |
| `tool_executor.py` | `get_query_str_from_tool_call()` |

---

**总结：** MiroFlow通过七层边界控制机制，实现了灵活而稳定的"边搜边思考"模式，既允许LLM自主决策，又确保不会失控。

