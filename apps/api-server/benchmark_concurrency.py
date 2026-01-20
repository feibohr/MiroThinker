"""
Concurrency Benchmark for MiroThinker API
"""

import asyncio
import time
from typing import List

import httpx


async def single_request(client: httpx.AsyncClient, query: str, request_id: int):
    """Send a single request and measure time"""
    url = "http://localhost:8000/v1/chat/completions"

    payload = {
        "model": "mirothinker",
        "messages": [{"role": "user", "content": query}],
        "stream": False,  # Non-streaming for easier timing
    }

    start_time = time.time()
    try:
        response = await client.post(url, json=payload, timeout=300.0)
        end_time = time.time()

        duration = end_time - start_time
        status = response.status_code

        return {
            "request_id": request_id,
            "duration": duration,
            "status": status,
            "success": status == 200,
        }
    except Exception as e:
        end_time = time.time()
        return {
            "request_id": request_id,
            "duration": end_time - start_time,
            "status": "error",
            "success": False,
            "error": str(e),
        }


async def benchmark_sequential(num_requests: int, query: str):
    """Benchmark sequential requests"""
    print(f"\n{'=' * 60}")
    print(f"Sequential Benchmark: {num_requests} requests")
    print(f"{'=' * 60}")

    results = []
    start_time = time.time()

    async with httpx.AsyncClient() as client:
        for i in range(num_requests):
            print(f"  Request {i+1}/{num_requests}...", end="", flush=True)
            result = await single_request(client, query, i + 1)
            results.append(result)
            print(f" ✓ {result['duration']:.2f}s")

    total_time = time.time() - start_time

    # Summary
    successful = [r for r in results if r["success"]]
    print(f"\n{'=' * 60}")
    print(f"Total time: {total_time:.2f}s")
    print(f"Success rate: {len(successful)}/{num_requests}")
    print(f"Avg time per request: {total_time / num_requests:.2f}s")
    print(f"{'=' * 60}\n")

    return results, total_time


async def benchmark_concurrent(num_requests: int, query: str):
    """Benchmark concurrent requests"""
    print(f"\n{'=' * 60}")
    print(f"Concurrent Benchmark: {num_requests} requests")
    print(f"{'=' * 60}")

    start_time = time.time()

    async with httpx.AsyncClient() as client:
        tasks = [
            single_request(client, query, i + 1) for i in range(num_requests)
        ]
        results = await asyncio.gather(*tasks)

    total_time = time.time() - start_time

    # Summary
    successful = [r for r in results if r["success"]]
    durations = [r["duration"] for r in successful]

    print(f"\n{'=' * 60}")
    print(f"Total time: {total_time:.2f}s")
    print(f"Success rate: {len(successful)}/{num_requests}")
    if durations:
        print(f"Avg request duration: {sum(durations) / len(durations):.2f}s")
        print(f"Min request duration: {min(durations):.2f}s")
        print(f"Max request duration: {max(durations):.2f}s")
    print(f"Throughput: {num_requests / total_time:.2f} req/s")
    print(f"{'=' * 60}\n")

    return results, total_time


async def compare_benchmarks():
    """Compare sequential vs concurrent performance"""
    # Use a simple query for faster testing
    query = "What is 2+2?"
    num_requests = 3

    print("\n" + "=" * 60)
    print("MiroThinker API Concurrency Benchmark")
    print("=" * 60)
    print(f"Query: {query}")
    print(f"Number of requests: {num_requests}")

    # Test 1: Sequential
    seq_results, seq_time = await benchmark_sequential(num_requests, query)

    # Test 2: Concurrent
    con_results, con_time = await benchmark_concurrent(num_requests, query)

    # Comparison
    print("\n" + "=" * 60)
    print("COMPARISON")
    print("=" * 60)
    print(f"Sequential total time: {seq_time:.2f}s")
    print(f"Concurrent total time: {con_time:.2f}s")
    print(f"Speedup: {seq_time / con_time:.2f}x")

    if con_time >= seq_time * 0.8:
        print("\n⚠️  WARNING: Concurrent requests are NOT faster!")
        print("   Possible bottlenecks:")
        print("   - Shared Pipeline components")
        print("   - LLM API rate limiting")
        print("   - Tool execution serialization")
        print("   - E2B sandbox creation limits")
    else:
        print("\n✅ Concurrent requests show good speedup!")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(compare_benchmarks())

