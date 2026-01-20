"""
Pipeline Manager
Manages miroflow-agent pipeline components initialization and lifecycle
"""

import logging
import os
from pathlib import Path
from typing import Dict, Optional

from hydra import compose, initialize_config_dir
from omegaconf import DictConfig

from src.config.settings import expose_sub_agents_as_tools
from src.core.pipeline import create_pipeline_components
from src.io.output_formatter import OutputFormatter

from .concurrency_manager import ConcurrencyLimiter, PipelinePool

logger = logging.getLogger(__name__)


class PipelineManager:
    """Manages pipeline components initialization and lifecycle with concurrency support"""

    def __init__(self, pool_size: int = 5, max_concurrent: int = 10):
        """
        Initialize pipeline manager.

        Args:
            pool_size: Number of pipeline instances in the pool (default: 5)
            max_concurrent: Maximum concurrent requests (default: 10)
        """
        self.cfg: Optional[DictConfig] = None
        self.pipeline_pool: Optional[PipelinePool] = None
        self.concurrency_limiter = ConcurrencyLimiter(max_concurrent=max_concurrent)
        self.pool_size = pool_size
        self._initialized = False

    async def initialize(self):
        """Initialize pipeline components with connection pooling"""
        if self._initialized:
            logger.warning("Pipeline manager already initialized")
            return

        logger.info("Initializing pipeline manager...")

        try:
            # Load configuration
            self.cfg = self._load_config()
            agent_set = os.getenv("DEFAULT_AGENT_SET", "demo")
            logger.info(f"Loaded configuration: agent_set={agent_set}")

            # Initialize pipeline pool
            self.pipeline_pool = PipelinePool(self.cfg, pool_size=self.pool_size)
            await self.pipeline_pool.initialize()

            self._initialized = True
            logger.info(
                f"✅ Pipeline manager initialized (pool_size={self.pool_size}, "
                f"max_concurrent={self.concurrency_limiter.max_concurrent})"
            )

        except Exception as e:
            logger.error(f"Failed to initialize pipeline: {e}", exc_info=True)
            raise

    async def cleanup(self):
        """Cleanup pipeline resources"""
        if not self._initialized:
            return

        logger.info("Cleaning up pipeline components...")
        if self.pipeline_pool:
            await self.pipeline_pool.cleanup()
        self._initialized = False

    async def acquire_pipeline(self):
        """Acquire a pipeline instance from the pool"""
        # First acquire concurrency slot
        await self.concurrency_limiter.acquire()

        try:
            # Then acquire pipeline instance
            instance = await self.pipeline_pool.acquire()
            return instance
        except Exception as e:
            # Release concurrency slot if pipeline acquisition fails
            self.concurrency_limiter.release()
            raise

    def release_pipeline(self, instance: dict):
        """Release a pipeline instance back to the pool"""
        self.pipeline_pool.release(instance)
        self.concurrency_limiter.release()

    @property
    def active_requests(self) -> int:
        """Get number of active requests"""
        return self.concurrency_limiter.active_count

    def _load_config(self) -> DictConfig:
        """Load Hydra configuration"""
        # Get config directory
        config_dir = Path(__file__).parent.parent.parent / "miroflow-agent" / "conf"
        config_dir = config_dir.resolve()

        if not config_dir.exists():
            raise FileNotFoundError(f"Config directory not found: {config_dir}")

        # Initialize Hydra
        try:
            initialize_config_dir(config_dir=str(config_dir), version_base=None)
        except Exception as e:
            logger.debug(f"Hydra already initialized: {e}")

        # Compose configuration with environment variable overrides
        overrides = self._build_config_overrides()

        try:
            cfg = compose(config_name="config", overrides=overrides)
            return cfg
        except Exception as e:
            logger.error(f"Failed to compose config: {e}")
            raise

    def _build_config_overrides(self):
        """Build configuration overrides from environment variables"""
        overrides = []

        # LLM configuration
        llm_provider = os.getenv("DEFAULT_LLM_PROVIDER", "qwen")
        model_name = os.getenv("DEFAULT_MODEL_NAME", "MiroThinker")
        agent_set = os.getenv("DEFAULT_AGENT_SET", "demo")
        base_url = os.getenv("BASE_URL", "http://localhost:11434")
        api_key = os.getenv("API_KEY", "")

        # Map provider to config file
        provider_config_map = {
            "anthropic": "claude-3-7",
            "openai": "gpt-5",
            "qwen": "qwen-3",
        }
        llm_config = provider_config_map.get(llm_provider, "qwen-3")

        overrides.extend(
            [
                f"llm={llm_config}",
                f"agent={agent_set}",
                f"llm.model_name={model_name}",
                f"llm.base_url={base_url}",
                f"llm.api_key={api_key}",
            ]
        )

        logger.debug(f"Config overrides: {overrides}")
        return overrides

    def is_initialized(self) -> bool:
        """Check if pipeline is initialized"""
        return self._initialized

