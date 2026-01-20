# MiroFlow Agent 框架深度分析

## 📚 目录
1. [框架总体架构](#框架总体架构)
2. [核心执行流程](#核心执行流程)
3. [关键组件解析](#关键组件解析)
4. [系统提示词完整列表](#系统提示词完整列表)
5. [核心设计思路](#核心设计思路)

---

## 🏗️ 框架总体架构

MiroFlow Agent 是一个基于 **ReAct (Reasoning + Acting)** 范式的多智能体框架，通过 **MCP (Model Context Protocol)** 协议集成各种工具。

### 架构层次

```
┌─────────────────────────────────────────────────────────┐
│                     main.py (入口)                       │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────▼───────────┐
         │   Pipeline (管道层)    │
         │  - 组件初始化          │
         │  - 任务日志管理        │
         │  - 异常处理            │
         └───────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │ Orchestrator (编排层)  │
         │  - 主Agent循环         │
         │  - 子Agent调度         │
         │  - 上下文管理          │
         └───────────┬───────────┘
                     │
    ┌────────────────┼────────────────┐
    │                │                │
┌───▼───┐    ┌──────▼──────┐   ┌────▼─────┐
│ LLM   │    │ Tool        │   │ Answer   │
│Client │    │ Executor    │   │Generator │
└───────┘    └─────────────┘   └──────────┘
```

---

## 🔄 核心执行流程

### 1. 初始化阶段（Pipeline）

```python
# main.py 入口
main(cfg: DictConfig)
  ↓
amain(cfg: DictConfig)  # 异步主函数
  ↓
create_pipeline_components(cfg)  # 创建核心组件
  ├── ToolManager (主Agent工具管理器)
  ├── ToolManager (子Agent工具管理器们)
  └── OutputFormatter (输出格式化器)
  ↓
execute_task_pipeline(...)  # 执行任务管道
```

**关键步骤：**
1. **加载配置** - Hydra配置系统（LLM配置 + Agent配置 + Benchmark配置）
2. **初始化工具管理器** - 基于MCP协议连接各种工具服务器
3. **创建TaskLog** - 记录完整的执行轨迹
4. **初始化LLM Client** - 支持OpenAI/Anthropic等多种Provider
5. **创建Orchestrator** - 核心编排器

### 2. 主Agent执行循环（Orchestrator.run_main_agent）

```python
while turn_count < max_turns:
    ┌─────────────────────────────────────┐
    │  1. LLM Call (生成推理和工具调用)     │
    └─────────────────┬───────────────────┘
                      │
    ┌─────────────────▼───────────────────┐
    │  2. 解析响应                         │
    │  - 提取文本                          │
    │  - 提取工具调用                      │
    │  - 提取boxed答案（如果有）           │
    └─────────────────┬───────────────────┘
                      │
    ┌─────────────────▼───────────────────┐
    │  3. 检查退出条件                     │
    │  - 无工具调用？                      │
    │  - 格式错误？                        │
    │  - 拒绝关键词？                      │
    └─────────────────┬───────────────────┘
                      │ 否，继续
    ┌─────────────────▼───────────────────┐
    │  4. 执行工具调用                     │
    │  - 检查重复查询                      │
    │  - 调用工具                          │
    │  - 后处理结果                        │
    │  - 错误回滚机制                      │
    └─────────────────┬───────────────────┘
                      │
    ┌─────────────────▼───────────────────┐
    │  5. 更新对话历史                     │
    │  - 添加工具结果到消息历史            │
    │  - 检查上下文长度                    │
    └─────────────────┬───────────────────┘
                      │
                      └─── 循环继续
```

**关键机制：**

#### a) 回滚机制（Rollback）
当遇到以下情况时触发：
- 工具调用格式错误（包含MCP标签）
- LLM拒绝回答（refusal keywords）
- 重复查询检测
- 工具执行错误

```python
if error_condition:
    message_history.pop()  # 移除最后一条消息
    turn_count -= 1        # 回退轮次
    consecutive_rollbacks += 1  # 增加连续回滚计数
    
    if consecutive_rollbacks >= MAX_CONSECUTIVE_ROLLBACKS:
        break  # 防止无限循环
```

#### b) 重复查询检测
```python
used_queries = {
    "cache_name": {
        "query_string": count
    }
}

# 检测到重复查询时回滚
if query_str in used_queries[cache_name]:
    rollback()
```

#### c) 上下文管理
```python
# 检查是否会超出上下文长度
if estimated_tokens >= max_context_length:
    # 移除最后一对 assistant-user 消息
    message_history.pop()  # user message
    message_history.pop()  # assistant message
    trigger_summary = True
```

### 3. 子Agent执行（Orchestrator.run_sub_agent）

当主Agent调用子Agent时（如 `agent-browsing`）：

```python
run_sub_agent(sub_agent_name, task_description)
  ↓
1. 生成子Agent特定的system prompt
  ↓
2. 独立的消息历史
  ↓
3. 独立的工具管理器
  ↓
4. 独立的执行循环（与主Agent类似）
  ↓
5. 生成子Agent的总结
  ↓
6. 返回结果给主Agent
```

### 4. 最终答案生成（AnswerGenerator）

```python
generate_and_finalize_answer(...)
  ↓
┌─── 策略1: 标准流程（context_compress_limit = 0）
│    ├── 生成summarize prompt
│    ├── 调用LLM生成最终答案
│    └── 提取\\boxed{}内容
│
├─── 策略2: 失败总结流程（达到max_turns）
│    ├── 生成failure summary prompt
│    ├── LLM分析失败原因
│    ├── 提取有用发现
│    └── 返回给上层用于重试
│
└─── 策略3: 上下文压缩流程（context_compress_limit > 0）
     ├── 每N轮压缩一次历史
     ├── 保留最近的工具结果
     └── 重新开始循环
```

---

## 🔧 关键组件解析

### 1. Pipeline（pipeline.py）
**职责：** 任务生命周期管理
- 组件创建和初始化
- 任务日志系统
- 异常捕获和错误处理
- 最终结果返回

### 2. Orchestrator（orchestrator.py）
**职责：** 核心执行编排
- **主要功能：**
  - Agent执行循环
  - 工具调用调度
  - 子Agent管理
  - 上下文管理
  - 流式输出处理

- **核心状态管理：**
```python
- turn_count: 当前轮次
- total_attempts: 总尝试次数
- consecutive_rollbacks: 连续回滚计数
- used_queries: 查询去重缓存
- intermediate_boxed_answers: 中间答案收集
```

### 3. LLM Client（llm/providers/）
**职责：** LLM API交互
- **支持的Provider：**
  - OpenAI (openai_client.py)
  - Anthropic (anthropic_client.py)
  
- **核心功能：**
  - 消息创建和发送
  - Token使用追踪
  - 响应解析
  - 重试机制（10次重试，指数退避）
  - 上下文长度管理

### 4. ToolManager（来自miroflow-tools包）
**职责：** MCP工具管理
- **功能：**
  - MCP服务器连接
  - 工具定义获取
  - 工具调用执行
  - 黑名单管理

### 5. ToolExecutor（tool_executor.py）
**职责：** 工具执行辅助
- 参数修正（fix_tool_call_arguments）
- 查询字符串提取
- 重复检测
- 结果后处理
- 错误判断

### 6. AnswerGenerator（answer_generator.py）
**职责：** 答案生成和重试
- LLM调用封装
- 失败总结生成
- 最终答案生成
- 多次重试机制
- 上下文压缩策略

### 7. OutputFormatter（io/output_formatter.py）
**职责：** 输出格式化
- 工具结果格式化
- \\boxed{}内容提取
- 最终总结生成

---

## 📝 系统提示词完整列表

### 1. MCP工具使用提示词（核心）

**来源：** `prompt_utils.py → generate_mcp_system_prompt()`

```python
"""In this environment you have access to a set of tools you can use to answer the user's question. 

You only have access to the tools provided below. You can only use one tool per message, and will receive the result of that tool in the user's next response. You use tools step-by-step to accomplish a given task, with each tool-use informed by the result of the previous tool-use. Today is: {formatted_date}

# Tool-Use Formatting Instructions 

Tool-use is formatted using XML-style tags. The tool-use is enclosed in <use_mcp_tool></use_mcp_tool> and each parameter is similarly enclosed within its own set of tags.

The Model Context Protocol (MCP) connects to servers that provide additional tools and resources to extend your capabilities. You can use the server's tools via the `use_mcp_tool`.

Description: 
Request to use a tool provided by a MCP server. Each MCP server can provide multiple tools with different capabilities. Tools have defined input schemas that specify required and optional parameters.

Parameters:
- server_name: (required) The name of the MCP server providing the tool
- tool_name: (required) The name of the tool to execute
- arguments: (required) A JSON object containing the tool's input parameters, following the tool's input schema, quotes within string must be properly escaped, ensure it's valid JSON

Usage:
<use_mcp_tool>
<server_name>server name here</server_name>
<tool_name>tool name here</tool_name>
<arguments>
{
"param1": "value1",
"param2": "value2 \\"escaped string\\""
}
</arguments>
</use_mcp_tool>

Important Notes:
- Tool-use must be placed **at the end** of your response, **top-level**, and not nested within other tags.
- Always adhere to this format for the tool use to ensure proper parsing and execution.

String and scalar parameters should be specified as is, while lists and objects should use JSON format. Note that spaces for string values are not stripped. The output is not expected to be valid XML and is parsed with regular expressions.

Here are the functions available in JSONSchema format:

[工具定义会被动态插入到这里]

# General Objective

You accomplish a given task iteratively, breaking it down into clear steps and working through them methodically.
"""
```

**作用：**
- 定义MCP工具调用的XML格式
- 列出所有可用工具及其schema
- 设定迭代式任务解决的基本框架

---

### 2. Agent特定目标提示词

**来源：** `prompt_utils.py → generate_agent_specific_system_prompt()`

#### a) 主Agent提示词 (agent_type="main")

```python
"""
# Agent Specific Objective

You are a task-solving agent that uses tools step-by-step to answer the user's question. Your goal is to provide complete, accurate and well-reasoned answers using additional tools.
"""
```

**核心要求：**
- 逐步使用工具
- 提供完整、准确的答案
- 基于工具辅助推理

#### b) 浏览Agent提示词 (agent_type="agent-browsing")

```python
"""# Agent Specific Objective

You are an agent that performs the task of searching and browsing the web for specific information and generating the desired answer. Your task is to retrieve reliable, factual, and verifiable information that fills in knowledge gaps.
Do not infer, speculate, summarize broadly, or attempt to fill in missing parts yourself. Only return factual content.
"""
```

**核心要求：**
- 专注于搜索和浏览
- 只返回事实性内容
- 不推测、不总结

---

### 3. 最终总结提示词

**来源：** `prompt_utils.py → generate_agent_summarize_prompt()`

#### a) 主Agent总结提示词 (agent_type="main")

```python
"""Summarize the above conversation, and output the FINAL ANSWER to the original question.

If a clear answer has already been provided earlier in the conversation, do not rethink or recalculate it — simply extract that answer and reformat it to match the required format below.
If a definitive answer could not be determined, make a well-informed educated guess based on the conversation.

The original question is repeated here for reference:

"{task_description}"

Wrap your final answer in \\boxed{}.
Your final answer should be:
- a number, OR
- as few words as possible, OR
- a comma-separated list of numbers and/or strings.

ADDITIONALLY, your final answer MUST strictly follow any formatting instructions in the original question — such as alphabetization, sequencing, units, rounding, decimal places, etc.
If you are asked for a number, express it numerically (i.e., with digits rather than words), don't use commas, and DO NOT INCLUDE UNITS such as $ or USD or percent signs unless specified otherwise.
If you are asked for a string, don't use articles or abbreviations (e.g. for cities), unless specified otherwise. Don't output any final sentence punctuation such as '.', '!', or '?'.
If you are asked for a comma-separated list, apply the above rules depending on whether the elements are numbers or strings.
Do NOT include any punctuation such as '.', '!', or '?' at the end of the answer.
Do NOT include any invisible or non-printable characters in the answer output.

You must absolutely not perform any MCP tool call, tool invocation, search, scrape, code execution, or similar actions.
You can only answer the original question based on the information already retrieved and your own internal knowledge.
If you attempt to call any tool, it will be considered a mistake."""
```

**核心要求：**
- 必须使用 \\boxed{} 包装答案
- 严格遵守格式要求（数字/字符串/列表）
- 禁止调用任何工具
- 不包含标点符号

#### b) 浏览Agent总结提示词 (agent_type="agent-browsing")

```python
"""This is a direct instruction to you (the assistant), not the result of a tool call.

We are now ending this session, and your conversation history will be deleted. You must NOT initiate any further tool use. This is your final opportunity to report *all* of the information gathered during the session.

The original task is repeated here for reference:

"{task_description}"

Summarize the above search and browsing history. Output the FINAL RESPONSE and detailed supporting information of the task given to you.

If you found any useful facts, data, quotes, or answers directly relevant to the original task, include them clearly and completely.
If you reached a conclusion or answer, include it as part of the response.
If the task could not be fully answered, do NOT make up any content. Instead, return all partially relevant findings, Search results, quotes, and observations that might help a downstream agent solve the problem.
If partial, conflicting, or inconclusive information was found, clearly indicate this in your response.

Your final response should be a clear, complete, and structured report.
Organize the content into logical sections with appropriate headings.
Do NOT include any tool call instructions, speculative filler, or vague summaries.
Focus on factual, specific, and well-organized information."""
```

**核心要求：**
- 报告所有收集到的信息
- 结构化组织内容
- 明确标注不完整/冲突的信息
- 不编造内容

---

### 4. 失败总结提示词（重试机制）

**来源：** `prompt_utils.py` 失败经验模板

#### a) 失败总结Prompt

```python
FAILURE_SUMMARY_PROMPT = """The task was not completed successfully. Do NOT call any tools. Provide a summary:

Failure type: [incomplete / blocked / misdirected / format_missed]
  - incomplete: ran out of turns before finishing
  - blocked: got stuck due to tool failure or missing information
  - misdirected: went down the wrong path
  - format_missed: found the answer but forgot to use \\boxed{}
What happened: [describe the approach taken and why a final answer was not reached]
Useful findings: [list any facts, intermediate results, or conclusions discovered that should be reused]"""
```

#### b) 失败经验注入格式

```python
FAILURE_EXPERIENCE_HEADER = """

=== Previous Attempts Analysis ===
The following summarizes what was tried before and why it didn't work. Use this to guide a NEW approach.

"""

FAILURE_EXPERIENCE_ITEM = """[Attempt {attempt_number}]
{failure_summary}

"""

FAILURE_EXPERIENCE_FOOTER = """=== End of Analysis ===

Based on the above, you should try a different strategy this time.
"""
```

**作用：**
- 分析失败原因
- 提取有用发现
- 指导下一次尝试采用不同策略

---

### 5. 辅助提示内容

#### a) 格式错误提示
```python
FORMAT_ERROR_MESSAGE = "No \\boxed{} content found in the final answer."
```

#### b) MCP标签检测
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

#### c) 拒绝关键词检测
```python
refusal_keywords = [
    "time constraint",
    "I'm sorry, but I can't",
    "I'm sorry, I cannot solve",
]
```

---

## 💡 核心设计思路

### 1. ReAct范式实现
- **Reasoning**: LLM在每次调用时进行思考和推理
- **Acting**: 通过MCP工具执行具体操作
- **Observation**: 获取工具结果并更新理解

### 2. MCP工具集成设计
**优势：**
- 标准化工具接口
- 动态工具加载
- 工具黑名单机制
- 多服务器支持

**架构：**
```
ToolManager
  ├── MCP Server 1 (e.g., tool-google-search)
  │   ├── google_search
  │   └── scrape_website
  ├── MCP Server 2 (e.g., tool-python)
  │   ├── execute_python_code
  │   ├── install_package
  │   └── ...
  └── MCP Server 3 (e.g., tool-vqa)
      └── analyze_image
```

### 3. 多层回滚机制
**目的：** 提高鲁棒性，避免无效循环

**触发条件：**
1. 格式错误（MCP标签泄露）
2. 重复查询
3. 工具执行失败
4. LLM拒绝回答

**限制：**
- `MAX_CONSECUTIVE_ROLLBACKS = 5`
- 超过限制后终止循环

### 4. 上下文管理策略

#### 策略A：无上下文管理 (keep_tool_result = -1)
- 保留完整的对话历史
- 适合短任务
- 可能超出上下文长度

#### 策略B：保留最近N个工具结果 (keep_tool_result = 5)
- 只保留最近5个工具结果
- 自动移除旧的工具输出
- 平衡性能和上下文使用

#### 策略C：周期性压缩 (context_compress_limit > 0)
- 每N轮执行一次总结
- 压缩历史为简短摘要
- 继续执行新的循环

### 5. 分层Agent架构

```
Main Agent (主控制器)
  │
  ├── 直接调用工具 (Google搜索、Python执行等)
  │
  └── 调用Sub-Agent
      └── agent-browsing (浏览Agent)
          ├── 独立的工具集
          ├── 独立的执行循环
          └── 返回总结给Main Agent
```

**优势：**
- 模块化设计
- 专业化分工
- 可扩展性强

### 6. 失败重试机制

**流程：**
```
第1次尝试
  ├── 达到max_turns → 生成failure summary
  └── 格式错误 (无\\boxed{}) → 生成failure summary

第2次尝试（注入failure experience）
  ├── 带着上次的失败经验
  └── 尝试不同策略

第3次尝试（如果仍失败）
  └── 最终放弃或使用fallback
```

### 7. 流式输出设计

**StreamHandler** 支持实时输出：
```python
workflow_start → agent_start → llm_start
  ↓
tool_call_start → tool_call_result
  ↓
llm_end → agent_end → workflow_end
```

**适用场景：**
- Gradio界面
- WebSocket实时通信
- 进度追踪

### 8. 工具调用优化

#### a) 参数自动修正
```python
def fix_tool_call_arguments(tool_name, arguments):
    # 修正常见的参数名错误
    if tool_name == "scrape_and_extract_info":
        if "description" in arguments:
            arguments["info_to_extract"] = arguments.pop("description")
```

#### b) 重复查询去重
```python
used_queries = {
    "main_google_search": {
        "2026年股市": 2,  # 查询过2次
        "明日板块": 1     # 查询过1次
    }
}
```

#### c) 结果后处理
- Demo模式下截断过长的scrape结果
- 格式化工具输出为LLM可理解的格式
- 错误信息标准化

### 9. 日志和追踪系统

**TaskLog** 记录：
- 完整的消息历史
- 每个工具调用的详情
- Token使用统计
- 执行时间分析
- 错误和警告
- 最终答案

**用途：**
- 调试和分析
- 轨迹收集用于训练
- 性能优化
- Benchmark评估

---

## 🎯 总结

MiroFlow Agent框架的核心特点：

1. **灵活的LLM集成** - 支持多种Provider
2. **标准化的工具接口** - 基于MCP协议
3. **强大的错误恢复** - 多层回滚机制
4. **智能的上下文管理** - 多种策略可选
5. **模块化的Agent架构** - 主/子Agent协作
6. **完善的重试机制** - 失败经验学习
7. **详细的执行追踪** - 完整日志系统
8. **流式输出支持** - 实时反馈

这个框架特别适合：
- 需要多步推理的复杂任务
- 需要工具辅助的信息检索
- Benchmark评估和比较
- Agent行为研究和优化

---

**关键文件索引：**
- 核心执行：`src/core/orchestrator.py`
- 提示词：`src/utils/prompt_utils.py`
- 管道：`src/core/pipeline.py`
- LLM客户端：`src/llm/providers/openai_client.py`, `anthropic_client.py`
- 工具执行：`src/core/tool_executor.py`
- 答案生成：`src/core/answer_generator.py`

