"""Tests for the MCP server tools, embeddings, and indexer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Skip entire module if chromadb is not installed
chromadb = pytest.importorskip("chromadb")

from mcp_server.embeddings import (  # noqa: E402
    VectorStore,
    build_index_from_disk,
    extract_patterns_from_yaml,
    yaml_to_text_description,
)
from mcp_server.tools.handlers import (  # noqa: E402
    ConfidenceScoreTool,
    ConversionExampleTool,
    PatternSearchTool,
    RecordFeedbackTool,
    SuggestGitHubActionTool,
    SuggestWorkflowSplitTool,
    ValidateAgainstCorpusTool,
)

# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------

SIMPLE_GITLAB_CI = """\
stages:
  - build
  - test

build:
  stage: build
  image: python:3.12
  script:
    - pip install .

test:
  stage: test
  image: python:3.12
  services:
    - postgres:16
  script:
    - pytest
  cache:
    paths:
      - .cache/
  artifacts:
    reports:
      junit: report.xml
"""

SIMPLE_GH_ACTIONS = """\
name: CI
on:
  push:
    branches: [main]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install .
  test:
    needs: [build]
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
    steps:
      - uses: actions/checkout@v4
      - uses: actions/cache@v4
        with:
          path: .cache/
          key: cache-key
      - run: pytest
"""

LARGE_PIPELINE = """\
stages:
  - build
  - test
  - security
  - staging
  - production

build:
  stage: build
  script: [make build]

lint:
  stage: test
  script: [make lint]

unit_test:
  stage: test
  script: [make test]

integration_test:
  stage: test
  script: [make integration]

sast:
  stage: security
  script: [bandit -r src/]

deploy_staging:
  stage: staging
  script: [deploy staging]
  environment:
    name: staging

deploy_production:
  stage: production
  script: [deploy prod]
  environment:
    name: production
  when: manual
"""


@pytest.fixture(scope="module")
def store() -> VectorStore:
    """Build a vector store from seed data for the test module."""
    return build_index_from_disk()


# -----------------------------------------------------------------------
# extract_patterns_from_yaml
# -----------------------------------------------------------------------


class TestExtractPatterns:
    def test_basic_patterns(self):
        patterns = extract_patterns_from_yaml(SIMPLE_GITLAB_CI)
        assert "services" in patterns
        assert "cache" in patterns
        assert "artifacts" in patterns

    def test_invalid_yaml(self):
        assert extract_patterns_from_yaml(":::bad yaml") == []

    def test_non_dict(self):
        assert extract_patterns_from_yaml("- item1\n- item2") == []

    def test_template_detection(self):
        content = ".base:\n  image: python:3.12\n"
        patterns = extract_patterns_from_yaml(content)
        assert "template" in patterns

    def test_docker_build_detection(self):
        content = (
            "build:\n  script:\n"
            "    - docker build -t img .\n"
        )
        patterns = extract_patterns_from_yaml(content)
        assert "docker_build" in patterns

    def test_deployment_detection(self):
        content = (
            "deploy:\n  environment:\n"
            "    name: prod\n  script:\n    - deploy\n"
        )
        patterns = extract_patterns_from_yaml(content)
        assert "deployment" in patterns
        assert "environment" in patterns

    def test_extends_pattern(self):
        content = (
            ".base:\n  image: node:20\n"
            "build:\n  extends: .base\n  script: [npm run build]\n"
        )
        patterns = extract_patterns_from_yaml(content)
        assert "extends" in patterns
        assert "template" in patterns

    def test_rules_pattern(self):
        content = (
            "test:\n  rules:\n"
            "    - if: $CI_COMMIT_BRANCH == 'main'\n"
            "  script: [pytest]\n"
        )
        patterns = extract_patterns_from_yaml(content)
        assert "rules" in patterns


# -----------------------------------------------------------------------
# yaml_to_text_description
# -----------------------------------------------------------------------


class TestYamlToText:
    def test_basic_description(self):
        desc = yaml_to_text_description(SIMPLE_GITLAB_CI)
        assert "build" in desc.lower()
        assert "test" in desc.lower()
        assert "stages" in desc.lower()

    def test_invalid_yaml(self):
        desc = yaml_to_text_description(":::bad")
        assert len(desc) > 0

    def test_non_dict(self):
        desc = yaml_to_text_description("- a\n- b")
        assert len(desc) > 0

    def test_includes_patterns(self):
        desc = yaml_to_text_description(SIMPLE_GITLAB_CI)
        assert "patterns" in desc.lower()


# -----------------------------------------------------------------------
# VectorStore
# -----------------------------------------------------------------------


class TestVectorStore:
    def test_stats(self, store):
        stats = store.stats()
        assert "total_documents" in stats
        assert stats["total_documents"] > 0

    def test_search(self, store):
        results = store.search(
            "GitLab CI with services and caching", n_results=3
        )
        assert len(results) > 0
        assert "id" in results[0]
        assert "distance" in results[0]

    def test_search_with_filter(self, store):
        results = store.search(
            "docker build", n_results=3,
            pattern_filter="docker",
        )
        # May or may not find results depending on data
        assert isinstance(results, list)

    def test_search_by_pattern(self, store):
        results = store.search_by_pattern(
            ["services", "cache"], n_results=2
        )
        assert isinstance(results, list)

    def test_get_conversion_pairs(self, store):
        pairs = store.get_conversion_pairs(
            "services with postgres", n_results=2
        )
        assert isinstance(pairs, list)
        if pairs:
            assert "gitlab_ci" in pairs[0]
            assert "github_workflows" in pairs[0]

    def test_index_file(self, store):
        content = (
            "test:\n  script: [echo hello]\n"
        )
        store.index_file("test_entry", content, {"source": "test"})
        results = store.search("echo hello", n_results=1)
        assert len(results) > 0


# -----------------------------------------------------------------------
# PatternSearchTool
# -----------------------------------------------------------------------


class TestPatternSearchTool:
    def test_basic_search(self, store):
        tool = PatternSearchTool(store)
        result = tool.run(
            snippet="test:\n  services:\n    - postgres:16\n"
                    "  script:\n    - pytest\n",
            limit=3,
        )
        assert "query_patterns" in result
        assert "results" in result
        assert result["total_found"] <= 3

    def test_with_pattern_filter(self, store):
        tool = PatternSearchTool(store)
        result = tool.run(
            snippet="build:\n  script: [make build]\n",
            limit=2,
            pattern_filter="cache",
        )
        assert isinstance(result["results"], list)


# -----------------------------------------------------------------------
# ConversionExampleTool
# -----------------------------------------------------------------------


class TestConversionExampleTool:
    def test_find_examples(self, store):
        tool = ConversionExampleTool(store)
        result = tool.run(feature="services", limit=2)
        assert "examples" in result
        assert result["feature"] == "services"

    def test_find_cache_examples(self, store):
        tool = ConversionExampleTool(store)
        result = tool.run(feature="cache", limit=1)
        assert "examples" in result


# -----------------------------------------------------------------------
# ValidateAgainstCorpusTool
# -----------------------------------------------------------------------


class TestValidateAgainstCorpusTool:
    def test_valid_conversion(self, store):
        tool = ValidateAgainstCorpusTool(store)
        result = tool.run(
            gitlab_ci=SIMPLE_GITLAB_CI,
            github_actions=SIMPLE_GH_ACTIONS,
        )
        assert "valid" in result
        assert "confidence" in result
        assert 0.0 <= result["confidence"] <= 1.0

    def test_missing_services(self, store):
        tool = ValidateAgainstCorpusTool(store)
        gh_no_services = (
            "name: CI\non: push\njobs:\n"
            "  test:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - run: pytest\n"
        )
        result = tool.run(
            gitlab_ci=SIMPLE_GITLAB_CI,
            github_actions=gh_no_services,
        )
        assert any("services" in w for w in result["warnings"])

    def test_missing_cache(self, store):
        tool = ValidateAgainstCorpusTool(store)
        gh_no_cache = (
            "name: CI\non: push\njobs:\n"
            "  test:\n    runs-on: ubuntu-latest\n"
            "    services:\n"
            "      postgres:\n        image: postgres:16\n"
            "    steps:\n      - run: pytest\n"
        )
        result = tool.run(
            gitlab_ci=SIMPLE_GITLAB_CI,
            github_actions=gh_no_cache,
        )
        assert any("cache" in w.lower() for w in result["warnings"])

    def test_invalid_github_yaml(self, store):
        tool = ValidateAgainstCorpusTool(store)
        result = tool.run(
            gitlab_ci=SIMPLE_GITLAB_CI,
            github_actions=":::invalid",
        )
        assert result["valid"] is False
        assert result["confidence"] == 0.0

    def test_non_dict_github_yaml(self, store):
        tool = ValidateAgainstCorpusTool(store)
        result = tool.run(
            gitlab_ci=SIMPLE_GITLAB_CI,
            github_actions="- just a list",
        )
        assert result["valid"] is False


# -----------------------------------------------------------------------
# SuggestGitHubActionTool
# -----------------------------------------------------------------------


class TestSuggestGitHubActionTool:
    def test_docker_suggestions(self, store):
        tool = SuggestGitHubActionTool(store)
        result = tool.run(
            gitlab_snippet=(
                "build:\n  image: docker:24\n"
                "  services:\n    - docker:24-dind\n"
                "  script:\n    - docker build .\n"
            )
        )
        actions = [s["action"] for s in result["suggested_actions"]]
        assert "docker/build-push-action@v6" in actions

    def test_python_suggestions(self, store):
        tool = SuggestGitHubActionTool(store)
        result = tool.run(
            gitlab_snippet=(
                "test:\n  image: python:3.12\n"
                "  script:\n    - pytest\n"
            )
        )
        actions = [s["action"] for s in result["suggested_actions"]]
        assert "actions/setup-python@v5" in actions

    def test_always_suggests_checkout(self, store):
        tool = SuggestGitHubActionTool(store)
        result = tool.run(
            gitlab_snippet="build:\n  script: [echo hello]\n"
        )
        actions = [s["action"] for s in result["suggested_actions"]]
        assert "actions/checkout@v4" in actions

    def test_node_suggestions(self, store):
        tool = SuggestGitHubActionTool(store)
        result = tool.run(
            gitlab_snippet="build:\n  script:\n    - npm ci\n"
        )
        actions = [s["action"] for s in result["suggested_actions"]]
        assert "actions/setup-node@v4" in actions


# -----------------------------------------------------------------------
# ConfidenceScoreTool (NEW in v2.0)
# -----------------------------------------------------------------------


class TestConfidenceScoreTool:
    def test_basic_scoring(self, store):
        tool = ConfidenceScoreTool(store)
        result = tool.run(
            gitlab_ci=SIMPLE_GITLAB_CI,
            github_actions=SIMPLE_GH_ACTIONS,
        )
        assert "jobs" in result
        assert "overall" in result
        assert 0.0 <= result["overall"] <= 1.0
        assert result["total_jobs"] == 2

    def test_missing_job_penalised(self, store):
        tool = ConfidenceScoreTool(store)
        gh_missing_test = (
            "name: CI\non: push\njobs:\n"
            "  build:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - run: pip install .\n"
        )
        result = tool.run(
            gitlab_ci=SIMPLE_GITLAB_CI,
            github_actions=gh_missing_test,
        )
        test_job = next(
            j for j in result["jobs"] if j["job"] == "test"
        )
        assert test_job["confidence"] < 0.7
        assert "job not found" in " ".join(test_job["flags"])

    def test_complex_features_penalised(self, store):
        gl = (
            "deploy:\n  trigger:\n"
            "    project: other/repo\n"
            "  rules:\n"
            "    - if: $CI_COMMIT_BRANCH == 'main'\n"
            "  script: [deploy]\n"
        )
        tool = ConfidenceScoreTool(store)
        result = tool.run(gitlab_ci=gl, github_actions="name: CI\non: push\njobs: {}")
        if result["jobs"]:
            job = result["jobs"][0]
            assert job["confidence"] < 0.8
            assert any("trigger" in f for f in job["flags"])

    def test_invalid_yaml(self, store):
        tool = ConfidenceScoreTool(store)
        result = tool.run(
            gitlab_ci=":::bad", github_actions=":::bad"
        )
        assert result["jobs"] == []
        assert result["overall"] == 0.0

    def test_non_dict_yaml(self, store):
        tool = ConfidenceScoreTool(store)
        result = tool.run(
            gitlab_ci="- list", github_actions="- list"
        )
        assert result["overall"] == 0.0

    def test_templates_skipped(self, store):
        gl = (
            ".base:\n  image: python:3.12\n"
            "build:\n  extends: .base\n"
            "  script: [make build]\n"
        )
        gh = (
            "name: CI\non: push\njobs:\n"
            "  build:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - run: make build\n"
        )
        tool = ConfidenceScoreTool(store)
        result = tool.run(gitlab_ci=gl, github_actions=gh)
        # .base template should be skipped
        job_names = [j["job"] for j in result["jobs"]]
        assert ".base" not in job_names
        assert "build" in job_names


# -----------------------------------------------------------------------
# SuggestWorkflowSplitTool (NEW in v2.0)
# -----------------------------------------------------------------------


class TestSuggestWorkflowSplitTool:
    def test_small_pipeline_no_split(self, store):
        gl = (
            "stages: [build, test]\n"
            "build:\n  stage: build\n  script: [make]\n"
            "test:\n  stage: test\n  script: [pytest]\n"
        )
        tool = SuggestWorkflowSplitTool(store)
        result = tool.run(gitlab_ci=gl)
        assert result["should_split"] is False
        assert "only" in result["reason"].lower()

    def test_large_pipeline_split(self, store):
        tool = SuggestWorkflowSplitTool(store)
        result = tool.run(gitlab_ci=LARGE_PIPELINE)
        assert result["should_split"] is True
        assert result["total_jobs"] == 7
        wf_names = [w["name"] for w in result["workflows"]]
        assert "deploy.yml" in wf_names
        assert "security.yml" in wf_names

    def test_trigger_hints(self, store):
        tool = SuggestWorkflowSplitTool(store)
        result = tool.run(gitlab_ci=LARGE_PIPELINE)
        for wf in result["workflows"]:
            assert "trigger_hint" in wf

    def test_invalid_yaml(self, store):
        tool = SuggestWorkflowSplitTool(store)
        result = tool.run(gitlab_ci=":::bad")
        assert result["should_split"] is False

    def test_single_category(self, store):
        gl = (
            "stages: [build, test, lint, check, verify]\n"
            "build:\n  stage: build\n  script: [make]\n"
            "test:\n  stage: test\n  script: [pytest]\n"
            "lint:\n  stage: lint\n  script: [ruff]\n"
            "check:\n  stage: check\n  script: [mypy]\n"
            "verify:\n  stage: verify\n  script: [verify]\n"
        )
        tool = SuggestWorkflowSplitTool(store)
        result = tool.run(gitlab_ci=gl)
        # All jobs are CI category
        assert result["should_split"] is False


# -----------------------------------------------------------------------
# RecordFeedbackTool (NEW in v2.0)
# -----------------------------------------------------------------------


class TestRecordFeedbackTool:
    def test_record_feedback(self, tmp_path):
        tool = RecordFeedbackTool()
        # Override feedback dir to temp
        tool.FEEDBACK_DIR = tmp_path / "feedback"

        result = tool.run(
            gitlab_ci="test:\n  script: [pytest]\n",
            original_output="name: CI\non: push\njobs: {}",
            corrected_output=(
                "name: CI\non: push\njobs:\n"
                "  test:\n    runs-on: ubuntu-latest\n"
                "    steps:\n      - run: pytest\n"
            ),
            notes="Missing test job",
        )
        assert result["recorded"] is True
        assert "feedback_id" in result

        # Check files were written
        feedback_dir = Path(result["path"])
        assert (feedback_dir / "gitlab-ci.yml").exists()
        assert (feedback_dir / "original.yml").exists()
        assert (feedback_dir / "corrected.yml").exists()
        meta = json.loads(
            (feedback_dir / "metadata.json").read_text()
        )
        assert meta["notes"] == "Missing test job"

    def test_record_without_notes(self, tmp_path):
        tool = RecordFeedbackTool()
        tool.FEEDBACK_DIR = tmp_path / "feedback"

        result = tool.run(
            gitlab_ci="x:\n  script: [echo]\n",
            original_output="original",
            corrected_output="corrected",
        )
        assert result["recorded"] is True


# -----------------------------------------------------------------------
# build_index_from_disk
# -----------------------------------------------------------------------


class TestBuildIndex:
    def test_builds_successfully(self):
        store = build_index_from_disk()
        stats = store.stats()
        assert stats["total_documents"] > 0

    def test_indexes_conversion_pairs(self):
        store = build_index_from_disk()
        pairs = store.get_conversion_pairs(
            "node simple CI", n_results=1
        )
        assert len(pairs) > 0


# -----------------------------------------------------------------------
# MCP Server tool listing and dispatch
# -----------------------------------------------------------------------


class TestMCPServerTools:
    def test_tools_list(self):
        from mcp_server.server import TOOLS
        names = [t.name for t in TOOLS]
        assert "find_similar_gitlab_pattern" in names
        assert "get_conversion_example" in names
        assert "validate_against_corpus" in names
        assert "suggest_github_action" in names
        assert "index_stats" in names
        assert "confidence_score" in names
        assert "suggest_workflow_split" in names
        assert "record_feedback" in names
        assert len(TOOLS) == 8

    @pytest.mark.asyncio
    async def test_call_tool_index_stats(self):
        """Test index_stats tool logic via direct store call."""
        store = build_index_from_disk()
        stats = store.stats()
        assert "total_documents" in stats

    @pytest.mark.asyncio
    async def test_call_tool_unknown(self):
        """Test that TOOLS list has no unknown/duplicate names."""
        from mcp_server.server import TOOLS
        names = [t.name for t in TOOLS]
        assert len(names) == len(set(names)), "Duplicate tool names"
