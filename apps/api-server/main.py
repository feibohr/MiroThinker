"""
MiroThinker API Server
OpenAI-compatible API for MiroThinker research agent
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Load environment variables
miroflow_env_path = Path(__file__).parent.parent / "miroflow-agent" / ".env"
if miroflow_env_path.exists():
    load_dotenv(dotenv_path=miroflow_env_path)
else:
    load_dotenv()

# Import routers
from routers import chat

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Set DEMO_MODE for simplified tool configuration
os.environ["DEMO_MODE"] = "1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for FastAPI application"""
    logger.info("🚀 MiroThinker API Server starting up...")
    
    # Startup: Initialize pipeline components
    from services.pipeline_manager import PipelineManager
    from services.context_manager import ContextManager
    
    # Get concurrency settings from environment
    pool_size = int(os.getenv("PIPELINE_POOL_SIZE", "5"))
    max_concurrent = int(os.getenv("MAX_CONCURRENT_REQUESTS", "10"))
    
    pipeline_manager = PipelineManager(
        pool_size=pool_size, max_concurrent=max_concurrent
    )
    await pipeline_manager.initialize()
    app.state.pipeline_manager = pipeline_manager
    
    # Initialize context manager for conversation history compression
    context_manager = ContextManager(
        summary_llm_base_url=os.getenv("SUMMARY_LLM_BASE_URL", os.getenv("BASE_URL")),
        summary_llm_api_key=os.getenv("SUMMARY_LLM_API_KEY", os.getenv("API_KEY")),
        summary_llm_model=os.getenv("SUMMARY_LLM_MODEL", "gpt-4o-mini"),
        max_history_tokens=int(os.getenv("MAX_HISTORY_TOKENS", "30000")),
        compression_enabled=os.getenv("CONTEXT_COMPRESSION_ENABLED", "true").lower() == "true",
    )
    app.state.context_manager = context_manager
    
    logger.info("✅ Pipeline components initialized")
    logger.info(f"   - Pipeline pool size: {pool_size}")
    logger.info(f"   - Max concurrent requests: {max_concurrent}")
    logger.info(f"   - Context compression: {'enabled' if context_manager.compression_enabled else 'disabled'}")
    logger.info(f"   - Max history tokens: {context_manager.max_history_tokens}")
    logger.info(f"🌐 Server ready at http://0.0.0.0:{os.getenv('PORT', '8000')}")
    
    yield
    
    # Shutdown
    logger.info("👋 MiroThinker API Server shutting down...")
    await pipeline_manager.cleanup()


# Create FastAPI app
app = FastAPI(
    title="MiroThinker API",
    description="OpenAI-compatible API for MiroThinker research agent",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers (without prefix, routes handle versioning internally)
app.include_router(chat.router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "MiroThinker API Server",
        "version": "0.1.0",
        "endpoints": {
            "chat_v1": "/v1/chat/completions (简单格式)",
            "chat_v2": "/v2/chat/completions (扩展格式)",
            "health": "/health",
            "docs": "/docs",
        },
    }


@app.get("/health")
async def health(request):
    """Health check endpoint"""
    pipeline_manager = request.app.state.pipeline_manager
    return {
        "status": "healthy",
        "service": "mirothinker-api",
        "version": "0.1.0",
        "active_requests": pipeline_manager.active_requests,
        "pool_size": pipeline_manager.pool_size,
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "message": str(exc),
                "type": "internal_server_error",
                "code": "internal_error",
            }
        },
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
    )

