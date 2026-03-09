"""
GitLab CI YAML parser.
Parses .gitlab-ci.yml into structured Python objects.
"""

from __future__ import annotations

import logging
from typing import Any

from gl2gh.mappings.rules import normalize_service
from gl2gh.models import (
    GitLabArtifacts,
    GitLabCache,
    GitLabEnvironment,
    GitLabJob,
    GitLabParallel,
    GitLabPipeline,
    GitLabRetry,
)
from gl2gh.utils.yaml_utils import load_yaml_with_anchors

logger = logging.getLogger(__name__)

GLOBAL_KEYWORDS = {
    "stages",
    "variables",
    "default",
    "include",
    "workflow",
    "image",
    "services",
    "before_script",
    "after_script",
    "cache",
    "artifacts",
}


class GitLabCIParser:
    """Parse a .gitlab-ci.yml file into a GitLabPipeline object."""

    def __init__(self) -> None:
        self._raw: dict[str, Any] = {}

    def parse_string(self, content: str) -> GitLabPipeline:
        self._raw = load_yaml_with_anchors(content)
        return self._build_pipeline()

    def parse_file(self, path: str) -> GitLabPipeline:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return self.parse_string(content)

    def _build_pipeline(self) -> GitLabPipeline:
        raw = self._raw
        pipeline = GitLabPipeline()

        if "stages" in raw:
            pipeline.stages = list(raw["stages"])

        if "variables" in raw:
            pipeline.variables = self._parse_variables(raw["variables"])

        if "workflow" in raw:
            pipeline.workflow = dict(raw["workflow"])

        if "include" in raw:
            includes = raw["include"]
            if isinstance(includes, list):
                pipeline.includes = [
                    ({"local": i} if isinstance(i, str) else dict(i)) for i in includes
                ]
            elif isinstance(includes, dict):
                pipeline.includes = [dict(includes)]
            elif isinstance(includes, str):
                pipeline.includes = [{"local": includes}]

        default = raw.get("default", {}) or {}

        pipeline.default_image = raw.get("image") or default.get("image")
        if isinstance(pipeline.default_image, dict):
            pipeline.default_image = pipeline.default_image.get("name")

        pipeline.default_before_script = self._parse_script(
            raw.get("before_script") or default.get("before_script") or []
        )
        pipeline.default_after_script = self._parse_script(
            raw.get("after_script") or default.get("after_script") or []
        )

        raw_services = raw.get("services") or default.get("services") or []
        if raw_services:
            pipeline.default_services = self._parse_services(raw_services)

        raw_cache = raw.get("cache") or default.get("cache")
        if raw_cache:
            pipeline.default_cache = self._parse_cache(raw_cache)

        raw_artifacts = raw.get("artifacts") or default.get("artifacts")
        if raw_artifacts:
            pipeline.default_artifacts = self._parse_artifacts(raw_artifacts)

        pipeline.default_timeout = raw.get("timeout") or default.get("timeout")

        raw_retry = raw.get("retry") or default.get("retry")
        if raw_retry is not None:
            pipeline.default_retry = self._parse_retry(raw_retry)

        pipeline.default_tags = list(raw.get("tags") or default.get("tags") or [])

        for key, value in raw.items():
            if key in GLOBAL_KEYWORDS or not isinstance(value, dict):
                continue
            is_template = key.startswith(".")
            job = self._parse_job(key, value, pipeline, is_template)
            pipeline.jobs[key] = job

        self._resolve_extends(pipeline)
        return pipeline

    def _parse_job(
        self,
        name: str,
        raw_job: dict[str, Any],
        pipeline: GitLabPipeline,
        is_template: bool = False,
    ) -> GitLabJob:
        job = GitLabJob(name=name)
        job.is_template = is_template
        job.stage = raw_job.get("stage", "test")

        img = raw_job.get("image") or pipeline.default_image
        if isinstance(img, dict):
            img = img.get("name")
        job.image = img

        raw_services = raw_job.get("services", pipeline.default_services)
        job.services = self._parse_services(raw_services)

        job.before_script = self._parse_script(
            raw_job.get("before_script", pipeline.default_before_script)
        )
        job.script = self._parse_script(raw_job.get("script", []))
        job.after_script = self._parse_script(
            raw_job.get("after_script", pipeline.default_after_script)
        )

        job.variables = self._parse_variables(raw_job.get("variables", {}))

        if "artifacts" in raw_job:
            job.artifacts = self._parse_artifacts(raw_job["artifacts"])
        elif pipeline.default_artifacts:
            job.artifacts = pipeline.default_artifacts

        if "cache" in raw_job:
            job.cache = self._parse_cache(raw_job["cache"])
        elif pipeline.default_cache:
            job.cache = pipeline.default_cache

        if "environment" in raw_job:
            job.environment = self._parse_environment(raw_job["environment"])

        raw_needs = raw_job.get("needs", [])
        if isinstance(raw_needs, list):
            job.needs = []
            for n in raw_needs:
                if isinstance(n, str):
                    job.needs.append(n)
                elif isinstance(n, dict):
                    job.needs.append(n.get("job", ""))

        job.dependencies = list(raw_job.get("dependencies", []))
        job.tags = list(raw_job.get("tags", pipeline.default_tags) or [])

        af = raw_job.get("allow_failure", False)
        job.allow_failure = True if isinstance(af, dict) else bool(af)

        job.when = raw_job.get("when", "on_success")
        job.timeout = raw_job.get("timeout", pipeline.default_timeout)

        if "retry" in raw_job:
            job.retry = self._parse_retry(raw_job["retry"])
        elif pipeline.default_retry:
            job.retry = pipeline.default_retry

        if "parallel" in raw_job:
            job.parallel = self._parse_parallel(raw_job["parallel"])

        only = raw_job.get("only")
        if only is not None:
            job.only = {"refs": only} if isinstance(only, list) else dict(only)

        except_ = raw_job.get("except")
        if except_ is not None:
            job.except_ = (
                {"refs": except_} if isinstance(except_, list) else dict(except_)
            )

        job.rules = list(raw_job.get("rules", []))

        extends = raw_job.get("extends", [])
        if isinstance(extends, str):
            job.extends = [extends]
        elif isinstance(extends, list):
            job.extends = list(extends)
        else:
            job.extends = []

        if "trigger" in raw_job:
            trig = raw_job["trigger"]
            job.trigger = {"project": trig} if isinstance(trig, str) else dict(trig)

        job.interruptible = raw_job.get("interruptible", False)
        job.resource_group = raw_job.get("resource_group")

        return job

    def _resolve_extends(self, pipeline: GitLabPipeline) -> None:
        for job in pipeline.jobs.values():
            if not job.extends:
                continue
            for template_name in reversed(job.extends):
                template_job = pipeline.jobs.get(template_name)
                if not template_job:
                    logger.warning(
                        "extends: '%s' not found for job '%s'", template_name, job.name
                    )
                    continue
                self._merge_job_template(job, template_job)

    def _merge_job_template(self, job: GitLabJob, template: GitLabJob) -> None:
        if not job.image and template.image:
            job.image = template.image
        if not job.before_script and template.before_script:
            job.before_script = template.before_script
        if not job.after_script and template.after_script:
            job.after_script = template.after_script
        if not job.variables:
            job.variables = dict(template.variables)
        else:
            merged = dict(template.variables)
            merged.update(job.variables)
            job.variables = merged
        if not job.cache and template.cache:
            job.cache = template.cache
        if not job.artifacts and template.artifacts:
            job.artifacts = template.artifacts
        if not job.tags:
            job.tags = list(template.tags)
        if not job.services and template.services:
            job.services = list(template.services)
        if not job.rules and template.rules:
            job.rules = list(template.rules)
        if not job.timeout and template.timeout:
            job.timeout = template.timeout
        if not job.retry and template.retry:
            job.retry = template.retry
        if not job.parallel and template.parallel:
            job.parallel = template.parallel
        if job.allow_failure is False and template.allow_failure:
            job.allow_failure = template.allow_failure
        if job.when == "on_success" and template.when != "on_success":
            job.when = template.when

    def _parse_script(self, raw: Any) -> list[str]:
        if not raw:
            return []
        if isinstance(raw, str):
            return [raw]
        return [str(s) for s in raw]

    def _parse_variables(self, raw: Any) -> dict[str, str]:
        if not raw:
            return {}
        if isinstance(raw, dict):
            result = {}
            for k, v in raw.items():
                if isinstance(v, dict):
                    result[str(k)] = str(v.get("value", ""))
                else:
                    result[str(k)] = str(v) if v is not None else ""
            return result
        return {}

    def _parse_services(self, raw: Any) -> list[dict[str, Any]]:
        if not raw:
            return []
        return [normalize_service(svc) for svc in raw]

    def _parse_cache(self, raw: Any) -> GitLabCache:
        if isinstance(raw, dict):
            cache = GitLabCache()
            if "key" in raw:
                key = raw["key"]
                if isinstance(key, dict):
                    files = key.get("files", [])
                    cache.key = "-".join(files) if files else "default"
                else:
                    cache.key = str(key)
            cache.paths = list(raw.get("paths", []))
            cache.policy = raw.get("policy", "pull-push")
            cache.untracked = raw.get("untracked", False)
            return cache
        return GitLabCache()

    def _parse_artifacts(self, raw: dict[str, Any]) -> GitLabArtifacts:
        arts = GitLabArtifacts()
        arts.paths = list(raw.get("paths", []))
        arts.expire_in = raw.get("expire_in")
        arts.when = raw.get("when", "on_success")
        arts.name = raw.get("name")
        arts.untracked = raw.get("untracked", False)
        arts.expose_as = raw.get("expose_as")
        if "reports" in raw:
            arts.reports = dict(raw["reports"])
        return arts

    def _parse_environment(self, raw: Any) -> GitLabEnvironment:
        if isinstance(raw, str):
            return GitLabEnvironment(name=raw)
        if isinstance(raw, dict):
            env = GitLabEnvironment()
            env.name = raw.get("name", "")
            env.url = raw.get("url")
            env.action = raw.get("action")
            env.auto_stop_in = raw.get("auto_stop_in")
            env.on_stop = raw.get("on_stop")
            env.deployment_tier = raw.get("deployment_tier")
            return env
        return GitLabEnvironment()

    def _parse_retry(self, raw: Any) -> GitLabRetry:
        if isinstance(raw, int):
            return GitLabRetry(max=raw)
        if isinstance(raw, dict):
            retry = GitLabRetry()
            retry.max = int(raw.get("max", 0))
            when = raw.get("when", [])
            retry.when = [when] if isinstance(when, str) else list(when)
            return retry
        return GitLabRetry()

    def _parse_parallel(self, raw: Any) -> GitLabParallel:
        if isinstance(raw, int):
            return GitLabParallel(matrix=[{"INDEX": list(range(1, raw + 1))}])
        if isinstance(raw, dict):
            return GitLabParallel(matrix=list(raw.get("matrix", [])))
        return GitLabParallel()
