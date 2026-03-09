"""Tests for the shared convert_handler utility."""

from gl2gh.utils.convert_handler import convert_gitlab_yaml


class TestConvertGitlabYaml:
    def test_success_simple(self):
        content = (
            "stages:\n  - build\n\n"
            "build:\n  stage: build\n  script:\n    - echo hi\n"
        )
        result = convert_gitlab_yaml(content)
        assert result["success"] is True
        assert "workflow" in result
        assert "workflows" in result
        assert isinstance(result["warnings"], list)
        assert isinstance(result["notes"], list)

    def test_empty_content(self):
        result = convert_gitlab_yaml("")
        assert result["success"] is False
        assert "empty" in result["errors"][0].lower()

    def test_whitespace_only(self):
        result = convert_gitlab_yaml("   \n  \n  ")
        assert result["success"] is False

    def test_no_jobs_failure(self):
        result = convert_gitlab_yaml("variables:\n  FOO: bar\n")
        assert result["success"] is False
        assert len(result["errors"]) > 0
        assert "warnings" in result

    def test_workflows_dict_contains_filename(self):
        content = "build:\n  stage: build\n  script:\n    - make\n"
        result = convert_gitlab_yaml(content)
        assert result["success"] is True
        assert len(result["workflows"]) >= 1
        # Default workflow filename is ci.yml
        assert any(fn.endswith(".yml") for fn in result["workflows"])

    def test_trigger_produces_multiple_workflows(self):
        content = """\
stages:
  - build
  - deploy

build:
  stage: build
  script:
    - echo build

deploy_child:
  stage: deploy
  trigger:
    include: ci/deploy.yml
"""
        result = convert_gitlab_yaml(content)
        assert result["success"] is True
        assert len(result["workflows"]) >= 2
