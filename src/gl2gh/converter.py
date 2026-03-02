"""
Core rule-based converter: GitLab CI pipeline -> GitHub Actions workflows.
"""

from __future__ import annotations
import logging
import re
from typing import Any, Optional

from gl2gh.models import (
    ConversionResult,
    GitLabCache,
    GitLabJob,
    GitLabPipeline,
)
from gl2gh.mappings.rules import (
    convert_rules_to_if,
    image_to_runner,
    normalize_service,
    parse_expire_in_days,
    parse_only_except,
    parse_timeout_minutes,
    stages_to_needs_graph,
    translate_cache_key,
    translate_variable,
    translate_variables_dict,
    when_to_if_condition,
)
from gl2gh.utils.yaml_utils import dump_yaml, add_yaml_header

logger = logging.getLogger(__name__)


class GitLabToGitHubConverter:
    def __init__(
        self,
        workflow_name: str = "CI",
        source_file: str = ".gitlab-ci.yml",
    ) -> None:
        self.workflow_name = workflow_name
        self.source_file = source_file

    def convert(self, pipeline: GitLabPipeline) -> ConversionResult:
        result = ConversionResult(source_file=self.source_file)

        if not pipeline.jobs:
            result.errors.append("No jobs found in the GitLab CI pipeline.")
            return result

        try:
            workflow = self._build_workflow(pipeline, result)
            yaml_content = dump_yaml(workflow)
            yaml_with_header = add_yaml_header(yaml_content, self.source_file)
            filename = self._workflow_filename()
            result.output_workflows[filename] = yaml_with_header
        except Exception as exc:
            logger.exception("Conversion failed")
            result.errors.append(f"Conversion error: {exc}")

        return result

    def _workflow_filename(self) -> str:
        slug = self.workflow_name.lower().replace(" ", "-").replace("/", "-")
        return f"{slug}.yml"

    def _build_workflow(
        self,
        pipeline: GitLabPipeline,
        result: ConversionResult,
    ) -> dict[str, Any]:
        workflow: dict[str, Any] = {}
        workflow["name"] = self.workflow_name

        on_triggers = self._build_triggers(pipeline, result)
        workflow["on"] = on_triggers

        if pipeline.variables:
            workflow["env"] = translate_variables_dict(pipeline.variables)

        non_template_jobs = {
            name: job
            for name, job in pipeline.jobs.items()
            if not job.is_template
        }

        stage_needs = stages_to_needs_graph(non_template_jobs, pipeline.stages)

        jobs_dict: dict[str, Any] = {}
        for job_name, job in non_template_jobs.items():
            if job.trigger:
                result.warnings.append(
                    f"Job '{job_name}' uses 'trigger:' — converted to workflow_dispatch. "
                    "Review manually."
                )
                result.unsupported_features.append("trigger:")
                continue

            gha_job = self._convert_job(job_name, job, stage_needs, pipeline, result)
            jobs_dict[self._sanitize_job_name(job_name)] = gha_job

        workflow["jobs"] = jobs_dict
        return workflow

    def _build_triggers(
        self,
        pipeline: GitLabPipeline,
        result: ConversionResult,
    ) -> dict[str, Any]:
        if pipeline.workflow:
            rules = pipeline.workflow.get("rules", [])
            if rules:
                result.warnings.append(
                    "workflow: rules detected — using push/pull_request/workflow_dispatch defaults."
                )

        job_triggers: list[dict[str, Any]] = []
        for job in pipeline.jobs.values():
            if job.is_template:
                continue
            if job.only or job.except_:
                on_t, _ = parse_only_except(
                    job.only.get("refs") if job.only else None,
                    job.except_.get("refs") if job.except_ else None,
                )
                job_triggers.append(on_t)

        merged: dict[str, Any] = {}
        if job_triggers:
            for t in job_triggers:
                for event, config in t.items():
                    if event not in merged:
                        merged[event] = config
        else:
            merged = {
                "push": {"branches": ["main", "master"]},
                "pull_request": {"branches": ["main", "master"]},
                "workflow_dispatch": {},
            }

        merged.setdefault("workflow_dispatch", {})
        return merged

    def _convert_job(
        self,
        job_name: str,
        job: GitLabJob,
        stage_needs: dict[str, list[str]],
        pipeline: GitLabPipeline,
        result: ConversionResult,
    ) -> dict[str, Any]:
        gha_job: dict[str, Any] = {}

        runner = image_to_runner(job.image)
        gha_job["runs-on"] = runner

        if job.image and ((":" in job.image or "/" in job.image)):
            gha_job["container"] = {"image": job.image}

        if job.services:
            gha_job["services"] = self._convert_services(job.services, result)

        needs = job.needs if job.needs else stage_needs.get(job_name, [])
        if needs:
            gha_job["needs"] = [self._sanitize_job_name(n) for n in needs if n]

        if job.environment:
            env_spec: dict[str, Any] = {"name": translate_variable(job.environment.name)}
            if job.environment.url:
                env_spec["url"] = translate_variable(job.environment.url)
            gha_job["environment"] = env_spec

        if_condition = self._build_if_condition(job, result)
        if if_condition:
            gha_job["if"] = if_condition

        if job.timeout:
            mins = parse_timeout_minutes(job.timeout)
            if mins:
                gha_job["timeout-minutes"] = mins

        if job.allow_failure:
            gha_job["continue-on-error"] = True

        if job.parallel and job.parallel.matrix:
            gha_job["strategy"] = {
                "matrix": self._convert_matrix(job.parallel.matrix),
                "fail-fast": False,
            }

        if job.variables:
            gha_job["env"] = translate_variables_dict(job.variables)

        steps = self._build_steps(job, pipeline, result)
        gha_job["steps"] = steps

        return gha_job

    def _build_if_condition(
        self,
        job: GitLabJob,
        result: ConversionResult,
    ) -> Optional[str]:
        if job.rules:
            cond, warnings = convert_rules_to_if(job.rules)
            result.warnings.extend(warnings)
            return cond

        if job.when == "manual":
            result.warnings.append(
                f"Job '{job.name}' has 'when: manual' — consider using "
                "workflow_dispatch trigger or environment protection rules."
            )
            return None

        if job.only or job.except_:
            _, if_cond = parse_only_except(
                job.only.get("refs") if job.only else None,
                job.except_.get("refs") if job.except_ else None,
            )
            return if_cond

        if job.when and job.when != "on_success":
            return when_to_if_condition(job.when)

        return None

    def _build_steps(
        self,
        job: GitLabJob,
        pipeline: GitLabPipeline,
        result: ConversionResult,
    ) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []

        steps.append({
            "name": "Checkout code",
            "uses": "actions/checkout@v4",
        })

        cache = job.cache or pipeline.default_cache
        if cache:
            cache_step = self._convert_cache_to_step(cache)
            if cache_step:
                steps.append(cache_step)

        if job.before_script:
            steps.append({
                "name": "Before script",
                "run": self._script_to_run(job.before_script),
                "shell": "bash",
            })

        if job.script:
            steps.append({
                "name": "Run script",
                "run": self._script_to_run(job.script),
                "shell": "bash",
            })

        if job.after_script:
            steps.append({
                "name": "After script",
                "if": "always()",
                "run": self._script_to_run(job.after_script),
                "shell": "bash",
            })

        if job.artifacts:
            artifact_step = self._convert_artifacts_to_step(job, result)
            if artifact_step:
                steps.append(artifact_step)

        if job.artifacts and job.artifacts.reports:
            report_steps = self._convert_reports_to_steps(job.artifacts.reports, result)
            steps.extend(report_steps)

        return steps

    def _convert_services(
        self,
        services: list[dict[str, Any]],
        result: ConversionResult,
    ) -> dict[str, Any]:
        gha_services: dict[str, Any] = {}
        for svc in services:
            svc = normalize_service(svc)
            image = svc.get("image", "")
            name = image.split("/")[-1].split(":")[0].replace("-", "_")
            svc_def: dict[str, Any] = {"image": image}
            if "ports" in svc:
                svc_def["ports"] = svc["ports"]
            if "environment" in svc or "variables" in svc:
                env = svc.get("environment") or svc.get("variables") or {}
                svc_def["env"] = translate_variables_dict(env) if isinstance(env, dict) else {}
            gha_services[name] = svc_def
        return gha_services

    def _convert_cache_to_step(self, cache: GitLabCache) -> Optional[dict[str, Any]]:
        paths = cache.paths
        if not paths:
            return None
        key = translate_cache_key(cache.key or "${{ runner.os }}-cache")
        return {
            "name": "Cache dependencies",
            "uses": "actions/cache@v4",
            "with": {
                "path": "\n".join(paths),
                "key": key,
                "restore-keys": f"{key}\n${{{{ runner.os }}}}-",
            },
        }

    def _convert_artifacts_to_step(
        self,
        job: GitLabJob,
        result: ConversionResult,
    ) -> Optional[dict[str, Any]]:
        arts = job.artifacts
        if not arts or not arts.paths:
            return None

        step: dict[str, Any] = {
            "name": "Upload artifacts",
            "uses": "actions/upload-artifact@v4",
            "with": {
                "name": arts.name or f"{job.name}-artifacts",
                "path": "\n".join(arts.paths),
            },
        }

        if arts.expire_in:
            days = parse_expire_in_days(arts.expire_in)
            step["with"]["retention-days"] = days

        if arts.when == "on_failure":
            step["if"] = "failure()"
        elif arts.when == "always":
            step["if"] = "always()"

        return step

    def _convert_reports_to_steps(
        self,
        reports: dict[str, Any],
        result: ConversionResult,
    ) -> list[dict[str, Any]]:
        steps = []

        if "junit" in reports:
            junit_paths = reports["junit"]
            if isinstance(junit_paths, str):
                junit_paths = [junit_paths]
            steps.append({
                "name": "Publish test results",
                "uses": "dorny/test-reporter@v1",
                "if": "always()",
                "with": {
                    "name": "Test Results",
                    "path": ", ".join(junit_paths),
                    "reporter": "java-junit",
                },
            })
            result.conversion_notes.append(
                "JUnit reports: using dorny/test-reporter@v1."
            )

        if "coverage" in reports:
            result.warnings.append(
                "Coverage reports: consider using Codecov or coverallsapp/github-action."
            )

        unsupported_reports = set(reports.keys()) - {"junit", "coverage", "cobertura"}
        for report_type in unsupported_reports:
            result.unsupported_features.append(f"artifacts.reports.{report_type}")

        return steps

    def _convert_matrix(self, matrix: list[dict[str, Any]]) -> dict[str, Any]:
        if len(matrix) == 1:
            return matrix[0]
        combined: dict[str, Any] = {}
        for entry in matrix:
            for key, values in entry.items():
                if key in combined:
                    existing = combined[key]
                    if isinstance(existing, list):
                        for v in (values if isinstance(values, list) else [values]):
                            if v not in existing:
                                existing.append(v)
                    else:
                        combined[key] = [existing] + (
                            values if isinstance(values, list) else [values]
                        )
                else:
                    combined[key] = values if isinstance(values, list) else [values]
        return combined

    def _script_to_run(self, script: list[str]) -> str:
        return "\n".join(translate_variable(line) for line in script)

    def _sanitize_job_name(self, name: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        if sanitized and sanitized[0].isdigit():
            sanitized = "_" + sanitized
        return sanitized
