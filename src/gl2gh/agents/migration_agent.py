"""Migration Agent - GitHub Copilot SDK with tool use for CI migration."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from pydantic import BaseModel, Field

from gl2gh.converter import GitLabToGitHubConverter
from gl2gh.models import ConversionResult, GitLabPipeline
from gl2gh.utils.yaml_utils import add_yaml_header, validate_yaml_syntax

logger = logging.getLogger(__name__)


# --- Pydantic tool input models ---


class ValidateYamlInput(BaseModel):
    yaml_content: str = Field(..., description="The YAML content to validate")


class SaveWorkflowInput(BaseModel):
    yaml_content: str = Field(..., description="The workflow YAML content to save")
    filename: str = Field(..., description="Output filename for the workflow")
    notes: list[str] = Field(default_factory=list, description="Conversion notes")
    warnings: list[str] = Field(default_factory=list, description="Warning messages")
    manual_review_items: list[str] = Field(
        default_factory=list, description="Items needing manual review"
    )


class AddWarningInput(BaseModel):
    message: str = Field(..., description="Warning message to add")


class AddConversionNoteInput(BaseModel):
    note: str = Field(..., description="Conversion note to add")


class MigrationAgent:
    """Copilot-powered agent for GitLab CI -> GitHub Actions migration.

    Uses the GitHub Copilot SDK with tool use to:
    1. Analyze the GitLab CI pipeline structure
    2. Identify complex patterns that need AI assistance
    3. Generate optimal GitHub Actions workflows
    4. Validate and fix the output
    """

    SYSTEM_PROMPT = (
        "You are an expert DevOps engineer specializing in "
        "CI/CD pipeline migration.\n"
        "Your task is to migrate GitLab CI/CD pipelines to "
        "GitHub Actions workflows.\n\n"
        "Key principles:\n"
        "1. Preserve all functionality from the original pipeline\n"
        "2. Use GitHub Actions best practices "
        "(checkout@v4, cache@v4, etc.)\n"
        "3. Map GitLab CI variables to GitHub Actions contexts "
        "correctly\n"
        "4. Handle complex patterns like templates, includes, "
        "matrix builds\n"
        "5. Add helpful comments explaining migration decisions\n"
        "6. Flag anything that needs manual review\n\n"
        "GitLab -> GitHub variable mappings:\n"
        "- $CI_COMMIT_SHA -> ${{ github.sha }}\n"
        "- $CI_COMMIT_REF_NAME -> ${{ github.ref_name }}\n"
        "- $CI_PROJECT_PATH -> ${{ github.repository }}\n"
        "- $CI_REGISTRY -> ghcr.io\n"
        "- $CI_REGISTRY_IMAGE -> ghcr.io/${{ github.repository }}\n"
        "- $CI_REGISTRY_USER -> ${{ github.actor }}\n"
        "- $CI_REGISTRY_PASSWORD -> ${{ secrets.GITHUB_TOKEN }}\n"
        "- $CI_PIPELINE_ID -> ${{ github.run_id }}\n\n"
        "Always output valid GitHub Actions YAML. "
        "Use tools to validate your work."
    )

    def __init__(
        self,
        github_token: Optional[str] = None,
        model: str = "gpt-4.1",
    ) -> None:
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN", "")
        self.model = model
        self._converter = GitLabToGitHubConverter()

    def migrate(
        self,
        pipeline: GitLabPipeline,
        source_file: str = ".gitlab-ci.yml",
        workflow_name: str = "CI",
    ) -> ConversionResult:
        """Migrate a parsed GitLabPipeline using GitHub Copilot AI.
        Falls back to rule-based conversion if AI fails."""
        self._converter = GitLabToGitHubConverter(
            workflow_name=workflow_name,
            source_file=source_file,
        )

        base_result = self._converter.convert(pipeline)

        needs_ai = (
            len(base_result.warnings) > 0
            or len(base_result.unsupported_features) > 0
            or any(
                job.rules or job.parallel or job.extends
                for job in pipeline.jobs.values()
            )
        )

        if not needs_ai and base_result.success:
            return base_result

        try:
            enhanced: ConversionResult = asyncio.run(
                self._run_ai_migration(
                    pipeline, base_result, source_file, workflow_name
                )
            )
            enhanced.ai_enhanced = True
            return enhanced
        except Exception as exc:
            logger.warning("AI migration failed, using rule-based result: %s", exc)
            base_result.warnings.append(
                f"AI enhancement failed ({exc}); using rule-based conversion."
            )
            return base_result

    def migrate_repository(
        self,
        source_repo: str,
        target_repo: str,
        branch: str = "main",
    ) -> bool:
        """Full repository migration using streaming GitHub Copilot."""
        try:
            success: bool = asyncio.run(
                self._migrate_repository_async(source_repo, target_repo, branch)
            )
            return success
        except Exception as exc:
            logger.error("Repository migration failed: %s", exc)
            return False

    async def _migrate_repository_async(
        self, source_repo: str, target_repo: str, branch: str
    ) -> bool:
        from copilot import CopilotClient

        client = CopilotClient({"github_token": self.github_token, "auto_start": True})
        await client.start()

        session = await client.create_session(
            {
                "model": self.model,
                "streaming": True,
                "system_message": self.SYSTEM_PROMPT,  # type: ignore[typeddict-item]
            }
        )

        msg = (
            f"Help plan a GitLab to GitHub repository migration.\n"
            f"Source: {source_repo}\n"
            f"Target: {target_repo}\n"
            f"Branch: {branch}\n\n"
            f"Steps: 1. Clone repo 2. Find all .gitlab-ci.yml "
            f"3. Convert to GitHub Actions 4. Push to GitHub"
        )

        collected_text: list[str] = []
        done = asyncio.Event()

        def on_event(event):
            t = event.type.value
            if t == "assistant.message_delta":
                text = event.data.delta_content or ""
                print(text, end="", flush=True)
                collected_text.append(text)
            elif t == "session.idle":
                done.set()

        session.on(on_event)
        await session.send({"prompt": msg})
        await done.wait()
        print()

        await session.destroy()
        await client.stop()
        return len(collected_text) > 0

    async def _run_ai_migration(
        self,
        pipeline: GitLabPipeline,
        base_result: ConversionResult,
        source_file: str,
        workflow_name: str,
    ) -> ConversionResult:
        from copilot import CopilotClient, define_tool

        summary = self._summarize_pipeline(pipeline)
        base_wf = (
            list(base_result.output_workflows.values())[0]
            if base_result.output_workflows
            else ""
        )
        warns = "\n".join(base_result.warnings) or "none"
        unsup = "\n".join(base_result.unsupported_features) or "none"

        user_msg = (
            f"Review and improve this GitLab CI to GitHub Actions migration.\n\n"
            f"## Source Pipeline\n{summary}\n\n"
            f"## Rule-based Output\n```yaml\n{base_wf}\n```\n\n"
            f"## Warnings\n{warns}\n\n"
            f"## Unsupported\n{unsup}\n\n"
            f"Fix issues, handle unsupported features, optimize, "
            f"and save using save_workflow tool."
        )

        result = ConversionResult(source_file=source_file)

        # Define tools as closures that capture `result` and `workflow_name`
        @define_tool(description="Validate GitHub Actions YAML syntax")
        async def validate_yaml(params: ValidateYamlInput) -> str:
            err = validate_yaml_syntax(params.yaml_content)
            if err:
                return json.dumps({"valid": False, "error": err})
            return json.dumps({"valid": True})

        @define_tool(description="Save final GitHub Actions workflow after validation")
        async def save_workflow(params: SaveWorkflowInput) -> str:
            err = validate_yaml_syntax(params.yaml_content)
            if err:
                return json.dumps({"success": False, "error": f"Invalid YAML: {err}"})
            fname = params.filename or f"{workflow_name.lower()}.yml"
            result.output_workflows[fname] = add_yaml_header(
                params.yaml_content, result.source_file
            )
            result.conversion_notes.extend(params.notes)
            result.warnings.extend(params.warnings)
            for item in params.manual_review_items:
                result.conversion_notes.append(f"Manual review: {item}")
            return json.dumps({"success": True, "filename": fname})

        @define_tool(description="Add a migration warning")
        async def add_warning(params: AddWarningInput) -> str:
            result.warnings.append(params.message)
            return json.dumps({"added": True})

        @define_tool(description="Add a conversion note")
        async def add_conversion_note(params: AddConversionNoteInput) -> str:
            result.conversion_notes.append(params.note)
            return json.dumps({"added": True})

        client = CopilotClient({"github_token": self.github_token, "auto_start": True})
        await client.start()

        session = await client.create_session(
            {
                "model": self.model,
                "streaming": False,
                "tools": [
                    validate_yaml,
                    save_workflow,
                    add_warning,
                    add_conversion_note,
                ],
                "system_message": self.SYSTEM_PROMPT,  # type: ignore[typeddict-item]
            }
        )

        done = asyncio.Event()

        def on_event(event):
            if event.type.value == "session.idle":
                done.set()

        session.on(on_event)
        await session.send({"prompt": user_msg})
        await done.wait()

        await session.destroy()
        await client.stop()

        if not result.output_workflows:
            result = base_result
        return result

    def _summarize_pipeline(self, pipeline: GitLabPipeline) -> str:
        jobs = [j for j in pipeline.jobs.values() if not j.is_template]
        templates = [j for j in pipeline.jobs.values() if j.is_template]
        lines = [
            f"Stages: {', '.join(pipeline.stages)}",
            f"Jobs: {len(jobs)}",
            f"Templates: {len(templates)}",
            f"Global vars: {len(pipeline.variables)}",
        ]
        if pipeline.default_image:
            lines.append(f"Default image: {pipeline.default_image}")
        lines.append("\nJobs:")
        for job in jobs:
            feats = []
            if job.rules:
                feats.append("rules")
            if job.parallel:
                feats.append("parallel")
            if job.extends:
                feats.append(f"extends({','.join(job.extends)})")
            if job.environment:
                feats.append(f"env:{job.environment.name}")
            feat_str = f" [{', '.join(feats)}]" if feats else ""
            lines.append(f"  - {job.name} (stage:{job.stage}){feat_str}")
        return "\n".join(lines)
