"""
Context Manager for intelligent conversation history compression.

Manages client-provided conversation history to prevent context overflow,
using LLM-based semantic compression to extract relevant information.
"""

import logging
from typing import Dict, List, Optional

import tiktoken
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class ContextManager:
    """
    Intelligent context management for multi-turn conversations.
    
    Features:
    1. Token-based length control with configurable thresholds
    2. LLM-based semantic compression that extracts relevant history
    3. Context-aware summarization based on current question
    """

    def __init__(
        self,
        summary_llm_base_url: str,
        summary_llm_api_key: str,
        summary_llm_model: str = "gpt-4o-mini",
        max_history_tokens: int = 30000,  # 历史最多占用 30K tokens
        compression_enabled: bool = True,  # 是否启用压缩
    ):
        """
        Initialize context manager.
        
        Args:
            summary_llm_base_url: Base URL for summary LLM
            summary_llm_api_key: API key for summary LLM
            summary_llm_model: Model to use for summarization
            max_history_tokens: Maximum tokens allowed for history
            compression_enabled: Whether to enable compression
        """
        self.summary_llm_base_url = summary_llm_base_url
        self.summary_llm_api_key = summary_llm_api_key
        self.summary_llm_model = summary_llm_model
        self.max_history_tokens = max_history_tokens
        self.compression_enabled = compression_enabled

        # Initialize tiktoken encoder
        try:
            self.encoder = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"Failed to initialize tiktoken encoder: {e}")
            self.encoder = None

        # Initialize summary LLM client
        self.summary_client = AsyncOpenAI(
            base_url=summary_llm_base_url, api_key=summary_llm_api_key
        )

    def _count_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        
        Falls back to character-based estimation if tiktoken fails.
        """
        if self.encoder:
            try:
                return len(self.encoder.encode(text))
            except Exception:
                pass

        # Fallback: estimate as chars/4
        return len(text) // 4

    def _count_messages_tokens(self, messages: List[Dict]) -> int:
        """Count total tokens in messages list."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += self._count_tokens(str(content))
        return total

    def _format_simple_history(self, messages: List[Dict]) -> str:
        """
        Format history without compression (for short conversations).
        """
        if len(messages) == 1:
            return messages[0]["content"]

        parts = ["# Conversation History\n"]

        for idx, msg in enumerate(messages[:-1], 1):
            role = msg["role"]
            content = msg["content"]

            if role == "user":
                parts.append(f"\n**User (Turn {idx}):**\n{content}\n")
            elif role == "assistant":
                parts.append(f"\n**Assistant (Turn {idx}):**\n{content}\n")
            elif role == "system":
                parts.append(f"\n**System:**\n{content}\n")

        # Current question
        parts.append(f"\n# Current Question\n\n{messages[-1]['content']}")

        return "\n".join(parts)

    async def _compress_with_llm(
        self, messages: List[Dict], current_question: str
    ) -> str:
        """
        Use LLM to intelligently compress conversation history.
        
        Strategy:
        - Provide the current question as context
        - Ask LLM to extract only relevant information from history
        - Generate a concise summary that helps answer the current question
        
        Args:
            messages: Historical messages (excluding current question)
            current_question: The current user question
            
        Returns:
            Compressed context summary
        """
        # Format conversation history for analysis
        conversation_text = ""
        for idx, msg in enumerate(messages, 1):
            role = msg["role"].upper()
            content = msg["content"]
            conversation_text += f"[Turn {idx}] {role}: {content}\n\n"

        # Construct prompt for intelligent compression
        compression_prompt = f"""You are a context compression assistant. Your task is to analyze a conversation history and determine if it is relevant to the current question. If relevant, extract key information; if not relevant, explicitly state that the history is unrelated.

**Current Question:**
{current_question}

**Conversation History:**
{conversation_text}

**Instructions:**

**Step 1: Relevance Assessment (CRITICAL)**
First, determine if the conversation history has ANY meaningful connection to the current question:
- Does the history discuss the same topic, domain, or subject matter?
- Are there shared entities, concepts, or themes?
- Would information from the history actually help answer the current question?

**Step 2: Action Based on Relevance**

If RELEVANT (history is related to current question):
- Extract key facts, data, conclusions, or context from the history
- Include previous questions/topics that directly relate
- Include constraints, preferences, or requirements mentioned earlier
- Summarize in a concise format (max 500 words)

If NOT RELEVANT (history is unrelated to current question):
- Output ONLY: "No relevant context from previous conversation."
- DO NOT attempt to extract or summarize unrelated information
- DO NOT force connections between unrelated topics

**Critical Rules:**
❌ DO NOT let unrelated history influence or pollute the current question
❌ DO NOT assume continuity when topics have clearly changed
❌ DO NOT include information "just in case" - be selective and strict
✅ DO treat the current question independently if history is unrelated
✅ DO acknowledge when starting a new, unrelated topic
✅ DO only include context that DIRECTLY helps answer the current question

**Output Format:**

If relevant:
# Relevant Context

[Concise summary of relevant information from history]

If not relevant:
No relevant context from previous conversation.

Remember: The history is for REFERENCE ONLY. It should NOT be treated as required context unless it is truly relevant to the current question. When in doubt, err on the side of declaring it irrelevant."""

        try:
            logger.info(
                f"Compressing conversation history using {self.summary_llm_model}"
            )

            response = await self.summary_client.chat.completions.create(
                model=self.summary_llm_model,
                messages=[{"role": "user", "content": compression_prompt}],
                max_tokens=1000,
                temperature=0,
            )

            compressed_context = response.choices[0].message.content.strip()

            logger.info(
                f"Compression completed. Original: {self._count_tokens(conversation_text)} tokens, "
                f"Compressed: {self._count_tokens(compressed_context)} tokens"
            )

            return compressed_context

        except Exception as e:
            logger.error(f"LLM-based compression failed: {e}", exc_info=True)
            # Fallback: simple truncation
            return self._fallback_compression(messages)

    def _fallback_compression(self, messages: List[Dict]) -> str:
        """
        Fallback compression strategy when LLM fails.
        
        Simple strategy: Extract first 200 chars from each message.
        """
        logger.warning("Using fallback compression strategy")

        summaries = []
        for i in range(0, len(messages), 2):
            if i < len(messages):
                user_msg = messages[i]
                asst_msg = messages[i + 1] if i + 1 < len(messages) else None

                # User question (truncated)
                user_q = user_msg["content"][:150]
                if len(user_msg["content"]) > 150:
                    user_q += "..."

                summary = f"- Q: {user_q}"

                # Assistant response (truncated)
                if asst_msg:
                    asst_summary = asst_msg["content"][:300]
                    if len(asst_msg["content"]) > 300:
                        asst_summary += "..."
                    summary += f"\n  A: {asst_summary}"

                summaries.append(summary)

        return "# Previous Conversation Summary\n\n" + "\n\n".join(summaries)

    async def process_messages(
        self, messages: List[Dict], force_compression: bool = False
    ) -> str:
        """
        Process conversation messages with intelligent compression.
        
        Main entry point for context management.
        
        Args:
            messages: List of conversation messages in OpenAI format
            force_compression: Force compression regardless of length
            
        Returns:
            Formatted and potentially compressed context string
        """
        if not messages:
            return ""

        # Single message - no compression needed
        if len(messages) == 1:
            return messages[0]["content"]

        # Calculate total tokens
        total_tokens = self._count_messages_tokens(messages)
        current_question = messages[-1]["content"]
        history_messages = messages[:-1]

        logger.info(
            f"Processing conversation: {len(messages)} messages, {total_tokens} tokens"
        )

        # Decision: Should we compress?
        should_compress = (
            self.compression_enabled
            and (total_tokens > self.max_history_tokens or force_compression)
        )

        if not should_compress:
            # No compression needed - format full history
            logger.info("No compression needed, using full history")
            return self._format_simple_history(messages)

        # Compression needed
        logger.info(
            f"Compression triggered: {total_tokens} tokens > {self.max_history_tokens} threshold"
        )

        # Use LLM to intelligently compress
        compressed_context = await self._compress_with_llm(
            history_messages, current_question
        )

        # Combine compressed context with current question
        final_context = f"{compressed_context}\n\n# Current Question\n\n{current_question}"

        logger.info(
            f"Final context: {self._count_tokens(final_context)} tokens "
            f"(reduced from {total_tokens})"
        )

        return final_context


class ContextManagerConfig:
    """Configuration for context management."""

    def __init__(
        self,
        enabled: bool = True,
        max_history_tokens: int = 30000,
        summary_llm_model: str = "gpt-4o-mini",
    ):
        self.enabled = enabled
        self.max_history_tokens = max_history_tokens
        self.summary_llm_model = summary_llm_model

    @classmethod
    def from_dict(cls, config: Dict) -> "ContextManagerConfig":
        """Create config from dictionary."""
        return cls(
            enabled=config.get("enabled", True),
            max_history_tokens=config.get("max_history_tokens", 30000),
            summary_llm_model=config.get("summary_llm_model", "gpt-4o-mini"),
        )

