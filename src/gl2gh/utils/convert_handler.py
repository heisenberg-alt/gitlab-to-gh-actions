"""Shared conversion handler used by both Flask app and Vercel serverless function."""

from __future__ import annotations

from typing import Any

from gl2gh.converter import GitLabToGitHubConverter
from gl2gh.parser import GitLabCIParser


def convert_gitlab_yaml(content: str) -> dict[str, Any]:
    """Convert GitLab CI YAML content to GitHub Actions workflow.

    Returns a dict with ``success``, ``workflow``/``workflows``/``warnings``/
    ``notes`` on success, or ``errors``/``warnings`` on failure.
    """
    if not content.strip():
        return {"success": False, "errors": ["YAML content is empty."]}

    parser = GitLabCIParser()
    pipeline = parser.parse_string(content)

    conv = GitLabToGitHubConverter(
        workflow_name="CI",
        source_file=".gitlab-ci.yml",
    )
    result = conv.convert(pipeline)

    if result.success:
        return {
            "success": True,
            "workflow": next(iter(result.output_workflows.values()), ""),
            "workflows": result.output_workflows,
            "warnings": result.warnings,
            "notes": result.conversion_notes,
        }
    return {
        "success": False,
        "errors": result.errors,
        "warnings": result.warnings,
    }
