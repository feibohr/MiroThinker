"""
OpenAI Format Adapter V2 - Extended Format with Research Process
Converts MiroThinker events to extended OpenAI Chat Completions format
"""

import json
import logging
import re
import time
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ChatCompletionChunk(BaseModel):
    """OpenAI Chat Completion Chunk"""

    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: list


class OpenAIAdapterV2:
    """Adapts MiroThinker events to extended OpenAI format with research process tracking"""

    def __init__(self):
        # Track current task blocks to manage state transitions
        self.current_task_blocks: Dict[str, Dict[str, Any]] = {}
        # Track the root research process block for delayed completion
        self.root_process_taskid: Optional[str] = None
        self.root_process_chunk: Optional[ChatCompletionChunk] = None
        # Track current index for ordering
        self.current_index: int = 0
        # Track if main agent has started (to avoid multiple process blocks from sub-agents)
        self.main_agent_started: bool = False
        # Track if we're in final summary phase
        self.in_final_summary: bool = False
        # Store final answer to emit after research_completed
        self.pending_final_answer: Optional[ChatCompletionChunk] = None
        # Track seen URLs for deduplication across searches
        self.seen_urls: set = set()
        # Cache search results for browse to reuse: {url: {title, snippet, icon}}
        self.search_results_cache: Dict[str, Dict[str, str]] = {}
        # Track global search result index (across multiple searches)
        self.global_search_index: int = 0
        # Track cited source indices from the final answer
        self.cited_sources: List[int] = []
        # Accumulate final answer content for citation extraction
        self.final_answer_accumulated: str = ""
        # Track current think block for streaming
        self.current_think_taskid: Optional[str] = None
        self.current_think_index: Optional[int] = None
        self.current_think_started: bool = False
        
    def _generate_task_id(self) -> str:
        """Generate unique task ID"""
        return str(int(time.time() * 1000000))
    
    def _extract_favicon_url(self, url: str) -> str:
        """
        Extract favicon URL from a given URL.
        Returns the domain + /favicon.ico
        
        Args:
            url: Full URL (e.g., https://www.example.com/path/to/page)
            
        Returns:
            Favicon URL (e.g., https://www.example.com/favicon.ico)
        """
        try:
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}/favicon.ico"
            return ""
        except Exception:
            return ""
    
    def _extract_cited_sources(self, text: str) -> List[int]:
        """
        Extract cited source indices from <researchrefsource> tags.
        
        Format: <researchrefsource data-ids="[2,3]"></researchrefsource>
        Returns: List of unique cited indices [2, 3]
        """
        cited_indices = []
        
        # Pattern to match <researchrefsource data-ids="[N,M,...]"></researchrefsource>
        # Captures the content inside data-ids="[...]"
        pattern = r'<researchrefsource\s+data-ids="\[([^\]]+)\]"\s*></researchrefsource>'
        matches = re.findall(pattern, text)
        
        for match in matches:
            try:
                # match is like "2,3" or "1" or "1,2,3"
                # Split by comma and parse each number
                indices = [int(x.strip()) for x in match.split(',')]
                cited_indices.extend(indices)
            except ValueError as e:
                logger.warning(f"Failed to parse cited sources from: {match}, error: {e}")
        
        # Return unique indices, sorted
        return sorted(list(set(cited_indices)))
    
    def _next_index(self) -> int:
        """Get next index and increment"""
        idx = self.current_index
        self.current_index += 1
        return idx

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
    
    def create_task_chunk(
        self,
        task_id: str,
        model: str,
        taskstat: str,
        content_type: str,
        task_content: str,
        taskid: str,
        parent_taskid: str = "",
        index: Optional[int] = None,
        finish_reason: Optional[str] = None,
    ) -> ChatCompletionChunk:
        """Create task-format chunk with extended fields"""
        delta = {
            "taskstat": taskstat,
            "role": "task",
            "content_type": content_type,
            "parent_taskid": parent_taskid,
            "index": index if index is not None else 0,
            "task_content": task_content,
            "content": "",
            "taskid": taskid,
        }
        
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
    ) -> Optional[List[ChatCompletionChunk]]:
        """
        Convert MiroThinker event to OpenAI chunk(s).
        
        Returns a list of chunks to support multi-stage emissions (start, process, result).
        
        IMPORTANT: Each task block's three states (message_start, message_process, message_result)
        must be output as a complete group without interruption. All chunks returned from this
        function will be output atomically to maintain ordering.

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

        # Handle different event types with new format
        if event_type == "start_of_agent":
            # Agent started - emit research process block
            return self._handle_start_of_agent(task_id, model, data)

        elif event_type == "end_of_agent":
            # Agent finished - emit completion block
            return self._handle_end_of_agent(task_id, model, data)

        elif event_type == "tool_call":
            # Tool invocation - emit different blocks based on tool type
            return self._convert_tool_call(task_id, model, data)

        elif event_type == "message":
            # LLM message with delta streaming - emit as think block
            return self._convert_message(task_id, model, data)

        elif event_type == "error":
            # Error occurred
            return self._handle_error(task_id, model, data)

        return None

    def _handle_start_of_agent(
        self, task_id: str, model: str, data: dict
    ) -> List[ChatCompletionChunk]:
        """Handle agent start event - emit research process block (root node) only for main agent"""
        chunks = []
        
        # If there's an ongoing think block, close it first
        if self.current_think_started:
            chunks.append(self.create_task_chunk(
                task_id=task_id,
                model=model,
                taskstat="message_result",
                content_type="research_think_block",
                task_content="",
                taskid=self.current_think_taskid,
                parent_taskid=self.root_process_taskid or "",
                index=self.current_think_index,
            ))
            # Reset think block state
            self.current_think_started = False
            self.current_think_taskid = None
            self.current_think_index = None
        
        # Check if this is the final summary agent
        agent_name = data.get("agent_name", "")
        if agent_name == "Final Summary":
            self.in_final_summary = True
            # Set index for final answer streaming
            self._final_answer_index = self._next_index()
        
        # Only create research_process_block for the first (main) agent
        # Sub-agents (like summary agent) should not create their own process blocks
        if not self.main_agent_started:
            self.main_agent_started = True
            
            # Create root research process block
            root_taskid = self._generate_task_id()
            self.root_process_taskid = root_taskid
            root_index = self._next_index()
            
            # Emit message_start for root process block
            chunks.append(self.create_task_chunk(
                task_id=task_id,
                model=model,
                taskstat="message_start",
                content_type="research_process_block",
                task_content=json.dumps({"label": "正在收集和分析资料"}),
                taskid=root_taskid,
                parent_taskid="",
                index=root_index,
            ))
            
            # Emit message_process for root process block
            chunks.append(self.create_task_chunk(
                task_id=task_id,
                model=model,
                taskstat="message_process",
                content_type="research_process_block",
                task_content="",
                taskid=root_taskid,
                parent_taskid="",
                index=root_index,
            ))
            
            # Save the completion chunk for later (will be sent at the end of main agent)
            self.root_process_chunk = self.create_task_chunk(
                task_id=task_id,
                model=model,
                taskstat="message_result",
                content_type="research_process_block",
                task_content="",
                taskid=root_taskid,
                parent_taskid="",
                index=root_index,
            )
        
        return chunks
    
    def _handle_end_of_agent(
        self, task_id: str, model: str, data: dict
    ) -> List[ChatCompletionChunk]:
        """Handle agent end event - emit completion block and close root (only for main agent)"""
        chunks = []
        
        # If there's an ongoing think block, close it first
        if self.current_think_started:
            chunks.append(self.create_task_chunk(
                task_id=task_id,
                model=model,
                taskstat="message_result",
                content_type="research_think_block",
                task_content="",
                taskid=self.current_think_taskid,
                parent_taskid=self.root_process_taskid or "",
                index=self.current_think_index,
            ))
            # Reset think block state
            self.current_think_started = False
            self.current_think_taskid = None
            self.current_think_index = None
        
        agent_name = data.get("agent_name", "Unknown")
        
        # Only emit research_completed and root closure for the main agent
        # Sub-agents should not emit these blocks
        if self.root_process_chunk is not None:
            # Create research completed block as child of root
            complete_taskid = self._generate_task_id()
            complete_index = self._next_index()
            
            # Emit message_start with completion title
            chunks.append(self.create_task_chunk(
                task_id=task_id,
                model=model,
                taskstat="message_start",
                content_type="research_completed",
                task_content=json.dumps({"label": "已收集充分的信息，即将开始回复"}),
                taskid=complete_taskid,
                parent_taskid=self.root_process_taskid or "",
                index=complete_index,
            ))
            
            # Emit message_process
            chunks.append(self.create_task_chunk(
                task_id=task_id,
                model=model,
                taskstat="message_process",
                content_type="research_completed",
                task_content="",
                taskid=complete_taskid,
                parent_taskid=self.root_process_taskid or "",
                index=complete_index,
            ))
            
            # Emit message_result
            chunks.append(self.create_task_chunk(
                task_id=task_id,
                model=model,
                taskstat="message_result",
                content_type="research_completed",
                task_content="",
                taskid=complete_taskid,
                parent_taskid=self.root_process_taskid or "",
                index=complete_index,
            ))
            
            # NOW emit the root process block completion (delayed from start)
            chunks.append(self.root_process_chunk)
            self.root_process_chunk = None
            
            # Extract citations from accumulated final answer (if in streaming mode)
            if self.in_final_summary and self.final_answer_accumulated:
                logger.info(f"[CITATION] Extracting citations from final answer (length: {len(self.final_answer_accumulated)})")
                cited = self._extract_cited_sources(self.final_answer_accumulated)
                if cited:
                    self.cited_sources = cited
                    logger.info(f"[CITATION] Extracted cited sources: {cited}")
                else:
                    logger.info(f"[CITATION] No citations found in final answer")
                # Reset accumulated content
                self.final_answer_accumulated = ""
            
            # Finally, emit the pending final answer (after research_completed and root closure)
            if self.pending_final_answer:
                chunks.append(self.pending_final_answer)
                self.pending_final_answer = None
            
            # After final answer, emit research_used_sources component if we have citations
            if self.cited_sources:
                logger.info(f"[CITATION] ✅ Emitting research_used_sources component with cited indices: {self.cited_sources}")
                sources_taskid = self._generate_task_id()
                sources_index = self._next_index()
                
                # Emit message_start
                chunks.append(self.create_task_chunk(
                    task_id=task_id,
                    model=model,
                    taskstat="message_start",
                    content_type="research_used_sources",
                    task_content=json.dumps({"cited": self.cited_sources}),
                    taskid=sources_taskid,
                    parent_taskid=self.root_process_taskid or "",
                    index=sources_index,
                ))
                
                # Emit message_process (empty for this component)
                chunks.append(self.create_task_chunk(
                    task_id=task_id,
                    model=model,
                    taskstat="message_process",
                    content_type="research_used_sources",
                    task_content="",
                    taskid=sources_taskid,
                    parent_taskid=self.root_process_taskid or "",
                    index=sources_index,
                ))
                
                # Emit message_result
                chunks.append(self.create_task_chunk(
                    task_id=task_id,
                    model=model,
                    taskstat="message_result",
                    content_type="research_used_sources",
                    task_content="",
                    taskid=sources_taskid,
                    parent_taskid=self.root_process_taskid or "",
                    index=sources_index,
                ))
                
                # Reset cited sources for next query
                self.cited_sources = []
            else:
                logger.info(f"[CITATION] ⚠️ No cited sources to emit")
        else:
            # This is a sub-agent or subsequent end_of_agent call
            # But if we have pending_final_answer, we should still emit it!
            if self.pending_final_answer:
                chunks.append(self.pending_final_answer)
                self.pending_final_answer = None
                
                # Also emit citations if available
                if self.cited_sources:
                    sources_taskid = self._generate_task_id()
                    sources_index = self._next_index()
                    
                    chunks.append(self.create_task_chunk(
                        task_id=task_id,
                        model=model,
                        taskstat="message_start",
                        content_type="research_used_sources",
                        task_content=json.dumps({"cited": self.cited_sources}),
                        taskid=sources_taskid,
                        parent_taskid="",
                        index=sources_index,
                    ))
                    
                    chunks.append(self.create_task_chunk(
                        task_id=task_id,
                        model=model,
                        taskstat="message_process",
                        content_type="research_used_sources",
                        task_content="",
                        taskid=sources_taskid,
                        parent_taskid="",
                        index=sources_index,
                    ))
                    
                    chunks.append(self.create_task_chunk(
                        task_id=task_id,
                        model=model,
                        taskstat="message_result",
                        content_type="research_used_sources",
                        task_content="",
                        taskid=sources_taskid,
                        parent_taskid="",
                        index=sources_index,
                    ))
                    
                    self.cited_sources = []
        
        return chunks
    
    def _handle_error(
        self, task_id: str, model: str, data: dict
    ) -> List[ChatCompletionChunk]:
        """Handle error event"""
        error_msg = data.get("error", "Unknown error")
        error_taskid = self._generate_task_id()
        error_index = self._next_index()
        
        chunks = []
        chunks.append(self.create_task_chunk(
            task_id=task_id,
            model=model,
            taskstat="message_start",
            content_type="research_think_block",
            task_content=json.dumps({"label": "错误"}),
            taskid=error_taskid,
            parent_taskid=self.root_process_taskid or "",
            index=error_index,
        ))
        
        chunks.append(self.create_task_chunk(
            task_id=task_id,
            model=model,
            taskstat="message_process",
            content_type="research_think_block",
            task_content=f"❌ {error_msg}",
            taskid=error_taskid,
            parent_taskid=self.root_process_taskid or "",
            index=error_index,
        ))
        
        chunks.append(self.create_task_chunk(
            task_id=task_id,
            model=model,
            taskstat="message_result",
            content_type="research_think_block",
            task_content="",
            taskid=error_taskid,
            parent_taskid=self.root_process_taskid or "",
            index=error_index,
        ))
        
        return chunks

    def _convert_tool_call(
        self, task_id: str, model: str, data: dict
    ) -> Optional[List[ChatCompletionChunk]]:
        """Convert tool_call event to OpenAI chunks"""
        chunks = []
        
        # If there's an ongoing think block, close it first
        if self.current_think_started:
            chunks.append(self.create_task_chunk(
                task_id=task_id,
                model=model,
                taskstat="message_result",
                content_type="research_think_block",
                task_content="",
                taskid=self.current_think_taskid,
                parent_taskid=self.root_process_taskid or "",
                index=self.current_think_index,
            ))
            # Reset think block state
            self.current_think_started = False
            self.current_think_taskid = None
            self.current_think_index = None
        
        tool_name = data.get("tool_name", "unknown_tool")
        tool_input = data.get("tool_input", {})


        # Handle different tool types
        if tool_name == "show_text":
            # Extract text first
            text = self._extract_show_text_content(tool_input)
            
            if not text:
                return None
            
            # If we're in final summary phase
            if self.in_final_summary:
                # If we have accumulated content from streaming, ignore show_text
                # Otherwise, use show_text as fallback (when streaming is not enabled)
                if self.final_answer_accumulated:
                    # Streaming worked, ignore show_text
                    return None
                else:
                    # Streaming didn't work, use show_text as fallback
                    # Output in OpenAI format
                    final_index = self._final_answer_index if hasattr(self, '_final_answer_index') else self._next_index()
                    
                    # Extract cited sources
                    cited = self._extract_cited_sources(text)
                    if cited:
                        self.cited_sources = cited
                    
                    return [self.create_chunk(
                        task_id=task_id,
                        model=model,
                        delta={
                            "role": "assistant",
                            "index": final_index,
                            "content": text
                        },
                        finish_reason=None,
                    )]
            
            # NOT in final summary phase - all show_text content is thinking
            # (The real final answer will come from the Final Summary agent)
            think_taskid = self._generate_task_id()
            think_index = self._next_index()
            
            # message_start
            chunks.append(self.create_task_chunk(
                task_id=task_id,
                model=model,
                taskstat="message_start",
                content_type="research_think_block",
                task_content=json.dumps({"label": "思考过程"}),
                taskid=think_taskid,
                parent_taskid=self.root_process_taskid or "",
                index=think_index,
            ))
            
            # message_process
            chunks.append(self.create_task_chunk(
                task_id=task_id,
                model=model,
                taskstat="message_process",
                content_type="research_think_block",
                task_content=text,
                taskid=think_taskid,
                parent_taskid=self.root_process_taskid or "",
                index=think_index,
            ))
            
            # message_result
            chunks.append(self.create_task_chunk(
                task_id=task_id,
                model=model,
                taskstat="message_result",
                content_type="research_think_block",
                task_content="",
                taskid=think_taskid,
                parent_taskid=self.root_process_taskid or "",
                index=think_index,
            ))
            
            return chunks
        
        elif tool_name == "google_search":
            # Emit search results
            search_chunks = self._handle_search_tool(task_id, model, tool_input)
            if search_chunks:
                chunks.extend(search_chunks)
            return chunks if chunks else None
        
        elif tool_name in ["scrape", "scrape_website", "scrape_and_extract_info"]:
            # Emit browse website block
            scrape_chunks = self._handle_scrape_tool(task_id, model, tool_input)
            if scrape_chunks:
                chunks.extend(scrape_chunks)
            return chunks if chunks else None
        
        return chunks if chunks else None

    def _filter_tool_call_syntax(self, content: str) -> str:
        """
        Filter out tool call syntax from content.
        
        Removes lines that look like tool calls:
        - server_name tool_name {json}
        - Lines containing both a server name pattern and JSON
        """
        if not content:
            return content
        
        lines = content.split('\n')
        filtered_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            
            # Skip lines that match tool call pattern: word word {json}
            # Example: "search_and_scrape_webpage google_search {\"q\": \"...\"}"
            if ' ' in line_stripped and '{' in line_stripped and '"' in line_stripped:
                parts = line_stripped.split()
                # Check if it looks like: server_name tool_name {json}
                if len(parts) >= 2:
                    # Check if line contains common server/tool name patterns
                    if any(pattern in line_stripped for pattern in [
                        'search_and_scrape',
                        'google_search',
                        'sogou_search',
                        'scrape_website',
                        'scrape_and_extract',
                        'tool-python',
                        'jina_scrape',
                    ]):
                        # Skip this line (it's a tool call)
                        continue
            
            # Keep this line
            filtered_lines.append(line)
        
        return '\n'.join(filtered_lines)
    
    def _convert_message(
        self, task_id: str, model: str, data: dict
    ) -> Optional[List[ChatCompletionChunk]]:
        """Convert message event to OpenAI chunks - streaming for both think blocks and final answer"""
        # Extract delta content
        delta = data.get("delta", {})
        content = delta.get("content", "")
        role = delta.get("role", "")

        if not content:
            return None
        
        # Filter tool call syntax from thinking content (but not from final answer)
        if not self.in_final_summary:
            content = self._filter_tool_call_syntax(content)
        
        # If in final summary phase, output as standard OpenAI format (streaming)
        if self.in_final_summary:
            # Accumulate content for citation extraction
            self.final_answer_accumulated += content
            
            # Return standard OpenAI streaming format
            return [self.create_chunk(
                task_id=task_id,
                model=model,
                delta={
                    "role": "assistant",
                    "index": self._final_answer_index if hasattr(self, '_final_answer_index') else self._next_index(),
                    "content": content
                },
                finish_reason=None,
            )]
        
        # Research phase: stream thinking blocks (V2 format)
        chunks = []
        
        # First message: send message_start
        if not self.current_think_started:
            self.current_think_started = True
            self.current_think_taskid = self._generate_task_id()
            self.current_think_index = self._next_index()
            
            chunks.append(self.create_task_chunk(
                task_id=task_id,
                model=model,
                taskstat="message_start",
                content_type="research_think_block",
                task_content=json.dumps({"label": "思考过程"}),
                taskid=self.current_think_taskid,
                parent_taskid=self.root_process_taskid or "",
                index=self.current_think_index,
            ))
        
        # Every message: send message_process with content
        chunks.append(self.create_task_chunk(
            task_id=task_id,
            model=model,
            taskstat="message_process",
            content_type="research_think_block",
            task_content=content,
            taskid=self.current_think_taskid,
            parent_taskid=self.root_process_taskid or "",
            index=self.current_think_index,
        ))
        
        return chunks

    def _extract_show_text_content(self, tool_input: dict) -> str:
        """Extract text from show_text tool"""
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
    
    def _create_text_block(
        self, task_id: str, model: str, label: str, content: str
    ) -> List[ChatCompletionChunk]:
        """
        Create a research_text_block with streaming content.
        
        IMPORTANT: Returns chunks in order: message_start -> message_process (multiple) -> message_result
        All chunks are output atomically to ensure no interleaving.
        """
        chunks = []
        
        text_taskid = self._generate_task_id()
        text_index = self._next_index()
        
        # Emit message_start with label
        chunks.append(self.create_task_chunk(
            task_id=task_id,
            model=model,
            taskstat="message_start",
            content_type="research_text_block",
            task_content=json.dumps({"label": label}),
            taskid=text_taskid,
            parent_taskid=self.root_process_taskid or "",
            index=text_index,
        ))
        
        # Emit content in chunks (simulate streaming)
        # Split content into smaller pieces for better streaming effect
        chunk_size = 500
        for i in range(0, len(content), chunk_size):
            chunk_content = content[i:i+chunk_size]
            chunks.append(self.create_task_chunk(
                task_id=task_id,
                model=model,
                taskstat="message_process",
                content_type="research_text_block",
                task_content=chunk_content,
                taskid=text_taskid,
                parent_taskid=self.root_process_taskid or "",
                index=text_index,
            ))
        
        # Emit message_result
        chunks.append(self.create_task_chunk(
            task_id=task_id,
            model=model,
            taskstat="message_result",
            content_type="research_text_block",
            task_content="",
            taskid=text_taskid,
            parent_taskid=self.root_process_taskid or "",
            index=text_index,
        ))
        
        return chunks
    
    def _handle_search_tool(
        self, task_id: str, model: str, tool_input: dict
    ) -> List[ChatCompletionChunk]:
        """
        Handle Google search tool - emit search results as JSON Lines.
        
        IMPORTANT: All chunks returned must maintain ordering:
        - Search keyword block: message_start -> message_process -> message_result
        - Then search results block: message_start -> message_process (multiple) -> message_result
        All chunks are output atomically to ensure no interleaving.
        """
        chunks = []
        
        # Extract search keyword from various possible locations
        # Priority: q (google_search parameter) > query > keyword
        keyword = ""
        if isinstance(tool_input, dict):
            # Try different field names - google_search uses 'q'
            keyword = (tool_input.get("q") or 
                      tool_input.get("query") or 
                      tool_input.get("keyword") or 
                      tool_input.get("search_query") or "")
            
            # If keyword is in nested structure (args)
            if not keyword and "args" in tool_input:
                args = tool_input["args"]
                if isinstance(args, dict):
                    keyword = args.get("q") or args.get("query") or args.get("keyword") or ""
            
            # Last resort: try to extract from result
            if not keyword and "result" in tool_input:
                try:
                    result_str = tool_input.get("result", "{}")
                    result_dict = json.loads(result_str) if isinstance(result_str, str) else result_str
                    # Try to get search query from result
                    keyword = result_dict.get("searchParameters", {}).get("q", "")
                except Exception as e:
                    logger.warning(f"Failed to extract keyword from search result: {e}")
        
        # Extract and parse search results
        try:
            result = tool_input.get("result", "{}")
            result_dict = json.loads(result) if isinstance(result, str) else result
            organic = result_dict.get("organic", [])
            
            if not organic:
                return chunks
            
            # Create search results block
            search_taskid = self._generate_task_id()
            search_index = self._next_index()
            
            # First process search results with deduplication
            results_lines = []
            unique_count = 0
            
            for item in organic[:20]:  # Check more items to get 10 unique ones
                link = item.get("link", "")
                
                # Skip if URL already seen
                if link in self.seen_urls:
                    continue
                
                # Add to seen URLs
                self.seen_urls.add(link)
                unique_count += 1
                
                # Use global search index (increments across multiple searches)
                self.global_search_index += 1
                result_index = self.global_search_index
                
                title = item.get("title", "No title")
                snippet = item.get("snippet", "")
                icon = self._extract_favicon_url(link)
                
                # Debug: Log raw search result item
                logger.debug(f"[SEARCH_RESULT] Raw item: index={result_index}, title={title}, link={link}, snippet_len={len(snippet)}, icon={icon}")
                
                # Ensure title is not the same as link (防止title是URL的情况)
                if title == link or title.startswith("http://") or title.startswith("https://"):
                    title = "No title"
                
                # Cache search result for later browse reuse (including index)
                self.search_results_cache[link] = {
                    "index": result_index,
                    "title": title,
                    "snippet": snippet,
                    "icon": icon
                }
                
                result_json = json.dumps({
                    "index": result_index,
                    "title": title,
                    "link": link,
                    "snippet": snippet,
                    "icon": icon
                }, ensure_ascii=False)
                results_lines.append(result_json)
                
                # Stop after 10 unique results
                if unique_count >= 10:
                    break

            if keyword:
                search_label = f"搜索 {keyword}，搜索到相关网页 {unique_count} 个"
            else:
                search_label = f"搜索到相关网页 {unique_count} 个"
            
            # Emit message_start with count
            chunks.append(self.create_task_chunk(
                task_id=task_id,
                model=model,
                taskstat="message_start",
                content_type="research_web_search",
                task_content=json.dumps({"label": search_label, "count": unique_count, "keyword": keyword}),
                taskid=search_taskid,
                parent_taskid=self.root_process_taskid or "",
                index=search_index,
            ))
            
            # Send results in batches (to avoid too many chunks)
            batch_size = 3
            for i in range(0, len(results_lines), batch_size):
                batch = results_lines[i:i+batch_size]
                task_content = "\n".join(batch) + "\n"
                
                chunks.append(self.create_task_chunk(
                    task_id=task_id,
                    model=model,
                    taskstat="message_process",
                    content_type="research_web_search",
                    task_content=task_content,
                    taskid=search_taskid,
                    parent_taskid=self.root_process_taskid or "",
                    index=search_index,
                ))
            
            # Emit message_result
            chunks.append(self.create_task_chunk(
                task_id=task_id,
                model=model,
                taskstat="message_result",
                content_type="research_web_search",
                task_content="",
                taskid=search_taskid,
                parent_taskid=self.root_process_taskid or "",
                index=search_index,
            ))
        
        except Exception as e:
            logger.warning(f"Failed to parse search results: {e}")
        
        return chunks
    
    def _handle_scrape_tool(
        self, task_id: str, model: str, tool_input: dict
    ) -> List[ChatCompletionChunk]:
        """
        Handle scrape tool - emit browse website block as JSON.
        
        IMPORTANT: All chunks returned must maintain ordering:
        - Browse block: message_start -> message_process -> message_result
        - Then text block (if content exists): message_start -> message_process (multiple) -> message_result
        All chunks are output atomically to ensure no interleaving.
        """
        chunks = []
        
        url = ""
        if isinstance(tool_input, dict):
            url = tool_input.get("url", "")
        
        if not url:
            return chunks
        
        # Create browse block
        browse_taskid = self._generate_task_id()
        browse_index = self._next_index()
        
        # Emit message_start
        chunks.append(self.create_task_chunk(
            task_id=task_id,
            model=model,
            taskstat="message_start",
            content_type="research_web_browse",
            task_content=json.dumps({"label": "正在浏览网页"}),
            taskid=browse_taskid,
            parent_taskid=self.root_process_taskid or "",
            index=browse_index,
        ))
        
        # Build browse info as JSON
        # First, try to get cached search result info
        cached_info = self.search_results_cache.get(url, {})
        
        # Use cached index if available, otherwise use browse_index
        result_index = cached_info.get("index", browse_index)
        title = cached_info.get("title", "")
        snippet = cached_info.get("snippet", "")
        icon = cached_info.get("icon", "")
        sitename = ""
        
        # Log if we're using cached info
        if cached_info:
            logger.debug(f"[BROWSE] Using cached search result for URL: {url}, index={result_index}")
        
        # Extract result from tool_input (always needed for content)
        result = tool_input.get("result", {})
        # Parse result if it's a JSON string
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                result = {}
        
        # If not in cache, extract from result
        if not title or not snippet:
            
            if isinstance(result, dict):
                # Try to extract title from result
                if not title:
                    title = result.get("title", "")
                
                content = result.get("content", "") or result.get("text", "")
                
                # If no title, try to extract from content's first line
                if not title and content:
                    # Try to find title in the first few lines
                    lines = content.strip().split('\n')
                    for line in lines[:5]:  # Check first 5 lines
                        line = line.strip()
                        # Skip empty lines and very short lines
                        if line and len(line) > 5 and len(line) < 200:
                            # Skip lines that look like metadata or navigation
                            if not any(skip in line.lower() for skip in ['http://', 'https://', 'cookie', 'javascript', 'login', 'sign in']):
                                title = line
                                break
                
                # If no snippet from cache, extract from content
                if not snippet and content:
                    # Use first 200 chars as snippet
                    snippet = content[:200] + "..." if len(content) > 200 else content
                
                # Try to extract sitename from result
                sitename = result.get("sitename", "") or result.get("site_name", "")
        
        # If title is still empty or is a URL, try to extract from URL or use domain
        if not title or title == url or title.startswith("http://") or title.startswith("https://"):
            # Try to extract a meaningful title from URL
            from urllib.parse import urlparse, unquote
            parsed = urlparse(url)
            
            # Try to use the last path segment as title
            path_parts = [p for p in parsed.path.split('/') if p]
            if path_parts:
                # Use the last meaningful path segment
                last_part = unquote(path_parts[-1])
                # Remove file extensions
                if '.' in last_part:
                    last_part = last_part.rsplit('.', 1)[0]
                # Clean up the title
                title = last_part.replace('-', ' ').replace('_', ' ').title()
                # Limit title length
                if len(title) > 50:
                    title = title[:50] + "..."
            
            # If still no title, use domain name
            if not title or len(title) < 3:
                title = parsed.netloc or "No title"
        
        # Extract favicon URL if not cached
        if not icon:
            icon = self._extract_favicon_url(url)
        
        # Debug: Log browse info
        logger.debug(f"[BROWSE_INFO] title={title}, url={url}, snippet_len={len(snippet)}, icon={icon}")
        
        # Emit browse info as JSON (use result_index from cache if available)
        browse_info = json.dumps({
            "index": result_index,
            "title": title,
            "link": url,
            "snippet": snippet,
            "sitename": sitename,
            "icon": icon
        }, ensure_ascii=False)
        
        chunks.append(self.create_task_chunk(
            task_id=task_id,
            model=model,
            taskstat="message_process",
            content_type="research_web_browse",
            task_content=browse_info,
            taskid=browse_taskid,
            parent_taskid=self.root_process_taskid or "",
            index=browse_index,
        ))
        
        # Emit message_result
        chunks.append(self.create_task_chunk(
            task_id=task_id,
            model=model,
            taskstat="message_result",
            content_type="research_web_browse",
            task_content="",
            taskid=browse_taskid,
            parent_taskid=self.root_process_taskid or "",
            index=browse_index,
        ))
        
        # If we have extracted content, emit a text block
        if isinstance(result, dict):
            content = result.get("content", "") or result.get("text", "")
            if content:
                text_chunks = self._create_text_block(
                    task_id=task_id,
                    model=model,
                    label=f"{title} - 内容摘要",
                    content=content[:2000] + "..." if len(content) > 2000 else content
                )
                chunks.extend(text_chunks)
        
        return chunks

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
            
            # Only extract show_text content for non-streaming
            if tool_name == "show_text":
                return self._extract_show_text_content(tool_input)
            return ""

        elif event_type == "message":
            delta = data.get("delta", {})
            return delta.get("content", "")

        return ""

