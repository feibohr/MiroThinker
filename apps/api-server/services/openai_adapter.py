"""
OpenAI Format Adapter V1 - Simple Format
Converts MiroThinker events to standard OpenAI Chat Completions format
"""

import json
import logging
import time
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ChatCompletionChunk(BaseModel):
    """OpenAI Chat Completion Chunk"""

    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: list


class OpenAIAdapter:
    """Adapts MiroThinker events to standard OpenAI format (v1 - simple)"""

    def create_chunk(
        self,
        task_id: str,
        model: str,
        delta: dict,
        finish_reason: Optional[str] = None,
    ) -> ChatCompletionChunk:
        """Create OpenAI-format chunk"""
        return ChatCompletionChunk(
            id=task_id,
            object="chat.completion.chunk",
            created=int(time.time()),
            model=model,
            choices=[
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason,
                }
            ],
        )

    def convert_event_to_chunk(
        self, task_id: str, model: str, event: dict
    ) -> Optional[ChatCompletionChunk]:
        """
        Convert MiroThinker event to OpenAI chunk.

        MiroThinker events include:
        - start_of_agent: Agent started
        - end_of_agent: Agent finished
        - tool_call: Tool invocation
        - message: LLM message (with delta streaming)
        - error: Error occurred
        - heartbeat: Keep-alive signal
        """
        event_type = event.get("event")
        data = event.get("data", {})

        # Skip heartbeat events
        if event_type == "heartbeat":
            return None

        # Handle different event types
        if event_type == "start_of_agent":
            # Agent started
            agent_name = data.get("agent_name", "Agent")
            content = f"\n\n### 🤖 {agent_name} Started\n\n"
            return self.create_chunk(
                task_id=task_id,
                model=model,
                delta={"content": content},
                finish_reason=None,
            )

        elif event_type == "end_of_agent":
            # Agent finished
            agent_name = data.get("agent_name", "Agent")
            content = f"\n\n### ✅ {agent_name} Completed\n\n"
            return self.create_chunk(
                task_id=task_id,
                model=model,
                delta={"content": content},
                finish_reason=None,
            )

        elif event_type == "tool_call":
            # Tool invocation
            return self._convert_tool_call(task_id, model, data)

        elif event_type == "message":
            # LLM message with delta streaming
            return self._convert_message(task_id, model, data)

        elif event_type == "error":
            # Error occurred
            error_msg = data.get("error", "Unknown error")
            content = f"\n\n❌ **Error:** {error_msg}\n\n"
            return self.create_chunk(
                task_id=task_id,
                model=model,
                delta={"content": content},
                finish_reason=None,
            )

        return None

    def _convert_tool_call(
        self, task_id: str, model: str, data: dict
    ) -> Optional[ChatCompletionChunk]:
        """Convert tool_call event to OpenAI chunk"""
        tool_name = data.get("tool_name", "unknown_tool")
        tool_input = data.get("tool_input", {})

        # Format tool call information
        content = self._format_tool_call_content(tool_name, tool_input)

        if content:
            return self.create_chunk(
                task_id=task_id,
                model=model,
                delta={"content": content},
                finish_reason=None,
            )

        return None

    def _convert_message(
        self, task_id: str, model: str, data: dict
    ) -> Optional[ChatCompletionChunk]:
        """Convert message event to OpenAI chunk"""
        # Extract delta content
        delta = data.get("delta", {})
        content = delta.get("content", "")

        if content:
            return self.create_chunk(
                task_id=task_id,
                model=model,
                delta={"content": content},
                finish_reason=None,
            )

        return None

    def _format_tool_call_content(self, tool_name: str, tool_input: dict) -> str:
        """Format tool call as markdown content"""
        if tool_name == "show_text":
            # Extract text from show_text tool
            text = ""
            if isinstance(tool_input, dict):
                text = tool_input.get("text", "")
                if not text:
                    result = tool_input.get("result", {})
                    if isinstance(result, dict):
                        text = result.get("text", "")
            elif isinstance(tool_input, str):
                text = tool_input
            return text

        elif tool_name == "google_search":
            # Format search results
            return self._format_search_results(tool_input)

        elif tool_name in ["scrape", "scrape_website", "scrape_and_extract_info"]:
            # Format scrape action (not full content)
            url = ""
            if isinstance(tool_input, dict):
                url = tool_input.get("url", "")
            return f"\n📄 Scraping: {url}\n" if url else ""

        elif tool_name in ["run_python_code", "run_command"]:
            # Format code execution
            return self._format_code_execution(tool_input)

        else:
            # Generic tool call
            return f"\n🔧 Using tool: {tool_name}\n"

    def _format_search_results(self, tool_input: dict) -> str:
        """Format Google search results"""
        try:
            result = tool_input.get("result", "{}")
            result_dict = json.loads(result) if isinstance(result, str) else result
            organic = result_dict.get("organic", [])

            if not organic:
                return ""

            content = "\n### 🔍 Search Results\n\n"
            for idx, item in enumerate(organic[:5], 1):  # Top 5 results
                title = item.get("title", "No title")
                link = item.get("link", "")
                content += f"{idx}. [{title}]({link})\n"

            return content + "\n"

        except Exception as e:
            logger.warning(f"Failed to format search results: {e}")
            return ""

    def _format_code_execution(self, tool_input: dict) -> str:
        """Format code execution"""
        code = tool_input.get("code", "")
        if code:
            return f"\n```python\n{code}\n```\n"
        return ""

    def create_error_chunk(self, task_id: str, model: str, error: str):
        """Create error chunk"""
        return self.create_chunk(
            task_id=task_id,
            model=model,
            delta={"content": f"\n\n❌ **Error:** {error}\n\n"},
            finish_reason="stop",
        )

    def extract_content_from_event(self, event: dict) -> str:
        """Extract text content from event (for non-streaming mode)"""
        event_type = event.get("event")
        data = event.get("data", {})

        if event_type == "tool_call":
            tool_name = data.get("tool_name", "")
            tool_input = data.get("tool_input", {})
            return self._format_tool_call_content(tool_name, tool_input)

        elif event_type == "message":
            delta = data.get("delta", {})
            return delta.get("content", "")

        return ""
