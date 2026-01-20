# MiroThinker API Server

OpenAI-compatible API server for MiroThinker research agent.

## Features

- 🔌 **OpenAI-Compatible API**: Drop-in replacement for OpenAI Chat Completions API
- 🌊 **Streaming Support**: Real-time event streaming in OpenAI format
- 💬 **Multi-Turn Conversations**: Full conversation history support with intelligent context management
- 🧠 **Smart Compression**: LLM-based semantic compression extracts only relevant context
- 🔍 **Rich Events**: Search results, code execution, thinking process in structured format
- 🚀 **Production-Ready**: Docker support, health checks, graceful shutdown
- ⚡ **High Concurrency**: Pipeline pooling for concurrent request handling

## Quick Start

### Installation

```bash
cd apps/api-server
uv sync
```

### Configuration

Copy environment variables from miroflow-agent:

```bash
cp ../miroflow-agent/.env .env
# Edit .env with your API keys
```

### Run Server

```bash
# Development mode
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Usage

### Endpoint

```
POST /v1/chat/completions
```

### Request (OpenAI Compatible)

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "mirothinker",
    "messages": [
      {
        "role": "user",
        "content": "What are the latest developments in AI research?"
      }
    ],
    "stream": true
  }'
```

### Response (OpenAI SSE Format)

```
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1234567890,"model":"mirothinker","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1234567890,"model":"mirothinker","choices":[{"index":0,"delta":{"content":"Searching for information..."},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1234567890,"model":"mirothinker","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

## Docker Deployment

```bash
# Build image
docker build -t mirothinker-api:latest .

# Run container
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/.env:/app/.env \
  -v $(pwd)/logs:/app/logs \
  --name mirothinker-api \
  mirothinker-api:latest
```

## Architecture

```
Client → FastAPI → StreamHandler → miroflow-agent Pipeline
                ↓
         OpenAI Format Converter
                ↓
         SSE Stream Response
```

## Environment Variables

See `../miroflow-agent/.env.example` for required environment variables.

Key variables:
- `BASE_URL`: LLM model server URL
- `API_KEY`: LLM API key
- `SERPER_API_KEY`: Google search API key
- `JINA_API_KEY`: Web scraping API key
- `E2B_API_KEY`: Code execution sandbox key

## Health Check

```bash
curl http://localhost:8000/health
```

## License

MIT License

