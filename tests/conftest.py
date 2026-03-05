"""Shared test fixtures for gl2gh tests."""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "gitlab"


@pytest.fixture
def simple_gitlab_ci() -> str:
    return (FIXTURES_DIR / "simple.yml").read_text()


@pytest.fixture
def complex_gitlab_ci() -> str:
    return (FIXTURES_DIR / "complex.yml").read_text()


@pytest.fixture
def docker_gitlab_ci() -> str:
    return (FIXTURES_DIR / "docker.yml").read_text()
