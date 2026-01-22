"""
Stream Handler
Handles streaming events from miroflow-agent pipeline
Migrated from gradio-demo/main.py
"""

import asyncio
import logging
import os
import threading
import time
import uuid
from typing import AsyncGenerator, Optional

from src.core.pipeline import execute_task_pipeline

from .data_filter import DataFilter

logger = logging.getLogger(__name__)


class ThreadSafeAsyncQueue:
    """Thread-safe async queue wrapper (migrated from gradio-demo)"""

    def __init__(self):
        self._queue = asyncio.Queue()
        self._loop = None
        self._closed = False

    def set_loop(self, loop):
        self._loop = loop

    async def put(self, item):
        """Put data safely from any thread"""
        if self._closed:
            return
        await self._queue.put(item)

    def put_nowait_threadsafe(self, item):
        """Put data from other threads"""
        if self._closed or not self._loop:
            return
        self._loop.call_soon_threadsafe(lambda: self._queue.put_nowait(item))

    async def get(self):
        return await self._queue.get()

    def close(self):
        self._closed = True


class StreamHandler:
    """Handles streaming research events with concurrency support"""

    def __init__(self, pipeline_manager):
        self.pipeline_manager = pipeline_manager
        self.data_filter = DataFilter()

    async def stream_research(
        self, task_id: str, query: str
    ) -> AsyncGenerator[dict, None]:
        """
        Stream research events from miroflow-agent pipeline.

        Uses pipeline pool to support concurrent requests.
        """
        workflow_id = task_id
        last_heartbeat_time = time.time()

        # Acquire pipeline instance from pool
        logger.info(f"[PIPELINE] track_id={task_id} | Acquiring pipeline instance...")
        pipeline_instance = await self.pipeline_manager.acquire_pipeline()
        logger.info(
            f"[PIPELINE] track_id={task_id} | Acquired pipeline instance {pipeline_instance['id']}"
        )

        try:
            # Create thread-safe queue
            stream_queue = ThreadSafeAsyncQueue()
            stream_queue.set_loop(asyncio.get_event_loop())

            cancel_event = threading.Event()

            def run_pipeline_in_thread():
                """Run pipeline in separate thread"""
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    class ThreadQueueWrapper:
                        def __init__(self, thread_queue, cancel_event, data_filter):
                            self.thread_queue = thread_queue
                            self.cancel_event = cancel_event
                            self.data_filter = data_filter

                        async def put(self, item):
                            if self.cancel_event.is_set():
                                logger.info("Pipeline cancelled, stopping execution")
                                return
                            # Filter message before putting to queue
                            filtered = self.data_filter.filter_message(item)
                            self.thread_queue.put_nowait_threadsafe(filtered)

                    wrapper_queue = ThreadQueueWrapper(
                        stream_queue, cancel_event, self.data_filter
                    )

                    async def pipeline_with_cancellation():
                        pipeline_task = asyncio.create_task(
                            execute_task_pipeline(
                                cfg=self.pipeline_manager.cfg,
                                task_id=workflow_id,
                                task_description=query,
                                task_file_name=None,
                                main_agent_tool_manager=pipeline_instance[
                                    "main_agent_tool_manager"
                                ],
                                sub_agent_tool_managers=pipeline_instance[
                                    "sub_agent_tool_managers"
                                ],
                                output_formatter=pipeline_instance["output_formatter"],
                                stream_queue=wrapper_queue,
                                log_dir=os.getenv("LOG_DIR", "logs/api-server"),
                                tool_definitions=pipeline_instance["tool_definitions"],
                                sub_agent_tool_definitions=pipeline_instance[
                                    "sub_agent_tool_definitions"
                                ],
                            )
                        )

                        async def check_cancellation():
                            while not cancel_event.is_set():
                                await asyncio.sleep(0.5)
                            logger.info("Cancel event detected, cancelling pipeline")
                            pipeline_task.cancel()

                        cancel_task = asyncio.create_task(check_cancellation())

                        try:
                            done, pending = await asyncio.wait(
                                [pipeline_task, cancel_task],
                                return_when=asyncio.FIRST_COMPLETED,
                            )
                            for task in pending:
                                task.cancel()
                            for task in done:
                                if task == pipeline_task:
                                    try:
                                        await task
                                    except asyncio.CancelledError:
                                        logger.info("Pipeline task was cancelled")
                        except Exception as e:
                            logger.error(f"Pipeline execution error: {e}")
                            pipeline_task.cancel()
                            cancel_task.cancel()

                    loop.run_until_complete(pipeline_with_cancellation())

                except Exception as e:
                    if not cancel_event.is_set():
                        logger.error(f"Pipeline error: {e}", exc_info=True)
                        stream_queue.put_nowait_threadsafe(
                            {
                                "event": "error",
                                "data": {"error": str(e), "workflow_id": workflow_id},
                            }
                        )
                finally:
                    stream_queue.put_nowait_threadsafe(None)
                    if "loop" in locals():
                        loop.close()

            # Start pipeline in thread
            from concurrent.futures import ThreadPoolExecutor

            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(run_pipeline_in_thread)

            try:
                    while True:
                        try:
                            message = await asyncio.wait_for(stream_queue.get(), timeout=0.1)
                            if message is None:
                                logger.info(f"[PIPELINE] track_id={task_id} | Pipeline completed")
                                break
                            yield message

                        except asyncio.TimeoutError:
                            current_time = time.time()
                            # Check if pipeline thread finished
                            if future.done():
                                try:
                                    message = stream_queue._queue.get_nowait()
                                    if message is not None:
                                        yield message
                                        continue
                                except Exception:
                                    break

                            # Send heartbeat every 15 seconds
                            if current_time - last_heartbeat_time >= 15:
                                yield {
                                    "event": "heartbeat",
                                    "data": {
                                        "timestamp": current_time,
                                        "workflow_id": workflow_id,
                                    },
                                }
                                last_heartbeat_time = current_time

            except Exception as e:
                logger.error(f"[STREAM_ERROR] track_id={task_id} | {e}", exc_info=True)
                yield {
                    "event": "error",
                    "data": {
                        "workflow_id": workflow_id,
                        "error": f"Stream error: {str(e)}",
                    },
                }
            finally:
                cancel_event.set()
                stream_queue.close()
                try:
                    future.result(timeout=1.0)
                except Exception:
                    pass
                executor.shutdown(wait=False)

        finally:
            # Always release pipeline instance back to pool
            self.pipeline_manager.release_pipeline(pipeline_instance)
            logger.info(
                f"[PIPELINE] track_id={task_id} | Released pipeline instance {pipeline_instance['id']}"
            )

