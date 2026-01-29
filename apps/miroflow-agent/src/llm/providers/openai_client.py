# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

"""
OpenAI-compatible LLM client implementation.

This module provides the OpenAIClient class for interacting with OpenAI's API
and OpenAI-compatible endpoints (such as vLLM, Qwen, DeepSeek, etc.).

Features:
- Async and sync API support
- Automatic retry with exponential backoff
- Token usage tracking and context length management
- MCP tool call parsing and response processing
"""

import asyncio
import dataclasses
import logging
import uuid
from typing import Any, Dict, List, Tuple, Union

import tiktoken
from openai import AsyncOpenAI, DefaultAsyncHttpxClient, DefaultHttpxClient, OpenAI

from ...utils.prompt_utils import generate_mcp_system_prompt
from ..base_client import BaseClient

logger = logging.getLogger("miroflow_agent")


@dataclasses.dataclass
class OpenAIClient(BaseClient):
    def _create_client(self) -> Union[AsyncOpenAI, OpenAI]:
        """Create LLM client"""
        http_client_args = {"headers": {"x-upstream-session-id": self.task_id}}
        if self.async_client:
            return AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                http_client=DefaultAsyncHttpxClient(**http_client_args),
            )
        else:
            return OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                http_client=DefaultHttpxClient(**http_client_args),
            )

    def _update_token_usage(self, usage_data: Any) -> None:
        """Update cumulative token usage"""
        if usage_data:
            input_tokens = getattr(usage_data, "prompt_tokens", 0) or 0
            output_tokens = getattr(usage_data, "completion_tokens", 0) or 0
            prompt_tokens_details = getattr(usage_data, "prompt_tokens_details", None)
            if prompt_tokens_details:
                cached_tokens = (
                    getattr(prompt_tokens_details, "cached_tokens", None) or 0
                )
            else:
                cached_tokens = 0

            # Record token usage for the most recent call
            self.last_call_tokens = {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
            }

            # OpenAI does not provide cache_creation_input_tokens
            self.token_usage["total_input_tokens"] += input_tokens
            self.token_usage["total_output_tokens"] += output_tokens
            self.token_usage["total_cache_read_input_tokens"] += cached_tokens

            self.task_log.log_step(
                "info",
                "LLM | Token Usage",
                f"Input: {self.token_usage['total_input_tokens']}, "
                f"Output: {self.token_usage['total_output_tokens']}",
            )

    async def _create_message(
        self,
        system_prompt: str,
        messages_history: List[Dict[str, Any]],
        tools_definitions,
        keep_tool_result: int = -1,
        stream: bool = False,
        is_final_summary: bool = False,
    ):
        """
        Send message to OpenAI API.
        :param system_prompt: System prompt string.
        :param messages_history: Message history list.
        :return: OpenAI API response object or None (if error occurs).
        """

        # Create a copy for sending to LLM (to avoid modifying the original)
        messages_for_llm = [m.copy() for m in messages_history]

        # put the system prompt in the first message since OpenAI API does not support system prompt in
        if system_prompt:
            # Check if there's already a system or developer message
            if messages_for_llm and messages_for_llm[0]["role"] in [
                "system",
                "developer",
            ]:
                messages_for_llm[0] = {
                    "role": "system",
                    "content": system_prompt,
                }

            else:
                messages_for_llm.insert(
                    0,
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                )

        # Filter tool results to save tokens (only affects messages sent to LLM)
        messages_for_llm = self._remove_tool_result_from_messages(
            messages_for_llm, keep_tool_result
        )

        # Retry loop with dynamic max_tokens adjustment
        max_retries = 10
        base_wait_time = 30
        current_max_tokens = self.max_tokens

        for attempt in range(max_retries):
            params = {
                "model": self.model_name,
                "temperature": self.temperature,
                "messages": messages_for_llm,
                "stream": stream,
                "top_p": self.top_p,
                "extra_body": {},
            }
            # Check if the model is GPT-5, and adjust the parameter accordingly
            if "gpt-5" in self.model_name:
                # Use 'max_completion_tokens' for GPT-5
                params["max_completion_tokens"] = current_max_tokens
            else:
                # Use 'max_tokens' for GPT-4 and other models
                params["max_tokens"] = current_max_tokens

            # Add repetition_penalty if it's not the default value
            if self.repetition_penalty != 1.0:
                params["extra_body"]["repetition_penalty"] = self.repetition_penalty

            if "deepseek-v3-1" in self.model_name:
                params["extra_body"]["thinking"] = {"type": "enabled"}

            # auto-detect if we need to continue from the last assistant message
            if messages_for_llm and messages_for_llm[-1].get("role") == "assistant":
                params["extra_body"]["continue_final_message"] = True
                params["extra_body"]["add_generation_prompt"] = False

            try:
                # Handle streaming mode
                if stream:
                    response = await self._handle_streaming_response(
                        params, messages_history, attempt, max_retries, is_final_summary
                    )
                    if response:
                        return response, messages_history
                    # If None, continue to retry
                    continue
                
                # Non-streaming mode
                if self.async_client:
                    response = await self.client.chat.completions.create(**params)
                else:
                    response = self.client.chat.completions.create(**params)
                # Update token count
                self._update_token_usage(getattr(response, "usage", None))
                
                # Debug: log response structure
                finish_reason = getattr(response.choices[0], 'finish_reason', 'N/A')
                if finish_reason is None or finish_reason == 'N/A':
                    self.task_log.log_step(
                        "warning",
                        "LLM | Response Debug",
                        f"Response structure: {response}, Choices: {response.choices if response.choices else 'None'}",
                    )
                
                self.task_log.log_step(
                    "info",
                    "LLM | Response Status",
                    f"{finish_reason}",
                )

                # Check if response was truncated due to length limit
                finish_reason = getattr(response.choices[0], "finish_reason", None)
                # Handle None finish_reason - treat as 'stop' for compatibility
                if finish_reason is None:
                    finish_reason = "stop"
                    self.task_log.log_step(
                        "warning",
                        "LLM | Missing finish_reason",
                        "finish_reason is None, treating as 'stop' for compatibility",
                    )
                if finish_reason == "length":
                    # If this is not the last retry, increase max_tokens and retry
                    if attempt < max_retries - 1:
                        # Increase max_tokens by 10%
                        current_max_tokens = int(current_max_tokens * 1.1)
                        self.task_log.log_step(
                            "warning",
                            "LLM | Length Limit Reached",
                            f"Response was truncated due to length limit (attempt {attempt + 1}/{max_retries}). Increasing max_tokens to {current_max_tokens} and retrying...",
                        )
                        await asyncio.sleep(base_wait_time)
                        continue
                    else:
                        # Last retry, return the truncated response instead of raising exception
                        self.task_log.log_step(
                            "warning",
                            "LLM | Length Limit Reached - Returning Truncated Response",
                            f"Response was truncated after {max_retries} attempts. Returning truncated response to allow ReAct loop to continue.",
                        )
                        # Return the truncated response and let the orchestrator handle it
                        return response, messages_history

                # Check if the last 50 characters of the response appear more than 5 times in the response content.
                # If so, treat it as a severe repeat and trigger a retry.
                if hasattr(response.choices[0], "message") and hasattr(
                    response.choices[0].message, "content"
                ):
                    resp_content = response.choices[0].message.content or ""
                else:
                    resp_content = getattr(response.choices[0], "text", "")

                if resp_content and len(resp_content) >= 50:
                    tail_50 = resp_content[-50:]
                    repeat_count = resp_content.count(tail_50)
                    if repeat_count > 5:
                        # If this is not the last retry, retry
                        if attempt < max_retries - 1:
                            self.task_log.log_step(
                                "warning",
                                "LLM | Repeat Detected",
                                f"Severe repeat: the last 50 chars appeared over 5 times (attempt {attempt + 1}/{max_retries}), retrying...",
                            )
                            await asyncio.sleep(base_wait_time)
                            continue
                        else:
                            # Last retry, return anyway
                            self.task_log.log_step(
                                "warning",
                                "LLM | Repeat Detected - Returning Anyway",
                                f"Severe repeat detected after {max_retries} attempts. Returning response anyway.",
                            )

                # Success - return the original messages_history (not the filtered copy)
                # This ensures that the complete conversation history is preserved in logs
                return response, messages_history

            except asyncio.TimeoutError as e:
                if attempt < max_retries - 1:
                    self.task_log.log_step(
                        "warning",
                        "LLM | Timeout Error",
                        f"Timeout error (attempt {attempt + 1}/{max_retries}): {str(e)}, retrying...",
                    )
                    await asyncio.sleep(base_wait_time)
                    continue
                else:
                    self.task_log.log_step(
                        "error",
                        "LLM | Timeout Error",
                        f"Timeout error after {max_retries} attempts: {str(e)}",
                    )
                    raise e
            except asyncio.CancelledError as e:
                self.task_log.log_step(
                    "error",
                    "LLM | Request Cancelled",
                    f"Request was cancelled: {str(e)}",
                )
                raise e
            except Exception as e:
                if "Error code: 400" in str(e) and "longer than the model" in str(e):
                    self.task_log.log_step(
                        "error",
                        "LLM | Context Length Error",
                        f"Error: {str(e)}",
                    )
                    raise e
                else:
                    if attempt < max_retries - 1:
                        self.task_log.log_step(
                            "warning",
                            "LLM | API Error",
                            f"Error (attempt {attempt + 1}/{max_retries}): {str(e)}, retrying...",
                        )
                        await asyncio.sleep(base_wait_time)
                        continue
                    else:
                        self.task_log.log_step(
                            "error",
                            "LLM | API Error",
                            f"Error after {max_retries} attempts: {str(e)}",
                        )
                        raise e

        # Should never reach here, but just in case
        raise Exception("Unexpected error: retry loop completed without returning")

    def process_llm_response(
        self, llm_response: Any, message_history: List[Dict], agent_type: str = "main"
    ) -> tuple[str, bool, List[Dict]]:
        """Process LLM response"""
        if not llm_response or not llm_response.choices:
            error_msg = "LLM did not return a valid response."
            self.task_log.log_step(
                "error", "LLM | Response Error", f"Error: {error_msg}"
            )
            return "", True, message_history  # Exit loop, return message_history

        # Extract LLM response text
        # Handle both standard finish_reason and camelCase finishReason
        finish_reason = getattr(llm_response.choices[0], "finish_reason", None)
        if finish_reason is None:
            finish_reason = getattr(llm_response.choices[0], "finishReason", None)
        if finish_reason is None:
            finish_reason = "stop"  # Default to stop if not found
            
        if finish_reason == "stop":
            assistant_response_text = llm_response.choices[0].message.content or ""
            
            # Handle reasoning field (for o1-style models and MiroThinker)
            # If reasoning_content exists, prepend it as <think> tags
            reasoning_content = getattr(llm_response.choices[0].message, "reasoning_content", None)
            if reasoning_content:
                assistant_response_text = f"<think>\n{reasoning_content}\n</think>\n\n{assistant_response_text}"

            message_history.append(
                {"role": "assistant", "content": assistant_response_text}
            )

        elif finish_reason == "length":
            assistant_response_text = llm_response.choices[0].message.content or ""
            if assistant_response_text == "":
                assistant_response_text = "LLM response is empty."
            elif "Context length exceeded" in assistant_response_text:
                # This is the case where context length is exceeded, needs special handling
                self.task_log.log_step(
                    "warning",
                    "LLM | Context Length",
                    "Detected context length exceeded, returning error status",
                )
                message_history.append(
                    {"role": "assistant", "content": assistant_response_text}
                )
                return (
                    assistant_response_text,
                    True,
                    message_history,
                )  # Return True to indicate need to exit loop

            # Add assistant response to history
            message_history.append(
                {"role": "assistant", "content": assistant_response_text}
            )

        else:
            raise ValueError(
                f"Unsupported finish reason: {finish_reason}"
            )

        return assistant_response_text, False, message_history

    def extract_tool_calls_info(
        self, llm_response: Any, assistant_response_text: str
    ) -> List[Dict]:
        """Extract tool call information from LLM response"""
        from ...utils.parsing_utils import parse_llm_response_for_tool_calls

        # First, try to get tool_calls from the response object (OpenAI format)
        if llm_response and llm_response.choices:
            message = llm_response.choices[0].message
            if hasattr(message, 'tool_calls') and message.tool_calls:
                # Use the tool_calls list directly
                self.task_log.log_step(
                    "info",
                    "LLM | Tool Calls Extraction",
                    f"Found {len(message.tool_calls)} tool_calls in response object"
                )
                return parse_llm_response_for_tool_calls(message.tool_calls)
        
        # Fall back to parsing from text (for MCP XML format)
        self.task_log.log_step(
            "info",
            "LLM | Tool Calls Extraction",
            f"Parsing from text (length: {len(assistant_response_text)}, has MCP: {'<use_mcp_tool>' in assistant_response_text})"
        )
        tool_calls = parse_llm_response_for_tool_calls(assistant_response_text)
        self.task_log.log_step(
            "info",
            "LLM | Tool Calls Extraction",
            f"Extracted {len(tool_calls)} tool calls from text"
        )
        return tool_calls

    def update_message_history(
        self, message_history: List[Dict], all_tool_results_content_with_id: List[Tuple]
    ) -> List[Dict]:
        """Update message history with tool calls data (llm client specific)"""

        merged_text = "\n".join(
            [
                item[1]["text"]
                for item in all_tool_results_content_with_id
                if item[1]["type"] == "text"
            ]
        )

        message_history.append(
            {
                "role": "user",
                "content": merged_text,
            }
        )

        return message_history

    def generate_agent_system_prompt(self, date: Any, mcp_servers: List[Dict]) -> str:
        return generate_mcp_system_prompt(date, mcp_servers)

    def _estimate_tokens(self, text: str) -> int:
        """Use tiktoken to estimate the number of tokens in text"""
        if not hasattr(self, "encoding"):
            # Initialize tiktoken encoder
            try:
                self.encoding = tiktoken.get_encoding("o200k_base")
            except Exception:
                # If o200k_base is not available, use cl100k_base as fallback
                self.encoding = tiktoken.get_encoding("cl100k_base")

        try:
            return len(self.encoding.encode(text))
        except Exception as e:
            # If encoding fails, use simple estimation: approximately 1 token per 4 characters
            self.task_log.log_step(
                "error",
                "LLM | Token Estimation Error",
                f"Error: {str(e)}",
            )
            return len(text) // 4

    def ensure_summary_context(
        self, message_history: list, summary_prompt: str
    ) -> tuple[bool, list]:
        """
        Check if current message_history + summary_prompt will exceed context
        If it will exceed, remove the last assistant-user pair and return False
        Return True to continue, False if messages have been rolled back
        """
        # Get token usage from the last LLM call
        last_prompt_tokens = self.last_call_tokens.get("prompt_tokens", 0)
        last_completion_tokens = self.last_call_tokens.get("completion_tokens", 0)
        buffer_factor = 1.5

        # Calculate token count for summary prompt
        summary_tokens = int(self._estimate_tokens(summary_prompt) * buffer_factor)

        # Calculate token count for the last user message in message_history
        last_user_tokens = 0
        if message_history[-1]["role"] == "user":
            content = message_history[-1]["content"]
            last_user_tokens = int(self._estimate_tokens(str(content)) * buffer_factor)

        # Calculate total token count: last prompt + completion + last user message + summary + reserved response space
        estimated_total = (
            last_prompt_tokens
            + last_completion_tokens
            + last_user_tokens
            + summary_tokens
            + self.max_tokens
            + 1000  # Add 1000 tokens as buffer
        )

        if estimated_total >= self.max_context_length:
            self.task_log.log_step(
                "info",
                "LLM | Context Limit Reached",
                "Context limit reached, proceeding to step back and summarize the conversation",
            )

            # Remove the last user message (tool call results)
            if message_history[-1]["role"] == "user":
                message_history.pop()

            # Remove the second-to-last assistant message (tool call request)
            if message_history[-1]["role"] == "assistant":
                message_history.pop()

            self.task_log.log_step(
                "info",
                "LLM | Context Limit Reached",
                f"Removed the last assistant-user pair, current message_history length: {len(message_history)}",
            )

            return False, message_history

        self.task_log.log_step(
            "info",
            "LLM | Context Limit Not Reached",
            f"{estimated_total}/{self.max_context_length}",
        )
        return True, message_history

    def format_token_usage_summary(self) -> tuple[List[str], str]:
        """Format token usage statistics, return summary_lines for format_final_summary and log string"""
        token_usage = self.get_token_usage()

        total_input = token_usage.get("total_input_tokens", 0)
        total_output = token_usage.get("total_output_tokens", 0)
        cache_input = token_usage.get("total_cache_input_tokens", 0)

        summary_lines = []
        summary_lines.append("\n" + "-" * 20 + " Token Usage " + "-" * 20)
        summary_lines.append(f"Total Input Tokens: {total_input}")
        summary_lines.append(f"Total Cache Input Tokens: {cache_input}")
        summary_lines.append(f"Total Output Tokens: {total_output}")
        summary_lines.append("-" * (40 + len(" Token Usage ")))
        summary_lines.append("Pricing is disabled - no cost information available")
        summary_lines.append("-" * (40 + len(" Token Usage ")))

        # Generate log string
        log_string = (
            f"[{self.model_name}] Total Input: {total_input}, "
            f"Cache Input: {cache_input}, "
            f"Output: {total_output}"
        )

        return summary_lines, log_string

    def get_token_usage(self):
        return self.token_usage.copy()

    async def _handle_streaming_response(
        self,
        params: dict,
        messages_history: List[Dict[str, Any]],
        attempt: int,
        max_retries: int,
        is_final_summary: bool = False,
    ):
        """
        Handle streaming response from OpenAI API.
        
        Args:
            params: API call parameters
            messages_history: Message history
            attempt: Current retry attempt
            max_retries: Maximum retry attempts
            is_final_summary: Whether this is the final summary phase (no tools available)
            
        Returns:
            Constructed response object or None if needs retry
        """
        try:
            # Create streaming request
            if self.async_client:
                stream = await self.client.chat.completions.create(**params)
            else:
                stream = self.client.chat.completions.create(**params)
            
            # Accumulate response
            full_content = ""
            finish_reason = None
            response_id = None
            created = None
            model = None
            role = None
            
            # Generate message ID for streaming
            message_id = str(uuid.uuid4())
            
            # For collecting tool calls in streaming mode
            tool_calls_dict = {}  # indexed by tool_call index
            
            # Process streaming chunks
            chunk_count = 0
            if self.async_client:
                async for chunk in stream:
                    chunk_count += 1
                    # Debug log removed to reduce log noise
                    # self.task_log.log_step(
                    #     "info",
                    #     "LLM | Stream Debug",
                    #     f"Received chunk #{chunk_count}"
                    # )
                    response_id = chunk.id
                    created = chunk.created
                    model = chunk.model
                    
                    if chunk.choices and len(chunk.choices) > 0:
                        choice = chunk.choices[0]
                        finish_reason = choice.finish_reason
                        
                        # Handle content delta
                        # IMPORTANT: Separate handling for 'reasoning' and 'content' fields
                        # - 'reasoning' field: thinking process, output directly (no filtering)
                        # - 'content' field: depends on context
                        #   * In thinking phase (has tools): DON'T output (contains <use_mcp_tool> for param extraction)
                        #   * In summary phase (no tools): DO output (final answer for user)
                        
                        if choice.delta:
                            # Handle reasoning field (thinking process)
                            # This is the thinking process and should be output directly
                            if hasattr(choice.delta, 'reasoning') and choice.delta.reasoning:
                                reasoning_delta = choice.delta.reasoning
                                full_content += reasoning_delta
                                
                                # Send reasoning content directly without filtering
                                if self.stream_handler:
                                    await self.stream_handler.message(
                                        message_id=message_id,
                                        delta_content=reasoning_delta
                                    )
                            
                            # Handle content field (main content)
                            # Behavior depends on whether we're in thinking or summary phase
                            # Note: Use 'if' not 'elif' to handle both fields when present
                            if hasattr(choice.delta, 'content') and choice.delta.content:
                                content_delta = choice.delta.content
                                full_content += content_delta
                                
                                # Only output content in final summary phase
                                # In thinking phase, content contains <use_mcp_tool> tags for param extraction
                                if is_final_summary:
                                    # Summary phase: Output content directly (final answer)
                                    if self.stream_handler:
                                        await self.stream_handler.message(
                                            message_id=message_id,
                                            delta_content=content_delta
                                        )
                                # else: Thinking phase - don't output content
                        
                        # Handle role
                        if choice.delta and choice.delta.role:
                            role = choice.delta.role
                        
                        # Handle tool calls in streaming mode
                        if choice.delta and hasattr(choice.delta, 'tool_calls') and choice.delta.tool_calls:
                            for tool_call_delta in choice.delta.tool_calls:
                                idx = tool_call_delta.index
                                if idx not in tool_calls_dict:
                                    tool_calls_dict[idx] = {
                                        "id": tool_call_delta.id if hasattr(tool_call_delta, 'id') else None,
                                        "type": tool_call_delta.type if hasattr(tool_call_delta, 'type') else "function",
                                        "function": {
                                            "name": "",
                                            "arguments": ""
                                        }
                                    }
                                
                                # Accumulate function name
                                if hasattr(tool_call_delta, 'function') and tool_call_delta.function:
                                    if hasattr(tool_call_delta.function, 'name') and tool_call_delta.function.name:
                                        tool_calls_dict[idx]["function"]["name"] += tool_call_delta.function.name
                                    if hasattr(tool_call_delta.function, 'arguments') and tool_call_delta.function.arguments:
                                        tool_calls_dict[idx]["function"]["arguments"] += tool_call_delta.function.arguments
                    
                    # Handle usage (usually in the last chunk)
                    if hasattr(chunk, 'usage') and chunk.usage:
                        self._update_token_usage(chunk.usage)
            else:
                # Sync client (not recommended for streaming)
                for chunk in stream:
                    if chunk.choices and len(chunk.choices) > 0:
                        choice = chunk.choices[0]
                        # Handle both reasoning and content fields
                        if choice.delta:
                            if hasattr(choice.delta, 'reasoning') and choice.delta.reasoning:
                                full_content += choice.delta.reasoning
                            elif hasattr(choice.delta, 'content') and choice.delta.content:
                                full_content += choice.delta.content
                    
                    if hasattr(chunk, 'usage') and chunk.usage:
                        self._update_token_usage(chunk.usage)
            
            # Check if truncated due to length
            if finish_reason == "length":
                if attempt < max_retries - 1:
                    self.task_log.log_step(
                        "warning",
                        "LLM | Length Limit Reached",
                        f"Streaming response truncated (attempt {attempt + 1}/{max_retries}). Will retry...",
                    )
                    return None  # Trigger retry
                else:
                    self.task_log.log_step(
                        "warning",
                        "LLM | Length Limit Reached - Using Truncated",
                        "Returning truncated streaming response.",
                    )
            
            # Construct complete response object (for compatibility)
            from types import SimpleNamespace
            
            # Convert tool_calls_dict to list (if any)
            tool_calls_list = None
            if tool_calls_dict:
                tool_calls_list = []
                for idx in sorted(tool_calls_dict.keys()):
                    tc = tool_calls_dict[idx]
                    tool_call_obj = SimpleNamespace(
                        id=tc["id"],
                        type=tc["type"],
                        function=SimpleNamespace(
                            name=tc["function"]["name"],
                            arguments=tc["function"]["arguments"]
                        )
                    )
                    tool_calls_list.append(tool_call_obj)
            
            message = SimpleNamespace(
                role=role or "assistant",
                content=full_content,
                tool_calls=tool_calls_list,
            )
            
            choice = SimpleNamespace(
                index=0,
                message=message,
                finish_reason=finish_reason or "stop",
            )
            
            response = SimpleNamespace(
                id=response_id,
                created=created,
                model=model or self.model_name,
                choices=[choice],
            )
            
            return response
            
        except Exception as e:
            self.task_log.log_step(
                "error",
                "LLM | Streaming Error",
                f"Error during streaming: {str(e)}",
            )
            return None  # Trigger retry
