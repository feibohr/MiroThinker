"""
Concurrency Manager
Manages concurrent request execution with resource pooling and rate limiting
"""

import asyncio
import logging
from typing import Optional

from src.core.pipeline import create_pipeline_components

logger = logging.getLogger(__name__)


class PipelinePool:
    """
    Pipeline component pool for concurrent request handling.

    Creates multiple independent Pipeline instances to avoid resource contention.
    """

    def __init__(self, cfg, pool_size: int = 5):
        """
        Initialize pipeline pool.

        Args:
            cfg: Hydra configuration
            pool_size: Number of pipeline instances in the pool
        """
        self.cfg = cfg
        self.pool_size = pool_size
        self.pool = []
        self._semaphore = asyncio.Semaphore(pool_size)
        self._initialized = False

    async def initialize(self):
        """Initialize the pool"""
        if self._initialized:
            return

        logger.info(f"Initializing pipeline pool with {self.pool_size} instances...")

        for i in range(self.pool_size):
            try:
                (
                    main_agent_tool_manager,
                    sub_agent_tool_managers,
                    output_formatter,
                ) = create_pipeline_components(self.cfg)

                # Get tool definitions
                tool_definitions = (
                    await main_agent_tool_manager.get_all_tool_definitions()
                )

                # Get sub-agent tool definitions if any
                sub_agent_tool_definitions = {}
                if sub_agent_tool_managers:
                    for name, manager in sub_agent_tool_managers.items():
                        sub_agent_tool_definitions[name] = (
                            await manager.get_all_tool_definitions()
                        )

                self.pool.append(
                    {
                        "id": i,
                        "main_agent_tool_manager": main_agent_tool_manager,
                        "sub_agent_tool_managers": sub_agent_tool_managers,
                        "output_formatter": output_formatter,
                        "tool_definitions": tool_definitions,
                        "sub_agent_tool_definitions": sub_agent_tool_definitions,
                        "in_use": False,
                    }
                )

                logger.info(f"  Pipeline instance {i+1}/{self.pool_size} initialized")

            except Exception as e:
                logger.error(f"Failed to initialize pipeline instance {i}: {e}")
                raise

        self._initialized = True
        logger.info(f"✅ Pipeline pool initialized with {len(self.pool)} instances")

    async def acquire(self):
        """
        Acquire a pipeline instance from the pool.

        This will block if all instances are in use until one becomes available.
        """
        await self._semaphore.acquire()

        # Find an available instance
        for instance in self.pool:
            if not instance["in_use"]:
                instance["in_use"] = True
                logger.debug(f"Acquired pipeline instance {instance['id']}")
                return instance

        # Should not reach here if semaphore works correctly
        raise RuntimeError("No available pipeline instance (semaphore error)")

    def release(self, instance: dict):
        """Release a pipeline instance back to the pool"""
        instance["in_use"] = False
        self._semaphore.release()
        logger.debug(f"Released pipeline instance {instance['id']}")

    async def cleanup(self):
        """Cleanup all pipeline instances"""
        logger.info("Cleaning up pipeline pool...")
        # Add cleanup logic if needed
        self.pool.clear()
        self._initialized = False


class ConcurrencyLimiter:
    """
    Global concurrency limiter to prevent overwhelming the system.

    Limits the total number of concurrent requests being processed.
    """

    def __init__(self, max_concurrent: int = 10):
        """
        Initialize concurrency limiter.

        Args:
            max_concurrent: Maximum number of concurrent requests
        """
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_count = 0

    async def acquire(self):
        """Acquire a slot for processing"""
        await self._semaphore.acquire()
        self._active_count += 1
        logger.info(
            f"Concurrency: {self._active_count}/{self.max_concurrent} active requests"
        )

    def release(self):
        """Release a processing slot"""
        self._active_count -= 1
        self._semaphore.release()
        logger.info(
            f"Concurrency: {self._active_count}/{self.max_concurrent} active requests"
        )

    @property
    def active_count(self) -> int:
        """Get current number of active requests"""
        return self._active_count

