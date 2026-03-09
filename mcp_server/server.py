"""gl2gh MCP Server — GitLab CI RAG for accurate pipeline conversion.

Exposes tools via the Model Context Protocol (MCP) that allow AI agents
to search GitLab CI patterns, retrieve conversion examples, validate
outputs against a corpus, and get GitHub Action suggestions.

Run with:
    python -m mcp_server.server

Or configure in VS Code / Claude Desktop settings.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
)

# Add parent to path so we can import mcp_server modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_server.embeddings import VectorStore, build_index_from_disk
from mcp_server.tools.handlers import (
    ConversionExampleTool,
    PatternSearchTool,
    SuggestGitHubActionTool,
    ValidateAgainstCorpusTool,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP Server Definition
# ---------------------------------------------------------------------------

server = Server("gl2gh-gitlab-ci-rag")

# Lazy-init: build vector store on first tool call
_store: VectorStore | None = None


def _get_store() -> VectorStore:
    global _store
    if _store is None:
        _store = build_index_from_disk()
    return _store


# ---------------------------------------------------------------------------
# Tool Listing
# ---------------------------------------------------------------------------

TOOLS = [
    Tool(
        name="find_similar_gitlab_pattern",
        description=(
            "Search the GitLab CI corpus for patterns similar to the provided "
            "YAML snippet. Returns matching files with similarity scores, "
            "detected patterns, and content previews. Use this when converting "
            "a GitLab CI job and you want to see how similar patterns were "
            "structured in real-world projects."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "snippet": {
                    "type": "string",
                    "description": "A GitLab CI YAML snippet (a job definition, rule block, etc.)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5)",
                    "default": 5,
                },
                "pattern_filter": {
                    "type": "string",
                    "description": "Optional: filter results to those containing this pattern (e.g., 'docker_build', 'services', 'rules')",
                },
            },
            "required": ["snippet"],
        },
    ),
    Tool(
        name="get_conversion_example",
        description=(
            "Given a GitLab CI/CD feature name, retrieve real-world before/after "
            "conversion examples showing the GitLab CI YAML alongside the "
            "equivalent GitHub Actions workflow. Use this when you need a reference "
            "for how to convert a specific GitLab CI feature."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "feature": {
                    "type": "string",
                    "description": "The GitLab CI feature to find examples for (e.g., 'rules:if', 'services', 'cache', 'parallel:matrix', 'extends', 'include')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of examples (default: 3)",
                    "default": 3,
                },
            },
            "required": ["feature"],
        },
    ),
    Tool(
        name="validate_against_corpus",
        description=(
            "Validate a GitLab CI -> GitHub Actions conversion by checking "
            "it against known patterns in the corpus. Returns a confidence "
            "score, warnings about missing features, and suggestions. "
            "Use this after generating a GitHub Actions workflow to verify "
            "conversion completeness."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "gitlab_ci": {
                    "type": "string",
                    "description": "The original GitLab CI YAML content",
                },
                "github_actions": {
                    "type": "string",
                    "description": "The generated GitHub Actions YAML content",
                },
            },
            "required": ["gitlab_ci", "github_actions"],
        },
    ),
    Tool(
        name="suggest_github_action",
        description=(
            "Given a GitLab CI job snippet, suggest appropriate GitHub Actions "
            "marketplace actions to use in the conversion. Analyzes the job's "
            "patterns (Docker build, caching, testing, deployment, etc.) and "
            "returns curated action recommendations with version pins."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "gitlab_snippet": {
                    "type": "string",
                    "description": "A GitLab CI job YAML snippet to analyze",
                },
            },
            "required": ["gitlab_snippet"],
        },
    ),
    Tool(
        name="index_stats",
        description=(
            "Return statistics about the indexed GitLab CI corpus: total "
            "documents, conversion pairs available, storage info."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


# ---------------------------------------------------------------------------
# Tool Execution
# ---------------------------------------------------------------------------


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    store = _get_store()

    if name == "find_similar_gitlab_pattern":
        tool = PatternSearchTool(store)
        result = tool.run(
            snippet=arguments["snippet"],
            limit=arguments.get("limit", 5),
            pattern_filter=arguments.get("pattern_filter"),
        )

    elif name == "get_conversion_example":
        tool = ConversionExampleTool(store)
        result = tool.run(
            feature=arguments["feature"],
            limit=arguments.get("limit", 3),
        )

    elif name == "validate_against_corpus":
        tool = ValidateAgainstCorpusTool(store)
        result = tool.run(
            gitlab_ci=arguments["gitlab_ci"],
            github_actions=arguments["github_actions"],
        )

    elif name == "suggest_github_action":
        tool = SuggestGitHubActionTool(store)
        result = tool.run(
            gitlab_snippet=arguments["gitlab_snippet"],
        )

    elif name == "index_stats":
        result = store.stats()

    else:
        result = {"error": f"Unknown tool: {name}"}

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting gl2gh GitLab CI RAG MCP Server...")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
