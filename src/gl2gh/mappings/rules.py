"""
Comprehensive mapping rules from GitLab CI to GitHub Actions.
"""

from __future__ import annotations

import re
from typing import Any, Optional

COMMON_IMAGE_TO_RUNNER: dict[str, str] = {
    "ubuntu": "ubuntu-latest",
    "debian": "ubuntu-latest",
    "alpine": "ubuntu-latest",
    "python": "ubuntu-latest",
    "node": "ubuntu-latest",
    "ruby": "ubuntu-latest",
    "golang": "ubuntu-latest",
    "rust": "ubuntu-latest",
    "java": "ubuntu-latest",
    "openjdk": "ubuntu-latest",
    "maven": "ubuntu-latest",
    "gradle": "ubuntu-latest",
    "php": "ubuntu-latest",
    "dotnet": "windows-latest",
    "microsoft/dotnet": "windows-latest",
    "mcr.microsoft.com": "windows-latest",
    "macos": "macos-latest",
    "xcode": "macos-latest",
}

DEFAULT_RUNNER = "ubuntu-latest"


def image_to_runner(image: Optional[str]) -> str:
    if not image:
        return DEFAULT_RUNNER
    image_lower = image.lower()
    for pattern, runner in COMMON_IMAGE_TO_RUNNER.items():
        if pattern in image_lower:
            return runner
    return DEFAULT_RUNNER


GITLAB_TO_GHA_VARS: dict[str, str] = {
    "$CI_COMMIT_SHA": "${{ github.sha }}",
    "${CI_COMMIT_SHA}": "${{ github.sha }}",
    "$CI_COMMIT_REF_NAME": "${{ github.ref_name }}",
    "${CI_COMMIT_REF_NAME}": "${{ github.ref_name }}",
    "$CI_COMMIT_REF_SLUG": "${{ github.ref_name }}",
    "${CI_COMMIT_REF_SLUG}": "${{ github.ref_name }}",
    "$CI_COMMIT_BRANCH": "${{ github.ref_name }}",
    "${CI_COMMIT_BRANCH}": "${{ github.ref_name }}",
    "$CI_DEFAULT_BRANCH": "${{ github.event.repository.default_branch }}",
    "$CI_PIPELINE_ID": "${{ github.run_id }}",
    "${CI_PIPELINE_ID}": "${{ github.run_id }}",
    "$CI_JOB_ID": "${{ github.job }}",
    "$CI_JOB_NAME": "${{ github.job }}",
    "$CI_PROJECT_NAME": "${{ github.event.repository.name }}",
    "$CI_PROJECT_PATH": "${{ github.repository }}",
    "${CI_PROJECT_PATH}": "${{ github.repository }}",
    "$CI_PROJECT_URL": "${{ github.event.repository.html_url }}",
    "$CI_PROJECT_NAMESPACE": "${{ github.repository_owner }}",
    "$CI_REGISTRY": "ghcr.io",
    "$CI_REGISTRY_IMAGE": "ghcr.io/${{ github.repository }}",
    "${CI_REGISTRY_IMAGE}": "ghcr.io/${{ github.repository }}",
    "$CI_REGISTRY_USER": "${{ github.actor }}",
    "$CI_REGISTRY_PASSWORD": "${{ secrets.GITHUB_TOKEN }}",
    "$CI_COMMIT_TAG": "${{ github.ref_name }}",
    "${CI_COMMIT_TAG}": "${{ github.ref_name }}",
    "$CI_MERGE_REQUEST_IID": "${{ github.event.pull_request.number }}",
    "$CI_MERGE_REQUEST_SOURCE_BRANCH_NAME": "${{ github.head_ref }}",
    "$CI_MERGE_REQUEST_TARGET_BRANCH_NAME": "${{ github.base_ref }}",
    "$CI_SERVER_HOST": "github.com",
    "$CI_BUILDS_DIR": "${{ github.workspace }}",
    "$CI_PROJECT_DIR": "${{ github.workspace }}",
    "${CI_PROJECT_DIR}": "${{ github.workspace }}",
    "$CI_COMMIT_SHORT_SHA": "${{ github.sha }}",
    "${CI_COMMIT_SHORT_SHA}": "${{ github.sha }}",
}


def translate_variable(value: str) -> str:
    result = value
    for gl_var, gh_var in GITLAB_TO_GHA_VARS.items():
        result = result.replace(gl_var, gh_var)
    return result


def translate_variables_dict(variables: dict[str, str]) -> dict[str, str]:
    return {k: translate_variable(str(v)) for k, v in variables.items()}


GL_CI_VAR_TO_GH_EXPR: dict[str, str] = {
    "$CI_COMMIT_REF_NAME": "github.ref_name",
    "$CI_COMMIT_BRANCH": "github.ref_name",
    "$CI_PIPELINE_SOURCE": "github.event_name",
    "$CI_COMMIT_TAG": "github.ref",
    "$CI_MERGE_REQUEST_IID": "github.event.pull_request.number",
    "$CI_COMMIT_MESSAGE": "github.event.head_commit.message",
}


def parse_only_except(
    only: Optional[list],
    except_: Optional[list],
) -> tuple[dict[str, Any], Optional[str]]:
    triggers: dict[str, Any] = {}
    conditions: list[str] = []

    if only is not None:
        refs = only if isinstance(only, list) else [only]
        for ref in refs:
            if ref == "branches":
                triggers.setdefault("push", {}).setdefault("branches", ["**"])
                triggers.setdefault("pull_request", {})
            elif ref == "tags":
                triggers.setdefault("push", {}).setdefault("tags", ["*"])
            elif ref in ("merge_requests", "merge_request"):
                triggers.setdefault("pull_request", {})
            elif ref in ("schedules",):
                triggers.setdefault("schedule", [{"cron": "0 0 * * *"}])
            elif ref in ("web", "api", "triggers"):
                triggers.setdefault("workflow_dispatch", {})
            else:
                pattern = str(ref)
                branches = triggers.setdefault("push", {}).setdefault("branches", [])
                if isinstance(branches, list):
                    branches.append(pattern)

    if except_ is not None:
        refs = except_ if isinstance(except_, list) else [except_]
        for ref in refs:
            if ref in ("main", "master"):
                conditions.append(f"github.ref != 'refs/heads/{ref}'")
            elif ref == "tags":
                conditions.append("!startsWith(github.ref, 'refs/tags/')")
            elif ref in ("merge_requests",):
                conditions.append("github.event_name != 'pull_request'")

    if not triggers:
        triggers = {"push": {}, "pull_request": {}, "workflow_dispatch": {}}

    if_condition = " && ".join(conditions) if conditions else None
    return triggers, if_condition


def convert_rules_to_if(rules: list[dict[str, Any]]) -> tuple[Optional[str], list[str]]:
    if not rules:
        return None, []

    warnings: list[str] = []
    conditions: list[str] = []

    for rule in rules:
        if_clause = rule.get("if")
        when = rule.get("when", "on_success")

        if when == "never":
            continue
        if when == "manual":
            warnings.append(
                "Manual 'when: manual' rule detected — "
                "consider using 'workflow_dispatch' trigger"
            )

        if if_clause:
            gh_expr = str(if_clause)
            for gl, gh in GL_CI_VAR_TO_GH_EXPR.items():
                gh_expr = gh_expr.replace(gl, f"github.{gh.split('.')[-1]}")
            gh_expr = gh_expr.replace('"', "'")
            conditions.append(gh_expr)

    if not conditions:
        return None, warnings

    return " || ".join(conditions), warnings


WHEN_TO_IF: dict[str, Optional[str]] = {
    "on_success": "success()",
    "on_failure": "failure()",
    "always": "always()",
    "manual": None,
    "never": "false",
    "delayed": None,
}


def when_to_if_condition(when: str) -> Optional[str]:
    return WHEN_TO_IF.get(when)


def parse_timeout_minutes(timeout_str: str) -> Optional[int]:
    if not timeout_str:
        return None
    total_minutes = 0
    h_match = re.search(r"(\d+)\s*h(?:ours?)?", timeout_str)
    if h_match:
        total_minutes += int(h_match.group(1)) * 60
    m_match = re.search(r"(\d+)\s*m(?:in(?:utes?)?)?", timeout_str)
    if m_match:
        total_minutes += int(m_match.group(1))
    s_match = re.search(r"(\d+)\s*s(?:ec(?:onds?)?)?", timeout_str)
    if s_match:
        total_minutes += int(s_match.group(1)) // 60

    if total_minutes == 0:
        try:
            total_minutes = int(timeout_str)
        except ValueError:
            return None

    return total_minutes if total_minutes > 0 else None


GITLAB_CACHE_KEY_TO_GH: dict[str, str] = {
    "${CI_COMMIT_REF_SLUG}": "${{ github.ref_name }}",
    "$CI_COMMIT_REF_SLUG": "${{ github.ref_name }}",
    "${CI_PROJECT_NAME}": "${{ github.event.repository.name }}",
    "$CI_PROJECT_NAME": "${{ github.event.repository.name }}",
    "${CI_PIPELINE_ID}": "${{ github.run_id }}",
    "$CI_PIPELINE_ID": "${{ github.run_id }}",
    "${CI_JOB_NAME}": "${{ github.job }}",
    "$CI_JOB_NAME": "${{ github.job }}",
}


def translate_cache_key(key: str) -> str:
    result = key
    for gl, gh in GITLAB_CACHE_KEY_TO_GH.items():
        result = result.replace(gl, gh)
    return result


def normalize_service(service: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(service, str):
        return {"image": service}
    return dict(service)


EXPIRE_IN_PATTERN = re.compile(
    r"(\d+)\s*(second|minute|hour|day|week|month|year)s?", re.I
)


def parse_expire_in_days(expire_in: str) -> int:
    match = EXPIRE_IN_PATTERN.search(expire_in)
    if not match:
        return 30
    value = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "second":
        return max(1, value // 86400)
    elif unit == "minute":
        return max(1, value // 1440)
    elif unit == "hour":
        return max(1, value // 24)
    elif unit == "day":
        return value
    elif unit == "week":
        return value * 7
    elif unit == "month":
        return value * 30
    elif unit == "year":
        return min(value * 365, 400)
    return 30


def stages_to_needs_graph(
    jobs: dict[str, Any],
    stages: list[str],
) -> dict[str, list[str]]:
    stage_to_jobs: dict[str, list[str]] = {}
    for job_name, job in jobs.items():
        stage_to_jobs.setdefault(job.stage, []).append(job_name)

    needs_map: dict[str, list[str]] = {}
    ordered_stages = [s for s in stages if s in stage_to_jobs]

    for i, stage in enumerate(ordered_stages):
        prev_jobs: list[str] = []
        if i > 0:
            prev_stage = ordered_stages[i - 1]
            prev_jobs = stage_to_jobs.get(prev_stage, [])
        for job_name in stage_to_jobs.get(stage, []):
            needs_map[job_name] = prev_jobs

    return needs_map
