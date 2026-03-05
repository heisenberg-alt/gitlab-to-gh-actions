"""Validator agent for GitHub Actions workflow files."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    severity: str  # "error", "warning", "info"
    message: str
    line: Optional[int] = None


class ValidatorAgent:
    """Validates generated GitHub Actions workflow files."""

    REQUIRED_TOP_LEVEL = {"name", "on", "jobs"}
    REQUIRED_JOB_KEYS = {"runs-on", "steps"}
    SECURITY_PATTERNS = [
        (
            "${{ github.event.pull_request.head.ref }}",
            "Potential script injection via PR head ref",
        ),
        (
            "${{ github.event.issue.title }}",
            "Potential script injection via issue title",
        ),
        ("${{ github.event.issue.body }}", "Potential script injection via issue body"),
        (
            "${{ github.event.comment.body }}",
            "Potential script injection via comment body",
        ),
    ]

    def validate_static(self, content: str) -> list[ValidationIssue]:
        """Run static validation checks on a workflow YAML string."""
        issues: list[ValidationIssue] = []

        try:
            workflow = yaml.safe_load(content)
        except yaml.YAMLError as e:
            issues.append(ValidationIssue("error", f"Invalid YAML syntax: {e}"))
            return issues

        if not isinstance(workflow, dict):
            issues.append(ValidationIssue("error", "Workflow must be a YAML mapping"))
            return issues

        for key in self.REQUIRED_TOP_LEVEL:
            if key not in workflow:
                issues.append(
                    ValidationIssue("error", f"Missing required top-level key: '{key}'")
                )

        on_val = workflow.get("on")
        if on_val is not None:
            if not isinstance(on_val, (dict, list, str)):
                issues.append(
                    ValidationIssue("error", "'on' must be a mapping, list, or string")
                )

        jobs = workflow.get("jobs")
        if isinstance(jobs, dict):
            for job_name, job_def in jobs.items():
                issues.extend(self._validate_job(job_name, job_def))
        elif jobs is not None:
            issues.append(ValidationIssue("error", "'jobs' must be a mapping"))

        for pattern, msg in self.SECURITY_PATTERNS:
            if pattern in content:
                issues.append(ValidationIssue("warning", f"Security: {msg}"))

        return issues

    def _validate_job(self, name: str, job_def: Any) -> list[ValidationIssue]:
        """Validate a single job definition."""
        issues: list[ValidationIssue] = []

        if not isinstance(job_def, dict):
            issues.append(ValidationIssue("error", f"Job '{name}' must be a mapping"))
            return issues

        for key in self.REQUIRED_JOB_KEYS:
            if key not in job_def:
                issues.append(
                    ValidationIssue(
                        "error", f"Job '{name}' missing required key: '{key}'"
                    )
                )

        steps = job_def.get("steps")
        if isinstance(steps, list):
            for i, step in enumerate(steps):
                if not isinstance(step, dict):
                    issues.append(
                        ValidationIssue(
                            "error", f"Job '{name}' step {i} must be a mapping"
                        )
                    )
                    continue
                if "uses" not in step and "run" not in step:
                    issues.append(
                        ValidationIssue(
                            "warning", f"Job '{name}' step {i} has no 'uses' or 'run'"
                        )
                    )

        runner = job_def.get("runs-on")
        if isinstance(runner, str):
            valid_runners = {
                "ubuntu-latest",
                "ubuntu-22.04",
                "ubuntu-24.04",
                "windows-latest",
                "macos-latest",
                "macos-14",
                "self-hosted",
            }
            if runner not in valid_runners and not runner.startswith("${{"):
                issues.append(
                    ValidationIssue(
                        "info", f"Job '{name}' uses non-standard runner: '{runner}'"
                    )
                )

        return issues

    def validate_with_ai(
        self, content: str, github_token: str, model: str = "gpt-4.1"
    ) -> list[ValidationIssue]:
        """Validate using both static checks and GitHub Copilot AI review."""
        issues = self.validate_static(content)

        try:
            import asyncio

            from copilot import CopilotClient

            async def _ai_validate():
                client = CopilotClient(
                    {"github_token": github_token, "auto_start": True}
                )
                await client.start()
                session = await client.create_session(
                    {"model": model, "streaming": False}
                )

                collected: list[str] = []
                done = asyncio.Event()

                def on_event(event):
                    t = event.type.value
                    if t == "assistant.message_delta":
                        collected.append(event.data.delta_content or "")
                    elif t == "session.idle":
                        done.set()

                session.on(on_event)
                await session.send(
                    {
                        "prompt": (
                            "Review this GitHub Actions workflow for correctness, "
                            "security, and best practices. List each issue as: "
                            "SEVERITY: message (where severity is ERROR, WARNING, "
                            "or INFO).\n\n"
                            "```yaml\n" + content + "\n```"
                        )
                    }
                )
                await done.wait()
                await session.destroy()
                await client.stop()
                return "".join(collected)

            ai_text = asyncio.run(_ai_validate())
            for line in ai_text.split("\n"):
                line = line.strip()
                if line.startswith("ERROR:"):
                    issues.append(ValidationIssue("error", line[6:].strip()))
                elif line.startswith("WARNING:"):
                    issues.append(ValidationIssue("warning", line[8:].strip()))
                elif line.startswith("INFO:"):
                    issues.append(ValidationIssue("info", line[5:].strip()))

        except Exception as e:
            logger.warning("AI validation failed: %s", e)
            issues.append(ValidationIssue("info", f"AI review unavailable: {e}"))

        return issues
