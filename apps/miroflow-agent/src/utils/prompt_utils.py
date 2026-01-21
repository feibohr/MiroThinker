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
            f"Based on the information gathered above, please provide a comprehensive answer to the following question:\n\n"
            f'"{task_description}"\n\n'
            "**CRITICAL - This is the FINAL ANSWER phase:**\n"
            "❌ DO NOT call any tools (no <use_mcp_tool> tags)\n"
            "❌ DO NOT request more information or suggest further searches\n"
            "❌ DO NOT output tool call instructions or XML tags\n"
            "✅ DO provide a direct, complete answer based on the information you already gathered\n"
            "✅ DO synthesize and present the findings in a clear, structured format\n\n"
            "**Context Awareness:**\n"
            "- If previous conversation history was provided but is NOT relevant to this question, DO NOT reference it in your answer\n"
            "- Focus your answer ONLY on the current question and the information you gathered for it\n"
            "- Previous context is for reference only - do not force it into your answer if unrelated\n\n"
            "Please provide a complete and detailed response that:\n"
            "- Directly answers the current question based on gathered information\n"
            "- Includes all relevant analysis and explanations\n"
            "- Cites sources appropriately using the citation format\n"
            "- Is well-structured and easy to understand\n"
            "- Does NOT include irrelevant information from unrelated previous conversations\n"
            "- Does NOT contain any tool call tags or instructions\n\n"
            "⚠️ CRITICAL - Source Citation Format:\n\n"
            "You MUST cite sources using ONLY this exact format:\n"
            "<researchrefsource data-ids=\"[N]\"></researchrefsource>\n\n"
            "❌ WRONG formats (DO NOT USE):\n"
            "- [1] or [7] or [1,2] - These are INCORRECT\n"
            "- (Source 1) - This is INCORRECT\n"
            "- ¹ or ² - These are INCORRECT\n\n"
            "✅ CORRECT format (MUST USE):\n"
            "- Single source: 产值2.5万亿<researchrefsource data-ids=\"[7]\"></researchrefsource>\n"
            "- Multiple sources: 根据数据<researchrefsource data-ids=\"[1,2,7]\"></researchrefsource>\n\n"
            "IMPORTANT:\n"
            "1. Place the citation tag IMMEDIATELY after the fact (before punctuation)\n"
            "2. Use the EXACT format with angle brackets and data-ids attribute\n"
            "3. NEVER use simple brackets like [1] or [7] in your response\n"
            "4. Every fact from search results MUST have a citation tag\n\n"
            "Example of correct usage:\n"
            "For a single source<researchrefsource data-ids=\"[7]\"></researchrefsource>，预计2030年可达10万亿<researchrefsource data-ids=\"[3,7]\"></researchrefsource>。"
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
