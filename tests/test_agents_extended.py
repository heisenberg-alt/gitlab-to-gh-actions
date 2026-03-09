"""Extended agent tests for more coverage of optimizer and validator."""


from gl2gh.agents.optimizer_agent import OptimizerAgent
from gl2gh.agents.validator_agent import ValidatorAgent

WORKFLOW_WITH_TIMEOUT = """\
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - run: make build
"""

WORKFLOW_WITH_CACHE = """\
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/cache@v4
        with:
          path: node_modules
          key: deps-${{ hashFiles('package-lock.json') }}
      - run: npm test
"""

WORKFLOW_WITH_CONCURRENCY = """\
name: CI
on: push
concurrency:
  group: ${{ github.ref }}
  cancel-in-progress: true
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make
"""

WORKFLOW_WITH_MATRIX = """\
name: CI
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python: ["3.10", "3.11"]
    steps:
      - uses: actions/checkout@v4
      - run: pytest
"""

WORKFLOW_MANY_INDEPENDENT = """\
name: CI
on: push
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make lint
  test1:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make test1
  test2:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make test2
  test3:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make test3
"""

WORKFLOW_NO_CHECKOUT = """\
name: CI
on: push
jobs:
  notify:
    runs-on: ubuntu-latest
    steps:
      - run: curl https://hooks.slack.com/...
"""

WORKFLOW_STEP_NO_USES_OR_RUN = """\
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: "Empty step"
        env:
          FOO: bar
"""

WORKFLOW_NON_DICT_JOB = """\
name: CI
on: push
jobs:
  build: "not a dict"
"""

WORKFLOW_STEPS_NOT_LIST = """\
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps: "not a list"
"""

WORKFLOW_MISSING_NAME = """\
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""

WORKFLOW_ON_TYPE_INVALID = """\
name: CI
on: 42
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""

WORKFLOW_JOBS_NOT_DICT = """\
name: CI
on: push
jobs:
  - step1
  - step2
"""


class TestOptimizerExtended:
    def setup_method(self):
        self.optimizer = OptimizerAgent()

    def test_timeout_present_increases_score(self):
        report = self.optimizer.optimize(WORKFLOW_WITH_TIMEOUT)
        assert report.score_before >= 55

    def test_cache_present_increases_score(self):
        report = self.optimizer.optimize(WORKFLOW_WITH_CACHE)
        assert report.score_before >= 60

    def test_concurrency_increases_score(self):
        report = self.optimizer.optimize(WORKFLOW_WITH_CONCURRENCY)
        # concurrency adds 10 to base 50
        assert report.score_before >= 60

    def test_matrix_increases_score(self):
        report = self.optimizer.optimize(WORKFLOW_WITH_MATRIX)
        assert report.score_before >= 55

    def test_many_independent_parallelism_warning(self):
        report = self.optimizer.optimize(WORKFLOW_MANY_INDEPENDENT)
        cats = [o.category for o in report.optimizations]
        assert "parallelism" in cats

    def test_no_checkout_flagged(self):
        report = self.optimizer.optimize(WORKFLOW_NO_CHECKOUT)
        descs = [o.description for o in report.optimizations]
        assert any("checkout" in d.lower() for d in descs)

    def test_no_timeout_flagged_for_all_jobs(self):
        report = self.optimizer.optimize(WORKFLOW_MANY_INDEPENDENT)
        timeout_opts = [
            o for o in report.optimizations
            if "timeout" in o.description.lower()
        ]
        # Should flag ALL 4 jobs, not just the first
        assert len(timeout_opts) == 4

    def test_non_dict_workflow(self):
        report = self.optimizer.optimize("- just\n- a\n- list")
        assert report.score_before == 0

    def test_empty_jobs(self):
        wf = "name: CI\non: push\njobs: {}\n"
        report = self.optimizer.optimize(wf)
        assert report.score_before == 50

    def test_non_dict_jobs(self):
        wf = "name: CI\non: push\njobs: null\n"
        report = self.optimizer.optimize(wf)
        assert report.score_before == 0

    def test_score_after_higher(self):
        report = self.optimizer.optimize(WORKFLOW_NO_CHECKOUT)
        assert report.score_after >= report.score_before


class TestValidatorExtended:
    def setup_method(self):
        self.validator = ValidatorAgent()

    def test_non_dict_workflow(self):
        issues = self.validator.validate_static("- a\n- b")
        assert any("mapping" in i.message.lower() for i in issues)

    def test_missing_name_key(self):
        issues = self.validator.validate_static(WORKFLOW_MISSING_NAME)
        assert any("name" in i.message for i in issues)

    def test_on_invalid_type(self):
        issues = self.validator.validate_static(WORKFLOW_ON_TYPE_INVALID)
        assert any("'on'" in i.message for i in issues)

    def test_jobs_not_dict(self):
        issues = self.validator.validate_static(WORKFLOW_JOBS_NOT_DICT)
        assert any(
            "jobs" in i.message.lower()
            and "mapping" in i.message.lower()
            for i in issues
        )

    def test_non_dict_job_def(self):
        issues = self.validator.validate_static(WORKFLOW_NON_DICT_JOB)
        assert any("must be a mapping" in i.message for i in issues)

    def test_step_without_uses_or_run(self):
        issues = self.validator.validate_static(WORKFLOW_STEP_NO_USES_OR_RUN)
        assert any("'uses' or 'run'" in i.message for i in issues)

    def test_commit_message_injection(self):
        content = """\
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ github.event.head_commit.message }}
"""
        issues = self.validator.validate_static(content)
        assert any("injection" in i.message.lower() for i in issues)

    def test_comment_body_injection(self):
        content = """\
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ github.event.comment.body }}
"""
        issues = self.validator.validate_static(content)
        assert any("injection" in i.message.lower() for i in issues)

    def test_on_as_string_valid(self):
        content = """\
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""
        issues = self.validator.validate_static(content)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_on_as_list_valid(self):
        content = """\
name: CI
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""
        issues = self.validator.validate_static(content)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_expression_runner_no_warning(self):
        content = """\
name: CI
on: push
jobs:
  build:
    runs-on: ${{ matrix.os }}
    steps:
      - run: echo hi
"""
        issues = self.validator.validate_static(content)
        assert not any("non-standard runner" in i.message for i in issues)

    def test_on_key_parsed_as_true(self):
        """YAML 1.1 parses bare 'on' as boolean True; validator should handle it."""
        content = """\
name: CI
on:
  push:
    branches: [main]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""
        issues = self.validator.validate_static(content)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0


class TestOptimizerWithAI:
    """Test optimize_with_ai when copilot import fails (fallback path)."""

    def setup_method(self):
        self.optimizer = OptimizerAgent()

    def test_optimize_with_ai_import_fails(self):
        """When copilot is not installed, should fall back gracefully."""
        report = self.optimizer.optimize_with_ai(
            WORKFLOW_WITH_CACHE, github_token="fake-token"
        )
        # Should still return a report from static analysis
        assert report.score_before >= 0

    def test_optimize_with_ai_custom_model(self):
        report = self.optimizer.optimize_with_ai(
            WORKFLOW_WITH_CACHE, github_token="fake-token", model="gpt-4"
        )
        assert report.score_before >= 0


class TestValidatorWithAI:
    """Test validate_with_ai when copilot import fails (fallback path)."""

    def setup_method(self):
        self.validator = ValidatorAgent()

    def test_validate_with_ai_import_fails(self):
        """When copilot is not installed, should fall back to static results."""
        content = """\
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""
        issues = self.validator.validate_with_ai(
            content, github_token="fake-token"
        )
        # Should have at least the static results + an info about AI unavailable
        assert any("unavailable" in i.message.lower() for i in issues)

    def test_validate_with_ai_custom_model(self):
        content = (
            "name: CI\non: push\njobs:\n  build:"
            "\n    runs-on: ubuntu-latest"
            "\n    steps:\n      - run: echo hi\n"
        )
        issues = self.validator.validate_with_ai(
            content, github_token="fake-token", model="gpt-4"
        )
        assert isinstance(issues, list)


class TestMigrationAgentBasic:
    """Test MigrationAgent without actual AI calls."""

    def test_migrate_simple_no_ai_needed(self):
        """A simple pipeline with no warnings should skip AI."""
        from gl2gh.agents.migration_agent import MigrationAgent
        from gl2gh.parser import GitLabCIParser

        parser = GitLabCIParser()
        pipeline = parser.parse_string(
            "stages:\n  - build\n\nbuild:\n  stage: build\n  script:\n    - make\n"
        )
        agent = MigrationAgent(github_token="fake")
        result = agent.migrate(pipeline)
        assert result.success
        # Should NOT be AI enhanced since it's simple
        assert result.ai_enhanced is False

    def test_migrate_complex_falls_back(self):
        """Complex pipeline triggers AI path which fails and falls back."""
        from gl2gh.agents.migration_agent import MigrationAgent
        from gl2gh.parser import GitLabCIParser

        content = """\
stages:
  - test

test:
  stage: test
  script:
    - pytest
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
"""
        parser = GitLabCIParser()
        pipeline = parser.parse_string(content)
        agent = MigrationAgent(github_token="fake")
        result = agent.migrate(pipeline)
        # Should succeed (falls back to rule-based)
        assert result.success
        # Should have a warning about AI failure
        assert any("AI enhancement failed" in w for w in result.warnings)

    def test_migrate_repository_fails_gracefully(self):
        """migrate_repository should return False when copilot is unavailable."""
        from gl2gh.agents.migration_agent import MigrationAgent

        agent = MigrationAgent(github_token="fake")
        success = agent.migrate_repository("source", "target")
        assert success is False

    def test_summarize_pipeline(self):
        """Test _summarize_pipeline produces readable output."""
        from gl2gh.agents.migration_agent import MigrationAgent
        from gl2gh.parser import GitLabCIParser

        content = """\
stages:
  - build
  - test

variables:
  NODE_ENV: production

image: python:3.11

.template:
  tags:
    - docker

build:
  stage: build
  extends: .template
  script:
    - make

test:
  stage: test
  script:
    - pytest
  rules:
    - if: '$CI_COMMIT_BRANCH'
  parallel:
    matrix:
      - PY: ["3.10", "3.11"]
  environment: staging
"""
        parser = GitLabCIParser()
        pipeline = parser.parse_string(content)
        agent = MigrationAgent(github_token="fake")
        summary = agent._summarize_pipeline(pipeline)
        assert "Stages:" in summary
        assert "Jobs:" in summary
        assert "build" in summary
        assert "test" in summary
        assert "Default image:" in summary
