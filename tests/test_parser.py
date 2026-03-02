"""Tests for GitLab CI parser."""

import pytest
from gl2gh.parser import GitLabCIParser


class TestGitLabCIParser:
    def setup_method(self):
        self.parser = GitLabCIParser()

    def test_parse_simple_pipeline(self, simple_gitlab_ci):
        pipeline = self.parser.parse_string(simple_gitlab_ci)
        assert len(pipeline.stages) == 3
        assert "build" in pipeline.stages
        non_template_jobs = {n: j for n, j in pipeline.jobs.items() if not j.is_template}
        assert len(non_template_jobs) == 3
        assert "build" in non_template_jobs
        assert "test" in non_template_jobs
        assert "deploy" in non_template_jobs

    def test_parse_job_properties(self, simple_gitlab_ci):
        pipeline = self.parser.parse_string(simple_gitlab_ci)
        build_job = pipeline.jobs["build"]
        assert build_job.stage == "build"
        assert build_job.image == "node:18"
        assert "npm ci" in build_job.script
        assert build_job.artifacts is not None
        assert "dist/" in build_job.artifacts.paths

    def test_parse_environment(self, simple_gitlab_ci):
        pipeline = self.parser.parse_string(simple_gitlab_ci)
        deploy_job = pipeline.jobs["deploy"]
        assert deploy_job.environment is not None
        assert deploy_job.environment.name == "production"
        assert deploy_job.environment.url == "https://example.com"

    def test_parse_only_except(self, simple_gitlab_ci):
        pipeline = self.parser.parse_string(simple_gitlab_ci)
        deploy_job = pipeline.jobs["deploy"]
        assert deploy_job.only is not None

    def test_parse_variables(self, simple_gitlab_ci):
        pipeline = self.parser.parse_string(simple_gitlab_ci)
        assert "NODE_VERSION" in pipeline.variables
        assert pipeline.variables["NODE_VERSION"] == "18"

    def test_parse_complex_pipeline(self, complex_gitlab_ci):
        pipeline = self.parser.parse_string(complex_gitlab_ci)
        assert len(pipeline.stages) == 4
        assert "security" in pipeline.stages

    def test_parse_extends(self, complex_gitlab_ci):
        pipeline = self.parser.parse_string(complex_gitlab_ci)
        build_job = pipeline.jobs["build"]
        # After extends resolution, build should inherit from .base_job
        assert build_job.image == "python:3.11"

    def test_parse_services(self, complex_gitlab_ci):
        pipeline = self.parser.parse_string(complex_gitlab_ci)
        test_job = pipeline.jobs["test"]
        assert len(test_job.services) == 2

    def test_parse_parallel_matrix(self, complex_gitlab_ci):
        pipeline = self.parser.parse_string(complex_gitlab_ci)
        test_job = pipeline.jobs["test"]
        assert test_job.parallel is not None
        assert len(test_job.parallel.matrix) > 0

    def test_parse_rules(self, complex_gitlab_ci):
        pipeline = self.parser.parse_string(complex_gitlab_ci)
        security_job = pipeline.jobs["security_scan"]
        assert len(security_job.rules) == 2

    def test_parse_allow_failure(self, complex_gitlab_ci):
        pipeline = self.parser.parse_string(complex_gitlab_ci)
        security_job = pipeline.jobs["security_scan"]
        assert security_job.allow_failure is True

    def test_parse_docker_pipeline(self, docker_gitlab_ci):
        pipeline = self.parser.parse_string(docker_gitlab_ci)
        assert len(pipeline.jobs) == 2
        build_job = pipeline.jobs["build_image"]
        assert build_job.image == "docker:24"
        assert len(build_job.services) == 1

    def test_parse_empty_string(self):
        pipeline = self.parser.parse_string("")
        assert len(pipeline.jobs) == 0

    def test_parse_minimal(self):
        pipeline = self.parser.parse_string("job1:\n  script: echo hello")
        assert "job1" in pipeline.jobs
