"""Data models for GitLab CI and GitHub Actions structures."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class GitLabArtifacts:
    paths: list[str] = field(default_factory=list)
    reports: dict[str, Any] = field(default_factory=dict)
    expire_in: Optional[str] = None
    when: str = "on_success"
    name: Optional[str] = None
    untracked: bool = False
    expose_as: Optional[str] = None


@dataclass
class GitLabCache:
    key: Optional[str] = None
    paths: list[str] = field(default_factory=list)
    policy: str = "pull-push"
    untracked: bool = False
    when: str = "on_success"


@dataclass
class GitLabEnvironment:
    name: str = ""
    url: Optional[str] = None
    action: Optional[str] = None
    auto_stop_in: Optional[str] = None
    on_stop: Optional[str] = None
    deployment_tier: Optional[str] = None


@dataclass
class GitLabRetry:
    max: int = 0
    when: list[str] = field(default_factory=list)


@dataclass
class GitLabParallel:
    matrix: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class GitLabJob:
    name: str
    stage: str = "test"
    image: Optional[str] = None
    services: list[dict[str, Any]] = field(default_factory=list)
    script: list[str] = field(default_factory=list)
    before_script: list[str] = field(default_factory=list)
    after_script: list[str] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)
    artifacts: Optional[GitLabArtifacts] = None
    cache: Optional[GitLabCache] = None
    environment: Optional[GitLabEnvironment] = None
    needs: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    allow_failure: bool = False
    when: str = "on_success"
    timeout: Optional[str] = None
    retry: Optional[GitLabRetry] = None
    parallel: Optional[GitLabParallel] = None
    only: Optional[dict[str, Any]] = None
    except_: Optional[dict[str, Any]] = None
    rules: list[dict[str, Any]] = field(default_factory=list)
    extends: list[str] = field(default_factory=list)
    trigger: Optional[dict[str, Any]] = None
    interruptible: bool = False
    resource_group: Optional[str] = None
    is_template: bool = False


@dataclass
class GitLabPipeline:
    stages: list[str] = field(default_factory=lambda: ["build", "test", "deploy"])
    variables: dict[str, str] = field(default_factory=dict)
    default_image: Optional[str] = None
    default_services: list[dict[str, Any]] = field(default_factory=list)
    default_before_script: list[str] = field(default_factory=list)
    default_after_script: list[str] = field(default_factory=list)
    default_cache: Optional[GitLabCache] = None
    default_artifacts: Optional[GitLabArtifacts] = None
    default_timeout: Optional[str] = None
    default_retry: Optional[GitLabRetry] = None
    default_tags: list[str] = field(default_factory=list)
    jobs: dict[str, GitLabJob] = field(default_factory=dict)
    workflow: Optional[dict[str, Any]] = None
    includes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ConversionResult:
    source_file: str
    output_workflows: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    unsupported_features: list[str] = field(default_factory=list)
    ai_enhanced: bool = False
    conversion_notes: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0 and len(self.output_workflows) > 0
