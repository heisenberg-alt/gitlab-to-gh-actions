"""Optimizer agent for improving generated GitHub Actions workflows."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import yaml

from gl2gh.utils.async_utils import run_async as _run_async

logger = logging.getLogger(__name__)


@dataclass
class Optimization:
    category: str
    description: str
    before: Optional[str] = None
    after: Optional[str] = None


@dataclass
class OptimizationReport:
    optimizations: list[Optimization] = field(default_factory=list)
    optimized_content: Optional[str] = None
    score_before: int = 0
    score_after: int = 0


class OptimizerAgent:
    """Analyzes and optimizes GitHub Actions workflows."""

    def optimize(self, content: str) -> OptimizationReport:
        """Run static optimization analysis on a workflow."""
        report = OptimizationReport()

        try:
            workflow = yaml.safe_load(content)
        except yaml.YAMLError:
            return report

        if not isinstance(workflow, dict):
            return report

        jobs = workflow.get("jobs", {})
        if not isinstance(jobs, dict):
            return report

        report.score_before = self._score_workflow(workflow)
        self._check_caching(jobs, report)
        self._check_parallelism(jobs, report)
        self._check_checkout(jobs, report)
        self._check_concurrency(workflow, report)
        self._check_timeout(jobs, report)
        report.score_after = report.score_before + len(report.optimizations) * 5
        return report

    def optimize_with_ai(
        self, content: str, github_token: str, model: str = "gpt-4.1"
    ) -> OptimizationReport:
        """Optimize using GitHub Copilot AI for deeper analysis."""
        report = self.optimize(content)
        try:
            from copilot import CopilotClient

            async def _ai_optimize():
                client = CopilotClient(
                    {"github_token": github_token, "auto_start": True}
                )
                await client.start()
                session = await client.create_session(
                    {"model": model, "streaming": True}
                )

                full_text_parts: list[str] = []
                done = asyncio.Event()

                def on_event(event):
                    t = event.type.value
                    if t == "assistant.message_delta":
                        full_text_parts.append(event.data.delta_content or "")
                    elif t == "session.idle":
                        done.set()

                session.on(on_event)
                await session.send(
                    {
                        "prompt": (
                            "Analyze this GitHub Actions workflow and suggest "
                            "optimizations. Focus on: caching, parallelism, "
                            "matrix builds, security, cost savings.\n\n"
                            "```yaml\n" + content + "\n```"
                        )
                    }
                )
                await done.wait()
                await session.destroy()
                await client.stop()
                return "".join(full_text_parts)

            full_text = _run_async(_ai_optimize())
            for line in full_text.split("\n"):
                line = line.strip()
                if line.startswith("- ") and ":" in line:
                    parts = line[2:].split(":", 1)
                    if len(parts) == 2:
                        report.optimizations.append(
                            Optimization(
                                category=parts[0].strip().lower(),
                                description=parts[1].strip(),
                            )
                        )
        except Exception as e:
            logger.warning("AI optimization failed: %s", e)
        return report

    def _score_workflow(self, workflow: dict[str, Any]) -> int:
        score = 50
        jobs = workflow.get("jobs", {})
        if workflow.get("concurrency"):
            score += 10
        if any("cache" in str(job) for job in jobs.values()):
            score += 10
        if any(isinstance(j, dict) and j.get("timeout-minutes") for j in jobs.values()):
            score += 5
        if any(
            isinstance(j, dict) and j.get("strategy", {}).get("matrix")
            for j in jobs.values()
        ):
            score += 5
        return min(score, 100)

    def _check_caching(self, jobs: dict[str, Any], report: OptimizationReport) -> None:
        has_cache = any(
            isinstance(step, dict) and "actions/cache" in str(step.get("uses", ""))
            for job_def in jobs.values()
            if isinstance(job_def, dict)
            for step in job_def.get("steps", [])
        )
        if not has_cache and len(jobs) > 0:
            report.optimizations.append(
                Optimization(
                    category="caching",
                    description=(
                        "No caching detected. Add actions/cache@v4 for dependencies."
                    ),
                )
            )

    def _check_parallelism(
        self, jobs: dict[str, Any], report: OptimizationReport
    ) -> None:
        independent = [
            name
            for name, job in jobs.items()
            if isinstance(job, dict) and not job.get("needs")
        ]
        if len(independent) > 2:
            report.optimizations.append(
                Optimization(
                    category="parallelism",
                    description=(
                        f"{len(independent)} jobs have no "
                        "dependencies - verify this is intentional."
                    ),
                )
            )

    def _check_checkout(self, jobs: dict[str, Any], report: OptimizationReport) -> None:
        for job_name, job_def in jobs.items():
            if not isinstance(job_def, dict):
                continue
            steps = job_def.get("steps", [])
            has_checkout = any(
                isinstance(s, dict) and "actions/checkout" in str(s.get("uses", ""))
                for s in steps
            )
            if not has_checkout:
                report.optimizations.append(
                    Optimization(
                        category="correctness",
                        description=f"Job '{job_name}' has no checkout step.",
                    )
                )

    def _check_concurrency(
        self, workflow: dict[str, Any], report: OptimizationReport
    ) -> None:
        if "concurrency" not in workflow:
            report.optimizations.append(
                Optimization(
                    category="cost",
                    description="Add concurrency group to cancel redundant runs.",
                )
            )

    def _check_timeout(self, jobs: dict[str, Any], report: OptimizationReport) -> None:
        for job_name, job_def in jobs.items():
            if isinstance(job_def, dict) and "timeout-minutes" not in job_def:
                report.optimizations.append(
                    Optimization(
                        category="cost",
                        description=(
                            f"Job '{job_name}' has no timeout (default is 6 hours)."
                        ),
                    )
                )
