# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

"""Output formatting utilities for agent responses."""

import re
from typing import Tuple

from ..utils.prompt_utils import FORMAT_ERROR_MESSAGE

# Maximum length for tool results before truncation (100k chars ≈ 25k tokens)
TOOL_RESULT_MAX_LENGTH = 100_000


class OutputFormatter:
    """Formatter for processing and formatting agent outputs."""
    
    def __init__(self):
        """Initialize OutputFormatter with URL deduplication state."""
        self.seen_urls = set()  # Track seen URLs for deduplication across searches

    def _extract_boxed_content(self, text: str) -> str:
        r"""
        Extract the content of the last \boxed{...} occurrence in the given text.

        Supports:
          - Arbitrary levels of nested braces
          - Escaped braces (\{ and \})
          - Whitespace between \boxed and the opening brace
          - Empty content inside braces
          - Incomplete boxed expressions (extracts to end of string as fallback)

        Args:
            text: Input text that may contain \boxed{...} expressions

        Returns:
            The extracted boxed content, or empty string if no match is found.
        """
        if not text:
            return ""

        _BOXED_RE = re.compile(r"\\boxed\b", re.DOTALL)

        last_result = None  # Track the last boxed content (complete or incomplete)
        i = 0
        n = len(text)

        while True:
            # Find the next \boxed occurrence
            m = _BOXED_RE.search(text, i)
            if not m:
                break
            j = m.end()

            # Skip any whitespace after \boxed
            while j < n and text[j].isspace():
                j += 1

            # Require that the next character is '{'
            if j >= n or text[j] != "{":
                i = j
                continue

            # Parse the brace content manually to handle nesting and escapes
            depth = 0
            k = j
            escaped = False
            found_closing = False
            while k < n:
                ch = text[k]
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    # When depth returns to zero, the boxed content ends
                    if depth == 0:
                        last_result = text[j + 1 : k]
                        i = k + 1
                        found_closing = True
                        break
                k += 1

            # If we didn't find a closing brace, this is an incomplete boxed
            # Store it as the last result (will be overwritten if we find more boxed later)
            if not found_closing and depth > 0:
                last_result = text[j + 1 : n]
                i = k  # Continue from where we stopped
            elif not found_closing:
                i = j + 1  # Move past this invalid boxed

        # Return the last boxed content found (complete or incomplete)
        black_list = ["?", "??", "???", "？", "……", "…", "...", "unknown", None]
        return last_result.strip() if last_result not in black_list else ""

    def format_tool_result_for_user(self, tool_call_execution_result: dict) -> dict:
        """
        Format tool execution results to be fed back to LLM as user messages.

        Only includes necessary information (results or errors). Long results
        are truncated to TOOL_RESULT_MAX_LENGTH to prevent context overflow.
        
        For search results, adds index numbers to help LLM cite sources.

        Args:
            tool_call_execution_result: Dict containing server_name, tool_name,
                and either 'result' or 'error'.

        Returns:
            Dict with 'type' and 'text' keys suitable for LLM message content.
        """
        server_name = tool_call_execution_result["server_name"]
        tool_name = tool_call_execution_result["tool_name"]

        if "error" in tool_call_execution_result:
            # Provide concise error information to LLM
            content = f"Tool call to {tool_name} on {server_name} failed. Error: {tool_call_execution_result['error']}"
        elif "result" in tool_call_execution_result:
            # Provide the original output result of the tool
            content = tool_call_execution_result["result"]
            
            # Add index numbers to search results for citation
            if tool_name in ["google_search", "sogou_search"]:
                content = self._add_search_result_indices(content)
            
            # Truncate overly long results to prevent context overflow
            if len(content) > TOOL_RESULT_MAX_LENGTH:
                content = content[:TOOL_RESULT_MAX_LENGTH] + "\n... [Result truncated]"
        else:
            content = f"Tool call to {tool_name} on {server_name} completed, but produced no specific output or result."

        return {"type": "text", "text": content}
    
    def _add_search_result_indices(self, search_result_json: str) -> str:
        """
        Add index numbers to search results for citation purposes.
        
        Performs URL-based deduplication to ensure indices match frontend display.
        
        Transforms:
        {"organic": [{"title": "A", "link": "..."}, {"title": "B", "link": "..."}]}
        
        Into:
        Search Results (cite using [index]):
        [1] Title: A
            Link: ...
            Snippet: ...
        [2] Title: B
            Link: ...
            Snippet: ...
            
        Note: Index numbers start from 1 and increment for each UNIQUE result.
        Duplicate URLs are skipped. These indices will match the frontend display indices.
        """
        try:
            import json
            import logging
            logger = logging.getLogger("miroflow_agent")
            
            data = json.loads(search_result_json)
            
            organic = data.get("organic", [])
            if not organic:
                return search_result_json  # No results, return original
            
            # Format results with indices, applying deduplication
            formatted_lines = [
                "Search Results (cite using [index]):",
                "Note: When citing information, use the index number shown in square brackets, e.g., [1] or [1,2]."
            ]
            
            unique_count = 0
            for item in organic[:20]:  # Check more items to get enough unique results
                link = item.get('link', '')
                
                # Skip if URL already seen (deduplication)
                if link in self.seen_urls:
                    logger.debug(f"[OUTPUT_FORMATTER] Skipping duplicate URL: {link}")
                    continue
                
                # Add to seen URLs
                self.seen_urls.add(link)
                unique_count += 1
                
                # Format this result
                title = item.get('title', 'No title')
                snippet = item.get('snippet', item.get('description', ''))
                
                formatted_lines.append(f"\n[{unique_count}] Title: {title}")
                formatted_lines.append(f"    Link: {link}")
                if snippet:
                    # Truncate very long snippets
                    if len(snippet) > 200:
                        snippet = snippet[:200] + "..."
                    formatted_lines.append(f"    Snippet: {snippet}")
                
                # Stop after 10 unique results
                if unique_count >= 10:
                    break
            
            logger.info(f"[OUTPUT_FORMATTER] Formatted {unique_count} unique search results for LLM")
            return "\n".join(formatted_lines)
            
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            # If parsing fails, return original content
            import logging
            logging.getLogger("miroflow_agent").warning(f"Failed to add search indices: {e}")
            return search_result_json

    def format_final_summary_and_log(
        self, final_answer_text: str, client=None
    ) -> Tuple[str, str, str]:
        """
        Format final summary information, including answers and token statistics.

        Args:
            final_answer_text: The final answer text from the agent
            client: Optional LLM client for token usage statistics

        Returns:
            Tuple of (summary_text, boxed_result, usage_log)
        """
        summary_lines = []
        summary_lines.append("\n" + "=" * 30 + " Final Answer " + "=" * 30)
        summary_lines.append(final_answer_text)

        # Extract boxed result - find the last match using safer regex patterns
        boxed_result = self._extract_boxed_content(final_answer_text)

        # Add extracted result section
        summary_lines.append("\n" + "-" * 20 + " Extracted Result " + "-" * 20)

        if boxed_result:
            summary_lines.append(boxed_result)
        elif final_answer_text:
            summary_lines.append("No \\boxed{} content found.")
            boxed_result = FORMAT_ERROR_MESSAGE

        # Token usage statistics and cost estimation - use client method
        if client and hasattr(client, "format_token_usage_summary"):
            token_summary_lines, log_string = client.format_token_usage_summary()
            summary_lines.extend(token_summary_lines)
        else:
            # If no client or client doesn't support it, use default format
            summary_lines.append("\n" + "-" * 20 + " Token Usage & Cost " + "-" * 20)
            summary_lines.append("Token usage information not available.")
            summary_lines.append("-" * (40 + len(" Token Usage & Cost ")))
            log_string = "Token usage information not available."

        return "\n".join(summary_lines), boxed_result, log_string
