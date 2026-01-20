# Context Management Documentation

## Overview

The API Server includes **intelligent context management** for multi-turn conversations. This prevents context overflow and optimizes token usage by compressing long conversation histories.

## How It Works

### 1. Length Control

```python
MAX_HISTORY_TOKENS=30000  # Default threshold
```

- If conversation history < 30K tokens → Use full history
- If conversation history > 30K tokens → Trigger intelligent compression

### 2. LLM-Based Semantic Compression

When compression is triggered:

1. **Context Analysis**: The system analyzes the current question
2. **Relevance Extraction**: Uses an LLM to extract ONLY relevant information from history
3. **Smart Summarization**: Generates a concise summary focused on the current question

**Key Advantage**: Unlike simple "keep last N turns", this approach:
- ✅ Preserves semantically relevant information
- ✅ Discards irrelevant conversations
- ✅ Maintains context coherence

### Example

```python
# Original conversation (50K tokens)
messages = [
    {"role": "user", "content": "Tell me about quantum computing"},
    {"role": "assistant", "content": "...(5K tokens about quantum)..."},
    {"role": "user", "content": "What's the weather today?"},
    {"role": "assistant", "content": "...(2K tokens about weather)..."},
    {"role": "user", "content": "Back to quantum - what are its applications?"},  # Current
]

# After compression (8K tokens)
# Weather conversation is discarded as irrelevant
# Quantum context is preserved and summarized
compressed_context = """
# Relevant Context

Previous discussion covered quantum computing fundamentals including superposition, 
entanglement, and qubit operations...

# Current Question

Back to quantum - what are its applications?
"""
```

## Configuration

### Environment Variables

```bash
# Enable/disable compression
CONTEXT_COMPRESSION_ENABLED=true

# Token threshold for triggering compression
MAX_HISTORY_TOKENS=30000

# LLM for summarization (uses small, fast model)
SUMMARY_LLM_MODEL=gpt-4o-mini
SUMMARY_LLM_BASE_URL=${BASE_URL}
SUMMARY_LLM_API_KEY=${API_KEY}
```

### Recommended Settings

| Scenario | MAX_HISTORY_TOKENS | SUMMARY_LLM_MODEL |
|----------|-------------------|-------------------|
| Short conversations (< 5 turns) | 50000 | gpt-4o-mini |
| Medium conversations (5-10 turns) | 30000 | gpt-4o-mini |
| Long conversations (> 10 turns) | 20000 | gpt-4o-mini |

## Client Usage

### No Changes Required

Clients use standard OpenAI API format - compression happens transparently:

```python
from openai import OpenAI

client = OpenAI(base_url="http://your-api/v1")

messages = []

# Turn 1
messages.append({"role": "user", "content": "What is AI?"})
response = client.chat.completions.create(model="mirothinker", messages=messages)
messages.append({"role": "assistant", "content": response.choices[0].message.content})

# Turn 2
messages.append({"role": "user", "content": "What are its applications?"})
response = client.chat.completions.create(model="mirothinker", messages=messages)
# ↑ Compression happens automatically if needed

# Turn 10+
# Long history is automatically compressed while preserving relevant context
```

## Best Practices

### 1. Client-Side History Management

While the server handles compression, clients should still:

```python
def manage_history(messages: List[dict], max_turns: int = 10) -> List[dict]:
    """
    Keep conversation manageable on client side
    """
    if len(messages) > max_turns * 2:
        # Keep system message + recent turns
        system_msgs = [m for m in messages if m["role"] == "system"]
        recent_msgs = messages[-max_turns * 2:]
        return system_msgs + recent_msgs
    return messages
```

### 2. Monitor Token Usage

```python
# Check if compression was triggered (logs will show)
# Original: 50000 tokens -> Compressed: 8000 tokens
```

### 3. Adjust Threshold Based on Use Case

**Research/Analysis** (needs more context):
```bash
MAX_HISTORY_TOKENS=50000
```

**Quick Q&A** (less context needed):
```bash
MAX_HISTORY_TOKENS=20000
```

## Architecture

```
┌─────────────────┐
│  Client sends   │
│  messages[...]  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────┐
│  API Server                     │
│                                 │
│  1. Count tokens in messages    │
│  2. If > MAX_HISTORY_TOKENS:    │
│     ┌──────────────────────┐   │
│     │ ContextManager       │   │
│     │                      │   │
│     │ a) Extract current Q │   │
│     │ b) Analyze history   │   │
│     │ c) Use LLM to        │   │
│     │    extract relevant  │   │
│     │    context           │   │
│     └──────────────────────┘   │
│  3. Send compressed context     │
│     to Pipeline                 │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────┐
│  MiroFlow       │
│  Pipeline       │
│  (sees          │
│  compressed     │
│  context)       │
└─────────────────┘
```

## Compression Example

### Input (Original Messages)

```json
{
  "messages": [
    {"role": "user", "content": "Tell me about Python"},
    {"role": "assistant", "content": "Python is a high-level programming language... (3000 tokens)"},
    {"role": "user", "content": "What's the weather?"},
    {"role": "assistant", "content": "I can help with that... (2000 tokens)"},
    {"role": "user", "content": "How do I use decorators in Python?"}
  ]
}
```

### LLM Compression Prompt

```
Current Question: How do I use decorators in Python?

Conversation History:
[Turn 1] USER: Tell me about Python
[Turn 1] ASSISTANT: Python is a high-level...
[Turn 2] USER: What's the weather?
[Turn 2] ASSISTANT: I can help with that...

Extract ONLY information relevant to answering the current question...
```

### Output (Compressed)

```
# Relevant Context

Previous discussion covered Python as a high-level programming language with 
dynamic typing and emphasis on readability. Key concepts mentioned: functions, 
classes, and Python's syntax.

# Current Question

How do I use decorators in Python?
```

## Performance

- **Compression time**: ~1-2 seconds (using gpt-4o-mini)
- **Token reduction**: Typically 60-80% reduction
- **Quality**: Preserves all semantically relevant information

## Fallback Strategy

If LLM compression fails:

1. Log error
2. Use simple truncation (first 200 chars per message)
3. Continue processing with degraded context

## Monitoring

Check logs for compression events:

```
INFO: Compression triggered: 45000 tokens > 30000 threshold
INFO: Compressing conversation history using gpt-4o-mini
INFO: Compression completed. Original: 45000 tokens, Compressed: 8500 tokens
INFO: Final context: 8600 tokens (reduced from 45100)
```

## Limitations

1. **Compression cost**: Each compression uses summary LLM tokens
2. **Latency**: Adds 1-2s for compression
3. **Information loss**: Some details may be omitted if deemed irrelevant

## Future Improvements

- [ ] Cache compressed contexts per conversation ID
- [ ] Support multiple compression strategies
- [ ] Adaptive threshold based on conversation type
- [ ] Compression quality metrics

