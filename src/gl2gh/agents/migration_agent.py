"""Migration Agent - Uses Claude claude-opus-4-6 with tool use to migrate GitLab CI to GitHub Actions."""

from __future__ import annotations
import json
import logging
import os
from typing import Any, Optional

import anthropic

from gl2gh.models import ConversionResult, GitLabPipeline
from gl2gh.converter import GitLabToGitHubConverter
from gl2gh.utils.yaml_utils import add_yaml_header, validate_yaml_syntax

logger = logging.getLogger(__name__)


class MigrationAgent:
    """Claude-powered migration agent for complex GitLab CI -> GitHub Actions conversions.

    Uses claude-opus-4-6 with adaptive thinking and tool use to:
    1. Analyze the GitLab CI pipeline structure
    2. Identify complex patterns that need AI assistance
    3. Generate optimal GitHub Actions workflows
    4. Validate and fix the output
    """

    SYSTEM_PROMPT = """You are an expert DevOps engineer specializing in CI/CD pipeline migration.
Your task is to migrate GitLab CI/CD pipelines to GitHub Actions workflows.

Key principles:
1. Preserve all functionality from the original pipeline
2. Use GitHub Actions best practices (checkout@v4, cache@v4, etc.)
3. Map GitLab CI variables to GitHub Actions contexts correctly
4. Handle complex patterns like templates, includes, matrix builds
5. Add helpful comments explaining migration decisions
6. Flag anything that needs manual review

GitLab -> GitHub variable mappings:
- $CI_COMMIT_SHA -> ${{ github.sha }}
- $CI_COMMIT_REF_NAME -> ${{ github.ref_name }}
- $CI_PROJECT_PATH -> ${{ github.repository }}
- $CI_REGISTRY -> ghcr.io
- $CI_REGISTRY_IMAGE -> ghcr.io/${{ github.repository }}
- $CI_REGISTRY_USER -> ${{ github.actor }}
- $CI_REGISTRY_PASSWORD -> ${{ secrets.GITHUB_TOKEN }}
- $CI_PIPELINE_ID -> ${{ github.run_id }}

Always output valid GitHub Actions YAML. Use tools to validate your work."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-opus-4-6",
    ) -> None:
        self.client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        self.model = model
        self._converter = GitLabToGitHubConverter()

    def migrate(
        self,
        pipeline: GitLabPipeline,
        source_file: str = ".gitlab-ci.yml",
        workflow_name: str = "CI",
    ) -> ConversionResult:
        """Migrate a parsed GitLabPipeline using Claude AI.
        Falls back to rule-based conversion if AI fails."""
        self._converter = GitLabToGitHubConverter(
            workflow_name=workflow_name,
            source_file=source_file,
        )

        base_result = self._converter.convert(pipeline)

        needs_ai = (
            len(base_result.warnings) > 0
            or len(base_result.unsupported_features) > 0
            or any(job.rules or job.parallel or job.extends for job in pipeline.jobs.values())
        )

        if not needs_ai and base_result.success:
            return base_result

        try:
            enhanced = self._run_ai_migration(pipeline, base_result, source_file, workflow_name)
            enhanced.ai_enhanced = True
            return enhanced
        except Exception as exc:
            logger.warning("AI migration failed, using rule-based result: %s", exc)
            base_result.warnings.append(f"AI enhancement failed ({exc}); using rule-based conversion.")
            return base_result

    def migrate_repository(
        self,
        source_repo: str,
        target_repo: str,
        branch: str = "main",
    ) -> bool:
        """Full repository migration using streaming Claude."""
        try:
            msg = f"""Help plan a GitLab to GitHub repository migration.
Source: {source_repo}
Target: {target_repo}
Branch: {branch}

Steps: 1. Clone repo 2. Find all .gitlab-ci.yml 3. Convert to GitHub Actions 4. Push to GitHub"""

            with self.client.messages.stream(
                model=self.model,
                max_tokens=4096,
                thinking={"type": "adaptive"},
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": msg}],
            ) as stream:
                for text in stream.text_stream:
                    print(text, end="", flush=True)
                final = stream.get_final_message()
            print()
            return final.stop_reason == "end_turn"
        except Exception as exc:
            logger.error("Repository migration failed: %s", exc)
            return False

    def _run_ai_migration(self, pipeline, base_result, source_file, workflow_name):
        summary = self._summarize_pipeline(pipeline)
        base_wf = list(base_result.output_workflows.values())[0] if base_result.output_workflows else ""
        warns = "\n".join(base_result.warnings) or "none"
        unsup = "\n".join(base_result.unsupported_features) or "none"

        user_msg = f"""Review and improve this GitLab CI to GitHub Actions migration.

## Source Pipeline
{summary}

## Rule-based Output
```yaml
{base_wf}
```

## Warnings
{warns}

## Unsupported
{unsup}

Fix issues, handle unsupported features, optimize, and save using save_workflow tool."""

        messages: list[dict[str, Any]] = [{"role": "user", "content": user_msg}]
        tools = self._get_tools()
        result = ConversionResult(source_file=source_file)

        for _ in range(8):
            response = self.client.messages.create(
                model=self.model, max_tokens=8192,
                thinking={"type": "adaptive"},
                system=self.SYSTEM_PROMPT, tools=tools, messages=messages,
            )

            if response.stop_reason == "end_turn":
                break
            if response.stop_reason != "tool_use":
                break

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                tr = self._execute_tool(block.name, block.input, result, workflow_name)
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": tr})
            messages.append({"role": "user", "content": tool_results})

        if not result.output_workflows:
            result = base_result
        return result

    def _execute_tool(self, name, inp, result, wf_name):
        try:
            if name == "validate_yaml":
                err = validate_yaml_syntax(inp.get("yaml_content", ""))
                return json.dumps({"valid": not err, "error": err} if err else {"valid": True})
            elif name == "save_workflow":
                content = inp.get("yaml_content", "")
                fname = inp.get("filename", f"{wf_name.lower()}.yml")
                err = validate_yaml_syntax(content)
                if err:
                    return json.dumps({"success": False, "error": f"Invalid YAML: {err}"})
                result.output_workflows[fname] = add_yaml_header(content, result.source_file)
                result.conversion_notes.extend(inp.get("notes", []))
                result.warnings.extend(inp.get("warnings", []))
                for item in inp.get("manual_review_items", []):
                    result.conversion_notes.append(f"Manual review: {item}")
                return json.dumps({"success": True, "filename": fname})
            elif name == "add_warning":
                result.warnings.append(inp.get("message", ""))
                return json.dumps({"added": True})
            elif name == "add_conversion_note":
                result.conversion_notes.append(inp.get("note", ""))
                return json.dumps({"added": True})
            return json.dumps({"error": f"Unknown tool: {name}"})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def _get_tools(self):
        return [
            {"name": "validate_yaml", "description": "Validate GitHub Actions YAML",
             "input_schema": {"type": "object", "properties": {"yaml_content": {"type": "string"}}, "required": ["yaml_content"]}},
            {"name": "save_workflow", "description": "Save final GitHub Actions workflow",
             "input_schema": {"type": "object", "properties": {
                 "yaml_content": {"type": "string"}, "filename": {"type": "string"},
                 "notes": {"type": "array", "items": {"type": "string"}},
                 "warnings": {"type": "array", "items": {"type": "string"}},
                 "manual_review_items": {"type": "array", "items": {"type": "string"}}},
                 "required": ["yaml_content", "filename"]}},
            {"name": "add_warning", "description": "Add a warning",
             "input_schema": {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]}},
            {"name": "add_conversion_note", "description": "Add a conversion note",
             "input_schema": {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]}},
        ]

    def _summarize_pipeline(self, pipeline):
        jobs = [j for j in pipeline.jobs.values() if not j.is_template]
        templates = [j for j in pipeline.jobs.values() if j.is_template]
        lines = [f"Stages: {', '.join(pipeline.stages)}", f"Jobs: {len(jobs)}",
                 f"Templates: {len(templates)}", f"Global vars: {len(pipeline.variables)}"]
        if pipeline.default_image:
            lines.append(f"Default image: {pipeline.default_image}")
        lines.append("\nJobs:")
        for job in jobs:
            feats = []
            if job.rules: feats.append("rules")
            if job.parallel: feats.append("parallel")
            if job.extends: feats.append(f"extends({','.join(job.extends)})")
            if job.environment: feats.append(f"env:{job.environment.name}")
            feat_str = f" [{', '.join(feats)}]" if feats else ""
            lines.append(f"  - {job.name} (stage:{job.stage}){feat_str}")
        return "\n".join(lines)
