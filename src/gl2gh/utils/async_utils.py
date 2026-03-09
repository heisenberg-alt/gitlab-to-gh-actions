"""Async helpers shared across agent modules."""

from __future__ import annotations

import asyncio


def run_async(coro):
    """Run a coroutine, handling the case where an event loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already inside an event loop — create a new thread to avoid RuntimeError
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
