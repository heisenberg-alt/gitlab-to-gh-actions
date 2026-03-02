"""Tests for the rule-based converter."""

import yaml
import pytest
from gl2gh.parser import GitLabCIParser
from gl2gh.converter import GitLabToGitHubConverter


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
        yaml_lines = [l for l in content.split("\n") if not l.startswith("#")]
        workflow = yaml.safe_load("\n".join(yaml_lines))
        assert "name" in workflow
        assert "on" in workflow
        assert "jobs" in workflow

    def test_jobs_have_steps(self, simple_gitlab_ci):
        pipeline = self.parser.parse_string(simple_gitlab_ci)
        result = self.converter.convert(pipeline)
        content = list(result.output_workflows.values())[0]
        yaml_lines = [l for l in content.split("\n") if not l.startswith("#")]
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
