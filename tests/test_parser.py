"""Tests for GitLab CI parser."""

from gl2gh.parser import GitLabCIParser


class TestGitLabCIParser:
    def setup_method(self):
        self.parser = GitLabCIParser()

    def test_parse_simple_pipeline(self, simple_gitlab_ci):
        pipeline = self.parser.parse_string(simple_gitlab_ci)
        assert len(pipeline.stages) == 3
        assert "build" in pipeline.stages
        non_template_jobs = {
            n: j for n, j in pipeline.jobs.items() if not j.is_template
        }
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

    def test_extends_merges_rules(self):
        content = """\
.base:
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'

job1:
  extends: .base
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        job = pipeline.jobs["job1"]
        assert len(job.rules) == 1
        assert job.rules[0]["if"] == '$CI_COMMIT_BRANCH == "main"'

    def test_extends_merges_timeout(self):
        content = """\
.base:
  timeout: 2h

job1:
  extends: .base
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].timeout == "2h"

    def test_extends_merges_retry(self):
        content = """\
.base:
  retry:
    max: 2
    when:
      - runner_system_failure

job1:
  extends: .base
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].retry is not None
        assert pipeline.jobs["job1"].retry.max == 2

    def test_extends_does_not_overwrite_job_rules(self):
        content = """\
.base:
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'

job1:
  extends: .base
  rules:
    - if: '$CI_COMMIT_TAG'
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        job = pipeline.jobs["job1"]
        assert len(job.rules) == 1
        assert "$CI_COMMIT_TAG" in job.rules[0]["if"]

    def test_parse_boolean_variable(self):
        """YAML boolean values should be lowercased in parsed variables."""
        content = """\
variables:
  ENABLED: true
  DISABLED: false

job1:
  script:
    - echo hi
  variables:
    DEBUG: true
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.variables["ENABLED"] == "true"
        assert pipeline.variables["DISABLED"] == "false"
        assert pipeline.jobs["job1"].variables["DEBUG"] == "true"

    def test_parse_null_variable(self):
        """Null variable values should become empty strings."""
        content = """\
job1:
  script:
    - echo hi
  variables:
    EMPTY_VAR:
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].variables["EMPTY_VAR"] == ""

    def test_extends_merges_variables(self):
        """Template variables should be merged with job variables."""
        content = """\
.base:
  variables:
    FROM_TEMPLATE: template_val
    SHARED: base

job1:
  extends: .base
  script:
    - echo hi
  variables:
    OWN_VAR: own_val
    SHARED: override
"""
        pipeline = self.parser.parse_string(content)
        job = pipeline.jobs["job1"]
        assert job.variables["FROM_TEMPLATE"] == "template_val"
        assert job.variables["OWN_VAR"] == "own_val"
        assert job.variables["SHARED"] == "override"

    def test_extends_inherits_variables_when_job_has_none(self):
        """Job without variables should inherit all template variables."""
        content = """\
.base:
  variables:
    FROM_TEMPLATE: template_val

job1:
  extends: .base
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        job = pipeline.jobs["job1"]
        assert job.variables["FROM_TEMPLATE"] == "template_val"
