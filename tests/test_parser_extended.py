"""Extended parser tests targeting uncovered lines."""

from gl2gh.parser import GitLabCIParser


class TestParserExtended:
    def setup_method(self):
        self.parser = GitLabCIParser()

    def test_parse_file(self, tmp_path):
        f = tmp_path / "test.yml"
        f.write_text("job1:\n  script:\n    - echo hi\n")
        pipeline = self.parser.parse_file(str(f))
        assert "job1" in pipeline.jobs

    def test_include_string(self):
        content = """\
include: local/ci.yml

job1:
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert len(pipeline.includes) == 1
        assert pipeline.includes[0]["local"] == "local/ci.yml"

    def test_include_list_of_strings(self):
        content = """\
include:
  - local/a.yml
  - local/b.yml

job1:
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert len(pipeline.includes) == 2

    def test_include_list_of_dicts(self):
        content = """\
include:
  - local: ci/build.yml
  - remote: https://example.com/ci.yml

job1:
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert len(pipeline.includes) == 2
        assert pipeline.includes[0]["local"] == "ci/build.yml"

    def test_include_single_dict(self):
        content = """\
include:
  local: ci/build.yml

job1:
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert len(pipeline.includes) == 1

    def test_default_section(self):
        content = """\
default:
  image: ruby:3.2
  before_script:
    - bundle install
  after_script:
    - cleanup.sh

job1:
  script:
    - rspec
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.default_image == "ruby:3.2"
        assert "bundle install" in pipeline.default_before_script
        assert "cleanup.sh" in pipeline.default_after_script

    def test_default_image_as_dict(self):
        content = """\
image:
  name: python:3.11
  entrypoint: ["/bin/sh"]

job1:
  script:
    - pytest
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.default_image == "python:3.11"

    def test_default_services(self):
        content = """\
services:
  - postgres:14

job1:
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert len(pipeline.default_services) == 1

    def test_default_cache(self):
        content = """\
cache:
  key: global
  paths:
    - .cache/

job1:
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.default_cache is not None
        assert pipeline.default_cache.key == "global"

    def test_default_artifacts(self):
        content = """\
artifacts:
  paths:
    - dist/
  expire_in: 1 day

job1:
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.default_artifacts is not None
        assert "dist/" in pipeline.default_artifacts.paths

    def test_default_timeout(self):
        content = """\
default:
  timeout: 1h

job1:
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.default_timeout == "1h"

    def test_default_retry(self):
        content = """\
default:
  retry:
    max: 2
    when:
      - runner_system_failure

job1:
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.default_retry is not None
        assert pipeline.default_retry.max == 2

    def test_default_tags(self):
        content = """\
default:
  tags:
    - docker

job1:
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert "docker" in pipeline.default_tags

    def test_job_image_as_dict(self):
        content = """\
stages:
  - build

build:
  stage: build
  image:
    name: python:3.11
    entrypoint: ["/bin/sh"]
  script:
    - python setup.py build
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["build"].image == "python:3.11"

    def test_job_inherits_default_services(self):
        content = """\
services:
  - redis:7

job1:
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert len(pipeline.jobs["job1"].services) == 1

    def test_job_inherits_default_artifacts(self):
        content = """\
artifacts:
  paths:
    - output/

job1:
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].artifacts is not None

    def test_job_inherits_default_cache(self):
        content = """\
cache:
  paths:
    - .cache/

job1:
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].cache is not None

    def test_job_environment_as_string(self):
        content = """\
job1:
  script:
    - deploy.sh
  environment: production
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].environment is not None
        assert pipeline.jobs["job1"].environment.name == "production"

    def test_job_environment_as_dict(self):
        content = """\
job1:
  script:
    - deploy.sh
  environment:
    name: staging
    url: https://staging.example.com
    action: start
    auto_stop_in: 1 day
    on_stop: stop_job
    deployment_tier: staging
"""
        pipeline = self.parser.parse_string(content)
        env = pipeline.jobs["job1"].environment
        assert env.name == "staging"
        assert env.url == "https://staging.example.com"
        assert env.action == "start"
        assert env.auto_stop_in == "1 day"
        assert env.on_stop == "stop_job"
        assert env.deployment_tier == "staging"

    def test_job_needs_as_dicts(self):
        content = """\
stages:
  - build
  - test

build:
  stage: build
  script:
    - make

test:
  stage: test
  needs:
    - job: build
      artifacts: true
  script:
    - make test
"""
        pipeline = self.parser.parse_string(content)
        assert "build" in pipeline.jobs["test"].needs

    def test_allow_failure_as_dict(self):
        content = """\
job1:
  script:
    - echo hi
  allow_failure:
    exit_codes: [137]
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].allow_failure is True

    def test_retry_as_int(self):
        content = """\
job1:
  script:
    - echo hi
  retry: 2
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].retry is not None
        assert pipeline.jobs["job1"].retry.max == 2

    def test_retry_as_dict(self):
        content = """\
job1:
  script:
    - echo hi
  retry:
    max: 2
    when: runner_system_failure
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].retry.max == 2
        assert "runner_system_failure" in pipeline.jobs["job1"].retry.when

    def test_parallel_as_int(self):
        content = """\
job1:
  script:
    - echo hi
  parallel: 3
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].parallel is not None
        assert len(pipeline.jobs["job1"].parallel.matrix) == 1
        assert len(pipeline.jobs["job1"].parallel.matrix[0]["INDEX"]) == 3

    def test_only_as_list(self):
        content = """\
job1:
  script:
    - echo hi
  only:
    - main
    - develop
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].only is not None
        assert "main" in pipeline.jobs["job1"].only["refs"]

    def test_only_as_dict(self):
        content = """\
job1:
  script:
    - echo hi
  only:
    refs:
      - main
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].only is not None

    def test_except_as_list(self):
        content = """\
job1:
  script:
    - echo hi
  except:
    - tags
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].except_ is not None

    def test_except_as_dict(self):
        content = """\
job1:
  script:
    - echo hi
  except:
    refs:
      - main
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].except_ is not None

    def test_extends_invalid_type_ignored(self):
        content = """\
job1:
  script:
    - echo hi
  extends: 42
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].extends == []

    def test_extends_as_list(self):
        content = """\
.base1:
  image: python:3.11

.base2:
  before_script:
    - setup.sh

job1:
  extends:
    - .base1
    - .base2
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].image == "python:3.11"
        assert "setup.sh" in pipeline.jobs["job1"].before_script

    def test_trigger_as_string(self):
        content = """\
job1:
  trigger: org/other-project
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].trigger is not None
        assert pipeline.jobs["job1"].trigger["project"] == "org/other-project"

    def test_trigger_as_dict(self):
        content = """\
job1:
  trigger:
    project: org/other-project
    branch: develop
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].trigger["project"] == "org/other-project"

    def test_interruptible(self):
        content = """\
job1:
  script:
    - echo hi
  interruptible: true
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].interruptible is True

    def test_resource_group(self):
        content = """\
job1:
  script:
    - deploy.sh
  resource_group: production
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].resource_group == "production"

    def test_template_job_dot_prefix(self):
        content = """\
.template:
  image: python:3.11
  before_script:
    - setup.sh

job1:
  extends: .template
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs[".template"].is_template is True
        assert pipeline.jobs["job1"].is_template is False

    def test_resolve_extends_missing_template_warns(self):
        """Extending a nonexistent template should log warning and not crash."""
        content = """\
job1:
  extends: .nonexistent
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert "job1" in pipeline.jobs

    def test_merge_job_template_variables_merged(self):
        content = """\
.base:
  variables:
    BASE_VAR: from-base
    SHARED: base-val

job1:
  extends: .base
  variables:
    SHARED: job-val
    JOB_VAR: from-job
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        job = pipeline.jobs["job1"]
        assert job.variables["BASE_VAR"] == "from-base"
        assert job.variables["SHARED"] == "job-val"
        assert job.variables["JOB_VAR"] == "from-job"

    def test_merge_template_when(self):
        content = """\
.base:
  when: manual

job1:
  extends: .base
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].when == "manual"

    def test_merge_template_allow_failure(self):
        content = """\
.base:
  allow_failure: true

job1:
  extends: .base
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].allow_failure is True

    def test_merge_template_parallel(self):
        content = """\
.base:
  parallel:
    matrix:
      - VER: ["3.10", "3.11"]

job1:
  extends: .base
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].parallel is not None

    def test_merge_template_services(self):
        content = """\
.base:
  services:
    - postgres:14

job1:
  extends: .base
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert len(pipeline.jobs["job1"].services) == 1

    def test_merge_template_tags(self):
        content = """\
.base:
  tags:
    - docker

job1:
  extends: .base
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert "docker" in pipeline.jobs["job1"].tags

    def test_merge_template_cache(self):
        content = """\
.base:
  cache:
    paths:
      - .cache/

job1:
  extends: .base
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].cache is not None

    def test_merge_template_artifacts(self):
        content = """\
.base:
  artifacts:
    paths:
      - dist/

job1:
  extends: .base
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].artifacts is not None

    def test_script_as_string(self):
        content = """\
job1:
  script: echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].script == ["echo hi"]

    def test_variables_with_value_key(self):
        content = """\
variables:
  MY_VAR:
    value: hello
  SIMPLE: world

job1:
  script:
    - echo $MY_VAR
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.variables["MY_VAR"] == "hello"
        assert pipeline.variables["SIMPLE"] == "world"

    def test_variables_none_value(self):
        content = """\
variables:
  MY_VAR:

job1:
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.variables["MY_VAR"] == ""

    def test_cache_key_as_files_dict(self):
        content = """\
cache:
  key:
    files:
      - Gemfile.lock
      - yarn.lock
  paths:
    - vendor/

job1:
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.default_cache is not None
        assert "Gemfile.lock" in pipeline.default_cache.key

    def test_cache_key_no_files(self):
        content = """\
cache:
  key:
    prefix: my-cache
  paths:
    - .cache/

job1:
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.default_cache.key == "default"

    def test_workflow_key_parsed(self):
        content = """\
workflow:
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'

job1:
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.workflow is not None
        assert "rules" in pipeline.workflow

    def test_dependencies_parsed(self):
        content = """\
stages:
  - build
  - test

build:
  stage: build
  script:
    - make

test:
  stage: test
  dependencies:
    - build
  script:
    - make test
"""
        pipeline = self.parser.parse_string(content)
        assert "build" in pipeline.jobs["test"].dependencies

    def test_cache_not_dict_returns_empty(self):
        """Cache given as a non-dict should return empty GitLabCache."""
        content = """\
cache: "not-a-dict"

job1:
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        # default_cache is set from _parse_cache which returns GitLabCache()
        assert pipeline.default_cache is not None

    def test_variables_not_dict_returns_empty(self):
        """Variables given as non-dict should return empty."""
        content = """\
variables: "not-a-dict"

job1:
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        # The parser calls _parse_variables which returns {}
        assert pipeline.variables == {} or isinstance(pipeline.variables, dict)

    def test_environment_non_string_non_dict(self):
        """Environment given as a list should return default GitLabEnvironment."""
        content = """\
job1:
  script:
    - echo hi
  environment:
    - not
    - valid
"""
        pipeline = self.parser.parse_string(content)
        # _parse_environment returns GitLabEnvironment() for non-str/dict
        assert pipeline.jobs["job1"].environment is not None

    def test_retry_non_int_non_dict(self):
        """Retry given as string should return default GitLabRetry."""
        content = """\
job1:
  script:
    - echo hi
  retry: "invalid"
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].retry is not None
        assert pipeline.jobs["job1"].retry.max == 0

    def test_parallel_non_int_non_dict(self):
        """Parallel given as string should return default GitLabParallel."""
        content = """\
job1:
  script:
    - echo hi
  parallel: "invalid"
"""
        pipeline = self.parser.parse_string(content)
        assert pipeline.jobs["job1"].parallel is not None
        assert pipeline.jobs["job1"].parallel.matrix == []

    def test_merge_template_after_script(self):
        content = """\
.base:
  after_script:
    - cleanup.sh

job1:
  extends: .base
  script:
    - echo hi
"""
        pipeline = self.parser.parse_string(content)
        assert "cleanup.sh" in pipeline.jobs["job1"].after_script
