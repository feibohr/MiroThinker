"""
OpenAI-compatible Chat Completions API
"""

import json
import logging
import time
import uuid
from typing import AsyncGenerator, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.openai_adapter import OpenAIAdapter
from services.openai_adapter_v2 import OpenAIAdapterV2
from services.stream_handler import StreamHandler

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ OpenAI-Compatible Models ============


class ChatMessage(BaseModel):
    """Chat message"""

    role: Literal["system", "user", "assistant", "task"]
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI Chat Completion Request"""

    model: str = Field(default="mirothinker", description="Model name")
    messages: List[ChatMessage] = Field(description="List of messages")
    temperature: Optional[float] = Field(default=1.0, ge=0, le=2)
    top_p: Optional[float] = Field(default=1.0, ge=0, le=1)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    stream: bool = Field(default=False, description="Enable streaming")
    stream_options: Optional[dict] = Field(
        default=None, description="Streaming options"
    )


class ChatCompletionResponse(BaseModel):
    """OpenAI Chat Completion Response (non-streaming)"""

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[dict]
    usage: dict


# ============ API Endpoints ============


@router.post("/v1/chat/completions")
async def create_chat_completion(request_body: ChatCompletionRequest, request: Request):
    """
    OpenAI-compatible chat completions endpoint (v1 - simple format).

    Supports both streaming and non-streaming modes.
    Multi-turn conversation with intelligent context compression.
    """
    try:
        # Get managers from app state
        pipeline_manager = request.app.state.pipeline_manager
        context_manager = request.app.state.context_manager

        # Process conversation history with intelligent compression
        messages_dict = [msg.model_dump() for msg in request_body.messages]
        query = await context_manager.process_messages(messages_dict)

        if not query:
            raise HTTPException(status_code=400, detail="No user message found")

        # Generate task ID
        task_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

        if request_body.stream:
            # Streaming mode
            return StreamingResponse(
                _stream_chat_completion(
                    task_id=task_id,
                    query=query,
                    model=request_body.model,
                    pipeline_manager=pipeline_manager,
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        else:
            # Non-streaming mode
            return await _complete_chat_completion(
                task_id=task_id,
                query=query,
                model=request_body.model,
                pipeline_manager=pipeline_manager,
            )

    except Exception as e:
        logger.error(f"Error in chat completion: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v2/chat/completions")
async def create_chat_completion_v2(request_body: ChatCompletionRequest, request: Request):
    """
    OpenAI-compatible chat completions endpoint (v2 - extended format).

    Supports both streaming and non-streaming modes with extended research process tracking.
    Multi-turn conversation with intelligent context compression.
    
    Extended format includes:
    - Hierarchical task blocks (parent_taskid, index)
    - Research process tracking (research_process_block, research_think_block, etc.)
    - JSON Lines format for search results
    - Structured metadata for web browsing
    """
    try:
        # Get managers from app state
        pipeline_manager = request.app.state.pipeline_manager
        context_manager = request.app.state.context_manager

        # Process conversation history with intelligent compression
        messages_dict = [msg.model_dump() for msg in request_body.messages]
        query = await context_manager.process_messages(messages_dict)

        if not query:
            raise HTTPException(status_code=400, detail="No user message found")

        # Generate task ID
        task_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

        if request_body.stream:
            # Streaming mode
            return StreamingResponse(
                _stream_chat_completion_v2(
                    task_id=task_id,
                    query=query,
                    model=request_body.model,
                    pipeline_manager=pipeline_manager,
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        else:
            # Non-streaming mode
            return await _complete_chat_completion_v2(
                task_id=task_id,
                query=query,
                model=request_body.model,
                pipeline_manager=pipeline_manager,
            )

    except Exception as e:
        logger.error(f"Error in chat completion v2: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============ Helper Functions ============
# Note: _extract_query_from_messages is deprecated in favor of ContextManager.process_messages()


async def _stream_chat_completion(
    task_id: str, query: str, model: str, pipeline_manager
) -> AsyncGenerator[str, None]:
    """
    Stream chat completion in standard OpenAI format (v1 - simple).

    Yields SSE-formatted events in OpenAI Chat Completion Chunk format.
    """
    stream_handler = StreamHandler(pipeline_manager)
    openai_adapter = OpenAIAdapter()

    try:
        # Send initial chunk with role
        initial_chunk = openai_adapter.create_chunk(
            task_id=task_id,
            model=model,
            delta={"role": "assistant"},
            finish_reason=None,
        )
        yield f"data: {initial_chunk.model_dump_json(exclude_none=True)}\n\n"

        # Stream research events
        async for event in stream_handler.stream_research(task_id, query):
            # Convert MiroThinker event to OpenAI chunk
            chunk = openai_adapter.convert_event_to_chunk(
                task_id=task_id,
                model=model,
                event=event,
            )

            if chunk:
                yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"

        # Send final chunk with finish reason
        final_chunk = openai_adapter.create_chunk(
            task_id=task_id,
            model=model,
            delta={},
            finish_reason="stop",
        )
        yield f"data: {final_chunk.model_dump_json(exclude_none=True)}\n\n"

        # Send [DONE] marker
        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"Stream error: {e}", exc_info=True)
        error_chunk = openai_adapter.create_error_chunk(
            task_id=task_id, model=model, error=str(e)
        )
        yield f"data: {error_chunk.model_dump_json(exclude_none=True)}\n\n"
        yield "data: [DONE]\n\n"


async def _stream_chat_completion_v2(
    task_id: str, query: str, model: str, pipeline_manager
) -> AsyncGenerator[str, None]:
    """
    Stream chat completion in extended format (v2 - with research process).

    Yields SSE-formatted events with extended fields.
    """
    stream_handler = StreamHandler(pipeline_manager)
    openai_adapter = OpenAIAdapterV2()

    try:
        # Send initial chunk with role
        initial_chunk = openai_adapter.create_chunk(
            task_id=task_id,
            model=model,
            delta={"role": "assistant"},
            finish_reason=None,
        )
        yield f"data: {initial_chunk.model_dump_json(exclude_none=True)}\n\n"

        # Stream research events
        async for event in stream_handler.stream_research(task_id, query):
            # Convert MiroThinker event to OpenAI chunk(s)
            chunks = openai_adapter.convert_event_to_chunk(
                task_id=task_id,
                model=model,
                event=event,
            )

            if chunks:
                # Handle both single chunk and list of chunks
                if not isinstance(chunks, list):
                    chunks = [chunks]
                
                # IMPORTANT: Output all chunks from this event together without interruption
                # This ensures message_start, message_process, message_result for each task block
                # are output as a complete group without other task blocks interleaving.
                # Each event's chunks are output atomically to maintain ordering.
                for chunk in chunks:
                    # Filter out assistant outputs with <think> tags (should be handled as research_think_block)
                    chunk_dict = chunk.model_dump()
                    delta = chunk_dict.get("choices", [{}])[0].get("delta", {})
                    
                    # Skip assistant role outputs that contain <think> tags
                    if delta.get("role") == "assistant" and delta.get("content"):
                        content = delta.get("content", "")
                        if "<think>" in content or "</think>" in content:
                            logger.warning(f"Filtered assistant output with <think> tags (length: {len(content)})")
                            continue
                    
                    # Yield chunk immediately to ensure sequential output
                    # This guarantees that all chunks from a single event are output together,
                    # maintaining the order: message_start -> message_process -> message_result
                    yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"

        # Send final chunk with finish reason
        final_chunk = openai_adapter.create_chunk(
            task_id=task_id,
            model=model,
            delta={},
            finish_reason="stop",
        )
        yield f"data: {final_chunk.model_dump_json(exclude_none=True)}\n\n"

        # Send [DONE] marker
        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"Stream error (v2): {e}", exc_info=True)
        error_chunk = openai_adapter.create_error_chunk(
            task_id=task_id, model=model, error=str(e)
        )
        yield f"data: {error_chunk.model_dump_json(exclude_none=True)}\n\n"
        yield "data: [DONE]\n\n"


async def _complete_chat_completion(
    task_id: str, query: str, model: str, pipeline_manager
) -> ChatCompletionResponse:
    """
    Complete chat completion (non-streaming mode, v1 - simple).

    Collects all events and returns final response.
    """
    stream_handler = StreamHandler(pipeline_manager)
    openai_adapter = OpenAIAdapter()

    # Collect all content
    content_parts = []

    try:
        async for event in stream_handler.stream_research(task_id, query):
            # Extract content from event
            text = openai_adapter.extract_content_from_event(event)
            if text:
                content_parts.append(text)

        # Build final response
        full_content = "".join(content_parts)

        return ChatCompletionResponse(
            id=task_id,
            object="chat.completion",
            created=int(time.time()),
            model=model,
            choices=[
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": full_content},
                    "finish_reason": "stop",
                }
            ],
            usage={
                "prompt_tokens": 0,  # Not tracked yet
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        )

    except Exception as e:
        logger.error(f"Completion error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _complete_chat_completion_v2(
    task_id: str, query: str, model: str, pipeline_manager
) -> ChatCompletionResponse:
    """
    Complete chat completion (non-streaming mode, v2 - extended).

    Collects all events and returns final response.
    """
    stream_handler = StreamHandler(pipeline_manager)
    openai_adapter = OpenAIAdapterV2()

    # Collect all content
    content_parts = []

    try:
        async for event in stream_handler.stream_research(task_id, query):
            # Extract content from event
            text = openai_adapter.extract_content_from_event(event)
            if text:
                content_parts.append(text)

        # Build final response
        full_content = "".join(content_parts)

        return ChatCompletionResponse(
            id=task_id,
            object="chat.completion",
            created=int(time.time()),
            model=model,
            choices=[
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": full_content},
                    "finish_reason": "stop",
                }
            ],
            usage={
                "prompt_tokens": 0,  # Not tracked yet
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        )

    except Exception as e:
        logger.error(f"Completion error (v2): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

