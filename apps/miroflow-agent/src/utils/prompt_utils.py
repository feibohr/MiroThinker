# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

"""
Prompt templates and utilities for agent system prompts.

This module provides:
- System prompt generation for MCP tool usage
- Agent-specific prompt generation (main agent, browsing agent)
- Summary prompt templates for final answer generation
- Failure experience templates for retry mechanisms
"""

# ============================================================================
# Failure Experience Templates
# ============================================================================

# Header that appears once before all failure experiences
FAILURE_EXPERIENCE_HEADER = """

=== Previous Attempts Analysis ===
The following summarizes what was tried before and why it didn't work. Use this to guide a NEW approach.

"""

# Template for each individual failure experience (used multiple times)
FAILURE_EXPERIENCE_ITEM = """[Attempt {attempt_number}]
{failure_summary}

"""

# Footer that appears once after all failure experiences
FAILURE_EXPERIENCE_FOOTER = """=== End of Analysis ===

Based on the above, you should try a different strategy this time.
"""

FAILURE_SUMMARY_PROMPT = """The task was not completed successfully. Do NOT call any tools. Provide a summary:

Failure type: [incomplete / blocked / misdirected]
  - incomplete: ran out of turns before finishing
  - blocked: got stuck due to tool failure or missing information
  - misdirected: went down the wrong path
What happened: [describe the approach taken and why a final answer was not reached]
Useful findings: [list any facts, intermediate results, or conclusions discovered that should be reused]"""

# Assistant prefix for failure summary generation (guides model to follow structured format)
FAILURE_SUMMARY_THINK_CONTENT = """We need to write a structured post-mortem style summary **without calling any tools**, explaining why the task was not completed, using these required sections:

* **Failure type**: pick one from **incomplete / blocked / misdirected**
* **What happened**: describe the approach taken and why it didn't reach a final answer
* **Useful findings**: list any facts, intermediate results, or conclusions that can be reused"""

FAILURE_SUMMARY_ASSISTANT_PREFIX = (
    f"<think>\n{FAILURE_SUMMARY_THINK_CONTENT}\n</think>\n\n"
)

# ============================================================================
# MCP Tags for Parsing
# ============================================================================

mcp_tags = [
    "<use_mcp_tool>",
    "</use_mcp_tool>",
    "<server_name>",
    "</server_name>",
    "<arguments>",
    "</arguments>",
]

refusal_keywords = [
    "time constraint",
    "I’m sorry, but I can’t",
    "I'm sorry, I cannot solve",
]


def generate_mcp_system_prompt(date, mcp_servers):
    """
    Generate the MCP (Model Context Protocol) system prompt for LLM.

    Creates a structured prompt that instructs the LLM on how to use available
    MCP tools. Includes tool definitions, XML formatting instructions, and
    general task-solving guidelines.

    Args:
        date: Current date object for timestamp inclusion
        mcp_servers: List of server definitions, each containing 'name' and 'tools'

    Returns:
        Complete system prompt string with tool definitions and usage instructions
    """
    formatted_date = date.strftime("%Y-%m-%d")

    # Start building the template, now follows https://docs.anthropic.com/en/docs/build-with-claude/tool-use/overview#tool-use-system-prompt
    template = f"""In this environment you have access to a set of tools you can use to answer the user's question. 

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
{{
"param1": "value1",
"param2": "value2 \\"escaped string\\""
}}
</arguments>
</use_mcp_tool>

Important Notes:
- Tool-use must be placed **at the end** of your response, **top-level**, and not nested within other tags.
- Always adhere to this format for the tool use to ensure proper parsing and execution.

String and scalar parameters should be specified as is, while lists and objects should use JSON format. Note that spaces for string values are not stripped. The output is not expected to be valid XML and is parsed with regular expressions.
Here are the functions available in JSONSchema format:

"""

    # Add MCP servers section
    if mcp_servers and len(mcp_servers) > 0:
        for server in mcp_servers:
            template += f"\n## Server name: {server['name']}\n"

            if "tools" in server and len(server["tools"]) > 0:
                for tool in server["tools"]:
                    # Skip tools that failed to load (they only have 'error' key)
                    if "error" in tool and "name" not in tool:
                        continue
                    template += f"### Tool name: {tool['name']}\n"
                    template += f"Description: {tool['description']}\n"
                    template += f"Input JSON schema: {tool['schema']}\n"

    # Add the full objective system prompt
    template += """
# General Objective

You accomplish a given task iteratively, breaking it down into clear steps and working through them methodically.

"""

    return template


def generate_no_mcp_system_prompt(date):
    """
    Generate a minimal system prompt without MCP tool definitions.

    Used when no tools are available or when running in tool-less mode.

    Args:
        date: Current date object for timestamp inclusion

    Returns:
        Basic system prompt string without tool definitions
    """
    formatted_date = date.strftime("%Y-%m-%d")

    # Start building the template, now follows https://docs.anthropic.com/en/docs/build-with-claude/tool-use/overview#tool-use-system-prompt
    template = """In this environment you have access to a set of tools you can use to answer the user's question. """

    template += f" Today is: {formatted_date}\n"

    template += """
Important Notes:
- Tool-use must be placed **at the end** of your response, **top-level**, and not nested within other tags.
- Always adhere to this format for the tool use to ensure proper parsing and execution.

String and scalar parameters should be specified as is, while lists and objects should use JSON format. Note that spaces for string values are not stripped. The output is not expected to be valid XML and is parsed with regular expressions.
"""

    # Add the full objective system prompt
    template += """
# General Objective

You accomplish a given task iteratively, breaking it down into clear steps and working through them methodically.

"""
    return template


def generate_agent_specific_system_prompt(agent_type=""):
    """
    Generate agent-specific objective prompts based on agent type.

    Different agent types have different objectives:
    - main: Task-solving agent that uses tools to answer questions
    - agent-browsing: Web search and browsing agent for information retrieval

    Args:
        agent_type: Type of agent ("main", "agent-browsing", or "browsing-agent")

    Returns:
        Agent-specific objective prompt string
    """
    if agent_type == "main":
        system_prompt = """\n
# Agent Specific Objective

You are a task-solving agent that uses tools step-by-step to gather information for the user's question.

## Your Role in This Phase:

**INFORMATION GATHERING ONLY** - You are currently in the research phase, NOT the final answer phase.

Your tasks:
1. **Search** for relevant information using available tools
2. **Browse** web pages to extract detailed facts and data
3. **Analyze** whether you have sufficient information to answer the question
4. **Decide** what additional information is needed

## Context Handling (IMPORTANT):

When conversation history or previous context is provided:

❌ **DO NOT assume the previous context is relevant** - Always evaluate if it relates to the current question
❌ **DO NOT let unrelated history pollute your answer** - Treat each question independently unless there's clear continuity
❌ **DO NOT force connections** between unrelated topics from history

✅ **DO assess relevance first** - Determine if previous context actually helps with the current question
✅ **DO treat as reference only** - Previous context is supplementary, not mandatory
✅ **DO start fresh** - If the current question is unrelated to history, focus solely on the new question

**Example:**
- If history discusses "商业航天" but current question asks "今天天气怎么样", ignore the history entirely
- If history discusses "Python编程" and current question asks "如何用Python处理数据", the history may be relevant

## Critical Rules:

❌ DO NOT write final answers or summaries in this phase
❌ DO NOT use heading formats (###) to structure answers
❌ DO NOT directly answer the user's question yet
❌ DO NOT provide conclusions or recommendations

✅ DO use <think> tags to reason about what information you need
✅ DO call tools to search and browse for information
✅ DO analyze the information you've gathered
✅ DO decide if you need more information or if you're ready to proceed

## When to Stop:

You will be explicitly asked to provide a final summary later. For now, focus ONLY on gathering comprehensive information.

"""
    elif agent_type == "agent-browsing" or agent_type == "browsing-agent":
        system_prompt = """# Agent Specific Objective

You are an agent that performs the task of searching and browsing the web for specific information and generating the desired answer. Your task is to retrieve reliable, factual, and verifiable information that fills in knowledge gaps.
Do not infer, speculate, summarize broadly, or attempt to fill in missing parts yourself. Only return factual content.
"""
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")
    return system_prompt.strip()


def generate_agent_summarize_prompt(task_description, agent_type=""):
    """
    Generate the final summarization prompt for an agent.

    Creates prompts that instruct agents to summarize their work and provide
    final answers. Different agent types have different summarization formats:
    - main: Comprehensive answer with citations
    - agent-browsing: Provides structured report of findings

    Args:
        task_description: The original task/question to reference in the summary
        agent_type: Type of agent ("main" or "agent-browsing")

    Returns:
        Summarization prompt string with formatting instructions
    """
    if agent_type == "main":
        summarize_prompt = (
            "# 角色转换：从研究助手到用户顾问\n\n"
            "前面你是一个研究助手，负责搜集信息、调用工具、分析数据。\n"
            "现在，你的角色变了——你是**用户的顾问**，需要将研究成果整理成清晰、人性化的答案呈现给用户。\n\n"
            "## 你的新定位\n\n"
            "✅ **你现在是**：\n"
            "- 面向用户的信息整理者和顾问\n"
            "- 将复杂的研究过程转化为易懂答案的专家\n"
            "- 用户的可信赖信息来源\n\n"
            "❌ **你不再是**：\n"
            "- 研究执行者（不要再提工具调用、访问失败等技术细节）\n"
            "- 决策者（不要说\"需要继续搜索\"、\"应该访问XX网站\"）\n"
            "- 过程记录者（不要列出尝试了什么、失败了什么）\n\n"
            "## 用户的问题\n\n"
            f'"{task_description}"\n\n'
            "## 如何回答用户\n\n"
            "**1. 心态转换**\n"
            "- 想象你正在和用户面对面交流，用自然、专业的语气\n"
            "- 关注用户关心的**结果和洞察**，而不是你的研究过程\n"
            "- 即使信息不完整，也要给出你能给的最佳答案\n\n"
            "**2. 内容组织**\n"
            "- 用清晰的结构（标题、列表、分段）让答案易读\n"
            "- 先给核心答案，再展开细节\n"
            "- 如果某些信息未获取到，简要说明并给出已有信息即可\n\n"
            "**3. 禁止事项**\n"
            "❌ 不要输出技术过程：\"先调用XX工具\"、\"访问XX网站失败\"\n"
            "❌ 不要输出工具标签：<use_mcp_tool>、server_name tool_name 等\n"
            "❌ 不要说\"需要进一步搜索\"、\"建议访问XX\"\n"
            "❌ 不要列举失败的尝试：这是技术细节，用户不关心\n\n"
            "**4. 引用来源**（非常重要）\n"
            "使用以下格式引用信息来源：\n"
            "<researchrefsource data-ids=\"[N]\"></researchrefsource>\n\n"
            "示例：\n"
            "- 单个来源：产值2.5万亿<researchrefsource data-ids=\"[7]\"></researchrefsource>\n"
            "- 多个来源：根据数据<researchrefsource data-ids=\"[1,2,7]\"></researchrefsource>\n\n"
            "❌ 错误格式：[1]、[7]、(来源1)、¹\n"
            "✅ 正确格式：<researchrefsource data-ids=\"[N]\"></researchrefsource>\n\n"
            "## 示例对比\n\n"
            "❌ **不好的回答**（研究者视角）：\n"
            "\\\"尝试访问了新浪财经但失败了，东方财富也超时了。先调用scrape_and_extract_info访问估值页面。\\n"
            "jina_scrape_llm_summary scrape_and_extract_info {...}\\\"\n\n"
            "✅ **好的回答**（顾问视角）：\n"
            "\\\"蓝色光标是中国领先的数字营销服务商<researchrefsource data-ids=\\\"[1]\\\"></researchrefsource>。\\n"
            "根据最新数据，公司2024年Q3营收实现增长<researchrefsource data-ids=\\\"[2]\\\"></researchrefsource>。\\n"
            "关于详细的财务估值数据，目前公开渠道信息有限，建议关注公司财报发布。\\\"\n\n"
            "---\n\n"
            "现在，请以**用户顾问**的身份，用人性化、逻辑清晰的方式回答用户的问题。"
        )
    elif agent_type == "agent-browsing":
        summarize_prompt = (
            "This is a direct instruction to you (the assistant), not the result of a tool call.\n\n"
            "We are now ending this session, and your conversation history will be deleted. "
            "You must NOT initiate any further tool use. This is your final opportunity to report "
            "*all* of the information gathered during the session.\n\n"
            "The original task is repeated here for reference:\n\n"
            f'"{task_description}"\n\n'
            "Summarize the above search and browsing history. Output the FINAL RESPONSE and detailed supporting information of the task given to you.\n\n"
            "If you found any useful facts, data, quotes, or answers directly relevant to the original task, include them clearly and completely.\n"
            "If you reached a conclusion or answer, include it as part of the response.\n"
            "If the task could not be fully answered, do NOT make up any content. Instead, return all partially relevant findings, "
            "Search results, quotes, and observations that might help a downstream agent solve the problem.\n"
            "If partial, conflicting, or inconclusive information was found, clearly indicate this in your response.\n\n"
            "Your final response should be a clear, complete, and structured report.\n"
            "Organize the content into logical sections with appropriate headings.\n"
            "Do NOT include any tool call instructions, speculative filler, or vague summaries.\n"
            "Focus on factual, specific, and well-organized information."
        )
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")

    return summarize_prompt.strip()
