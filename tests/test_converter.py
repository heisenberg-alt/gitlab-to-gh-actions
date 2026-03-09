"""Tests for the rule-based converter."""

import yaml

from gl2gh.converter import GitLabToGitHubConverter
from gl2gh.parser import GitLabCIParser


class TestGitLabToGitHubConverter:
    def setup_method(self):
        self.parser = GitLabCIParser()
        self.converter = GitLabToGitHubConverter()

    def test_convert_simple(self, simple_gitlab_ci):
        pipeline = self.parser.parse_string(simple_gitlab_ci)
        result = self.converter.convert(pipeline)
        assert result.success
        assert len(result.output_workflows) == 1
        assert len(result.errors) == 0

    def test_workflow_has_required_keys(self, simple_gitlab_ci):
        pipeline = self.parser.parse_string(simple_gitlab_ci)
        result = self.converter.convert(pipeline)
        content = list(result.output_workflows.values())[0]
        # Skip comment header lines
        yaml_lines = [line for line in content.split("\n") if not line.startswith("#")]
        workflow = yaml.safe_load("\n".join(yaml_lines))
        assert "name" in workflow
        assert "on" in workflow
        assert "jobs" in workflow

    def test_jobs_have_steps(self, simple_gitlab_ci):
        pipeline = self.parser.parse_string(simple_gitlab_ci)
        result = self.converter.convert(pipeline)
        content = list(result.output_workflows.values())[0]
        yaml_lines = [line for line in content.split("\n") if not line.startswith("#")]
        workflow = yaml.safe_load("\n".join(yaml_lines))
        for job_name, job_def in workflow["jobs"].items():
            assert "steps" in job_def
            assert "runs-on" in job_def

    def test_checkout_step_present(self, simple_gitlab_ci):
        pipeline = self.parser.parse_string(simple_gitlab_ci)
        result = self.converter.convert(pipeline)
        content = list(result.output_workflows.values())[0]
        assert "actions/checkout@v4" in content

    def test_artifacts_conversion(self, simple_gitlab_ci):
        pipeline = self.parser.parse_string(simple_gitlab_ci)
        result = self.converter.convert(pipeline)
        content = list(result.output_workflows.values())[0]
        assert "actions/upload-artifact@v4" in content

    def test_complex_conversion(self, complex_gitlab_ci):
        pipeline = self.parser.parse_string(complex_gitlab_ci)
        result = self.converter.convert(pipeline)
        assert result.success

    def test_docker_conversion(self, docker_gitlab_ci):
        pipeline = self.parser.parse_string(docker_gitlab_ci)
        result = self.converter.convert(pipeline)
        assert result.success

    def test_variable_translation(self, docker_gitlab_ci):
        pipeline = self.parser.parse_string(docker_gitlab_ci)
        result = self.converter.convert(pipeline)
        content = list(result.output_workflows.values())[0]
        assert "$CI_REGISTRY_IMAGE" not in content or "ghcr.io" in content

    def test_services_conversion(self, complex_gitlab_ci):
        pipeline = self.parser.parse_string(complex_gitlab_ci)
        result = self.converter.convert(pipeline)
        content = list(result.output_workflows.values())[0]
        assert "services:" in content or "Service" in str(result.warnings)

    def test_empty_pipeline_error(self):
        pipeline = self.parser.parse_string("variables:\n  FOO: bar")
        result = self.converter.convert(pipeline)
        assert not result.success
        assert len(result.errors) > 0

    def test_custom_workflow_name(self, simple_gitlab_ci):
        converter = GitLabToGitHubConverter(workflow_name="My Pipeline")
        pipeline = self.parser.parse_string(simple_gitlab_ci)
        result = converter.convert(pipeline)
        content = list(result.output_workflows.values())[0]
        assert "My Pipeline" in content

    def test_trigger_child_pipeline(self):
        """trigger: include: generates a reusable workflow and caller job."""
        content = """
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
        pipeline = self.parser.parse_string(content)
        result = self.converter.convert(pipeline)
        assert result.success

        # Main workflow should contain the caller job
        main_wf = list(result.output_workflows.values())[0]
        assert "uses:" in main_wf or "workflow_call" in str(result.output_workflows)

        # A child reusable workflow file should be generated
        assert len(result.output_workflows) >= 2
        child_keys = [k for k in result.output_workflows if k != "ci.yml"]
        assert len(child_keys) >= 1
        child_content = result.output_workflows[child_keys[0]]
        assert "workflow_call" in child_content


class TestConvertEnhanced:
    """Tests for convert_enhanced (validation + optimization post-processing)."""

    def setup_method(self):
        self.parser = GitLabCIParser()
        self.converter = GitLabToGitHubConverter()

    def test_enhanced_returns_optimization_score(self, simple_gitlab_ci):
        pipeline = self.parser.parse_string(simple_gitlab_ci)
        result = self.converter.convert_enhanced(pipeline)
        assert result.success
        assert result.optimization_score is not None
        assert 0 <= result.optimization_score <= 100

    def test_enhanced_populates_validation_issues(self, simple_gitlab_ci):
        pipeline = self.parser.parse_string(simple_gitlab_ci)
        result = self.converter.convert_enhanced(pipeline)
        assert result.success
        # validation_issues is a list (may be empty for clean workflows)
        assert isinstance(result.validation_issues, list)

    def test_enhanced_adds_conversion_notes(self, simple_gitlab_ci):
        pipeline = self.parser.parse_string(simple_gitlab_ci)
        result = self.converter.convert_enhanced(pipeline)
        assert result.success
        # Should have at least one optimization note
        assert len(result.conversion_notes) > 0

    def test_enhanced_empty_pipeline_still_fails(self):
        pipeline = self.parser.parse_string("variables:\n  FOO: bar")
        result = self.converter.convert_enhanced(pipeline)
        assert not result.success
        # Should not have optimization_score since conversion itself failed
        assert result.optimization_score is None

    def test_enhanced_low_score_suggests_ai(self, simple_gitlab_ci):
        pipeline = self.parser.parse_string(simple_gitlab_ci)
        result = self.converter.convert_enhanced(pipeline)
        if result.optimization_score is not None and result.optimization_score < 60:
            assert any("--ai" in note for note in result.conversion_notes)

    def test_trigger_cross_project(self):
        """trigger: project: generates a uses: reference without child file."""
        content = """
stages:
  - build
  - deploy

build:
  stage: build
  script:
    - echo build

infra:
  stage: deploy
  trigger:
    project: org/infra-repo
    branch: main
"""
        pipeline = self.parser.parse_string(content)
        result = self.converter.convert(pipeline)
        assert result.success

        main_wf = list(result.output_workflows.values())[0]
        assert "org/infra-repo" in main_wf
        assert any("cross-project" in w for w in result.warnings)

    def test_trigger_preserves_needs(self):
        """Trigger jobs should preserve stage-based dependency ordering."""
        content = """
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
        pipeline = self.parser.parse_string(content)
        result = self.converter.convert(pipeline)
        assert result.success

        main_wf = list(result.output_workflows.values())[0]
        wf = yaml.safe_load(
            "\n".join(line for line in main_wf.split("\n") if not line.startswith("#"))
        )
        deploy_job = wf["jobs"].get("deploy_child")
        assert deploy_job is not None
        assert "needs" in deploy_job
        assert "build" in deploy_job["needs"]

    def test_duplicate_service_names(self):
        """Two services with the same base name should not overwrite each other."""
        content = """
stages:
  - test

test:
  stage: test
  image: python:3.11
  services:
    - postgres:14
    - my-registry/postgres:15
  script:
    - pytest
"""
        pipeline = self.parser.parse_string(content)
        result = self.converter.convert(pipeline)
        assert result.success
        main_wf = list(result.output_workflows.values())[0]
        wf = yaml.safe_load(
            "\n".join(line for line in main_wf.split("\n") if not line.startswith("#"))
        )
        services = wf["jobs"]["test"]["services"]
        assert len(services) == 2
