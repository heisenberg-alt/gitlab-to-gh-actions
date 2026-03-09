"""Tests for async_utils shared helper."""

import asyncio

import pytest

from gl2gh.utils.async_utils import run_async


class TestRunAsync:
    def test_runs_simple_coroutine(self):
        async def add(a, b):
            return a + b

        assert run_async(add(2, 3)) == 5

    def test_runs_async_sleep(self):
        async def nap():
            await asyncio.sleep(0)
            return "awake"

        assert run_async(nap()) == "awake"

    def test_returns_none(self):
        async def noop():
            pass

        assert run_async(noop()) is None

    def test_propagates_exception(self):
        async def boom():
            raise ValueError("kaboom")

        with pytest.raises(ValueError, match="kaboom"):
            run_async(boom())

    def test_runs_inside_event_loop(self):
        """When already inside a running loop,
        run_async should use ThreadPoolExecutor."""
        result = None

        async def outer():
            nonlocal result
            async def inner():
                return 42
            result = run_async(inner())

        asyncio.run(outer())
        assert result == 42
