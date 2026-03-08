"""Tests for validator and optimizer agents (static checks only, no AI)."""

from gl2gh.agents.optimizer_agent import OptimizerAgent
from gl2gh.agents.validator_agent import ValidatorAgent

VALID_WORKFLOW = """\
name: CI
on:
  push:
    branches: [main]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: echo "hello"
"""

MINIMAL_WORKFLOW_NO_CACHE = """\
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make build
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make test
"""


class TestValidatorAgent:
    def setup_method(self):
        self.validator = ValidatorAgent()

    def test_valid_workflow(self):
        issues = self.validator.validate_static(VALID_WORKFLOW)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_invalid_yaml(self):
        issues = self.validator.validate_static("not: [valid: yaml: {{")
        assert any(i.severity == "error" for i in issues)

    def test_missing_jobs_key(self):
        issues = self.validator.validate_static("name: CI\non: push\n")
        assert any("jobs" in i.message for i in issues)

    def test_missing_runs_on(self):
        content = """\
name: CI
on: push
jobs:
  build:
    steps:
      - run: echo hi
"""
        issues = self.validator.validate_static(content)
        assert any("runs-on" in i.message for i in issues)

    def test_security_pattern_detected(self):
        content = """\
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ github.event.issue.title }}
"""
        issues = self.validator.validate_static(content)
        assert any(
            i.severity == "warning" and "injection" in i.message.lower() for i in issues
        )

    def test_non_standard_runner_info(self):
        content = """\
name: CI
on: push
jobs:
  build:
    runs-on: my-custom-runner
    steps:
      - run: echo hi
"""
        issues = self.validator.validate_static(content)
        assert any(i.severity == "info" and "non-standard" in i.message for i in issues)

    def test_reusable_workflow_caller_no_false_positive(self):
        """Jobs with only 'uses:' (reusable workflow callers) should not flag missing runs-on/steps."""
        content = """\
name: CI
on: push
jobs:
  deploy:
    uses: ./.github/workflows/deploy.yml
"""
        issues = self.validator.validate_static(content)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_pr_title_injection_detected(self):
        content = """\
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ github.event.pull_request.title }}
"""
        issues = self.validator.validate_static(content)
        assert any(
            i.severity == "warning" and "injection" in i.message.lower() for i in issues
        )


class TestOptimizerAgent:
    def setup_method(self):
        self.optimizer = OptimizerAgent()

    def test_optimize_returns_report(self):
        report = self.optimizer.optimize(VALID_WORKFLOW)
        assert report.score_before >= 0

    def test_no_cache_suggestion(self):
        report = self.optimizer.optimize(MINIMAL_WORKFLOW_NO_CACHE)
        cats = [o.category for o in report.optimizations]
        assert "caching" in cats

    def test_no_concurrency_suggestion(self):
        report = self.optimizer.optimize(VALID_WORKFLOW)
        cats = [o.category for o in report.optimizations]
        assert "cost" in cats

    def test_invalid_yaml_returns_empty(self):
        report = self.optimizer.optimize("not: [valid: {{")
        assert report.score_before == 0
        assert report.optimizations == []

    def test_score_increases_with_optimizations(self):
        report = self.optimizer.optimize(MINIMAL_WORKFLOW_NO_CACHE)
        assert report.score_after >= report.score_before
