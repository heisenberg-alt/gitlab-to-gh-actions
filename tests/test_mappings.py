"""Tests for GitLab to GitHub Actions mapping rules."""

from gl2gh.mappings.rules import (
    convert_rules_to_if,
    convert_trigger_to_reusable_workflow,
    image_to_runner,
    normalize_service,
    parse_expire_in_days,
    parse_only_except,
    parse_timeout_minutes,
    stages_to_needs_graph,
    translate_cache_key,
    translate_variable,
    translate_variables_dict,
    when_to_if_condition,
)


class TestImageToRunner:
    def test_python_image(self):
        assert image_to_runner("python:3.11") == "ubuntu-latest"

    def test_node_image(self):
        assert image_to_runner("node:18") == "ubuntu-latest"

    def test_dotnet_image(self):
        assert image_to_runner("mcr.microsoft.com/dotnet/sdk:8.0") == "windows-latest"

    def test_none_image(self):
        assert image_to_runner(None) == "ubuntu-latest"

    def test_unknown_image(self):
        assert image_to_runner("my-custom-image:latest") == "ubuntu-latest"


class TestTranslateVariable:
    def test_commit_sha(self):
        result = translate_variable("$CI_COMMIT_SHA")
        assert result == "${{ github.sha }}"

    def test_registry_image(self):
        result = translate_variable("$CI_REGISTRY_IMAGE:latest")
        assert "ghcr.io" in result

    def test_project_path(self):
        result = translate_variable("$CI_PROJECT_PATH")
        assert result == "${{ github.repository }}"

    def test_no_translation_needed(self):
        result = translate_variable("echo hello")
        assert result == "echo hello"

    def test_multiple_variables(self):
        result = translate_variable("$CI_REGISTRY_IMAGE:$CI_COMMIT_SHA")
        assert "ghcr.io" in result
        assert "github.sha" in result


class TestParseTimeout:
    def test_hours_minutes(self):
        assert parse_timeout_minutes("1h 30m") == 90

    def test_hours_only(self):
        assert parse_timeout_minutes("2h") == 120

    def test_minutes_only(self):
        assert parse_timeout_minutes("45m") == 45

    def test_invalid(self):
        assert parse_timeout_minutes("") is None

    def test_plain_number(self):
        assert parse_timeout_minutes("60") == 60


class TestParseExpireIn:
    def test_days(self):
        assert parse_expire_in_days("30 days") == 30

    def test_weeks(self):
        assert parse_expire_in_days("1 week") == 7

    def test_hours(self):
        result = parse_expire_in_days("48 hours")
        assert result == 2

    def test_default(self):
        assert parse_expire_in_days("unknown") == 30


class TestTranslateCacheKey:
    def test_ref_slug(self):
        result = translate_cache_key("${CI_COMMIT_REF_SLUG}-cache")
        assert "${{ github.ref_name }}" in result

    def test_no_translation(self):
        result = translate_cache_key("my-static-key")
        assert result == "my-static-key"


class TestNormalizeService:
    def test_string_service(self):
        assert normalize_service("postgres:14") == {"image": "postgres:14"}

    def test_dict_service(self):
        svc = {"name": "redis", "alias": "cache"}
        result = normalize_service(svc)
        assert result["name"] == "redis"
        assert result["alias"] == "cache"


class TestTranslateVariablesDict:
    def test_translates_values(self):
        result = translate_variables_dict({"IMG": "$CI_REGISTRY_IMAGE"})
        assert "ghcr.io" in result["IMG"]

    def test_preserves_plain_values(self):
        result = translate_variables_dict({"FOO": "bar"})
        assert result["FOO"] == "bar"


class TestParseOnlyExcept:
    def test_only_branches(self):
        triggers, _ = parse_only_except(["branches"], None)
        assert "push" in triggers

    def test_only_tags(self):
        triggers, _ = parse_only_except(["tags"], None)
        assert "tags" in triggers.get("push", {})

    def test_only_merge_requests(self):
        triggers, _ = parse_only_except(["merge_requests"], None)
        assert "pull_request" in triggers

    def test_except_main(self):
        _, condition = parse_only_except(None, ["main"])
        assert condition is not None
        assert "refs/heads/main" in condition

    def test_defaults_when_empty(self):
        triggers, cond = parse_only_except(None, None)
        assert "push" in triggers
        assert "pull_request" in triggers
        assert cond is None


class TestConvertRulesToIf:
    def test_empty_rules(self):
        cond, warns = convert_rules_to_if([])
        assert cond is None
        assert warns == []

    def test_never_skipped(self):
        cond, _ = convert_rules_to_if([{"when": "never"}])
        assert cond is None

    def test_manual_warning(self):
        _, warns = convert_rules_to_if([{"when": "manual"}])
        assert any("manual" in w.lower() for w in warns)

    def test_if_clause_translated(self):
        rules = [{"if": '$CI_COMMIT_BRANCH == "main"'}]
        cond, _ = convert_rules_to_if(rules)
        assert cond is not None
        assert "github.ref_name" in cond
        assert "$CI_COMMIT_BRANCH" not in cond


class TestWhenToIfCondition:
    def test_on_success(self):
        assert when_to_if_condition("on_success") == "success()"

    def test_on_failure(self):
        assert when_to_if_condition("on_failure") == "failure()"

    def test_always(self):
        assert when_to_if_condition("always") == "always()"

    def test_manual(self):
        assert when_to_if_condition("manual") is None

    def test_unknown(self):
        assert when_to_if_condition("unknown_value") is None


class TestStagesToNeedsGraph:
    def test_linear_stages(self):
        from gl2gh.models import GitLabJob

        jobs = {
            "build_app": GitLabJob(name="build_app", stage="build"),
            "test_app": GitLabJob(name="test_app", stage="test"),
            "deploy_app": GitLabJob(name="deploy_app", stage="deploy"),
        }
        stages = ["build", "test", "deploy"]
        needs = stages_to_needs_graph(jobs, stages)
        assert needs["build_app"] == []
        assert needs["test_app"] == ["build_app"]
        assert needs["deploy_app"] == ["test_app"]

    def test_multiple_jobs_in_stage(self):
        from gl2gh.models import GitLabJob

        jobs = {
            "lint": GitLabJob(name="lint", stage="test"),
            "unit": GitLabJob(name="unit", stage="test"),
            "deploy": GitLabJob(name="deploy", stage="deploy"),
        }
        stages = ["test", "deploy"]
        needs = stages_to_needs_graph(jobs, stages)
        assert needs["lint"] == []
        assert needs["unit"] == []
        assert set(needs["deploy"]) == {"lint", "unit"}


class TestConvertTriggerToReusableWorkflow:
    def test_cross_project_trigger(self):
        trigger = {"project": "org/other-repo", "branch": "main"}
        caller, child_wf, warnings = convert_trigger_to_reusable_workflow(
            trigger, "deploy_child"
        )
        assert "uses" in caller
        assert "org/other-repo" in caller["uses"]
        assert "@main" in caller["uses"]
        assert child_wf is None  # No child workflow for cross-project
        assert len(warnings) > 0

    def test_cross_project_with_file(self):
        trigger = {
            "project": "org/infra",
            "file": ".github/workflows/deploy.yml",
            "branch": "release",
        }
        caller, child_wf, warnings = convert_trigger_to_reusable_workflow(
            trigger, "infra_deploy"
        )
        assert caller["uses"] == "org/infra/.github/workflows/deploy.yml@release"
        assert child_wf is None

    def test_cross_project_strategy_depend(self):
        trigger = {"project": "org/repo", "strategy": "depend"}
        _, _, warnings = convert_trigger_to_reusable_workflow(trigger, "child")
        assert any("strategy: depend" in w for w in warnings)

    def test_child_pipeline_include_string(self):
        trigger = {"include": "ci/child.yml"}
        caller, child_wf, warnings = convert_trigger_to_reusable_workflow(
            trigger, "trigger_child"
        )
        assert ".github/workflows/" in caller["uses"]
        assert child_wf is not None
        assert child_wf["on"] == {"workflow_call": {}}
        assert "jobs" in child_wf

    def test_child_pipeline_include_list(self):
        trigger = {"include": [{"local": "/templates/deploy.gitlab-ci.yml"}]}
        caller, child_wf, warnings = convert_trigger_to_reusable_workflow(
            trigger, "deploy"
        )
        assert child_wf is not None
        assert "workflow_call" in child_wf["on"]
        assert ".yml" in caller["uses"]

    def test_child_pipeline_include_dict(self):
        trigger = {"include": {"local": "ci/build.yml"}}
        caller, child_wf, warnings = convert_trigger_to_reusable_workflow(
            trigger, "build"
        )
        assert child_wf is not None
        assert "uses" in caller

    def test_child_pipeline_forward_variables(self):
        trigger = {
            "include": "child.yml",
            "forward": {"pipeline_variables": True},
        }
        _, _, warnings = convert_trigger_to_reusable_workflow(trigger, "fwd")
        assert any("forward" in w.lower() for w in warnings)

    def test_bare_trigger(self):
        trigger = {}
        caller, child_wf, warnings = convert_trigger_to_reusable_workflow(
            trigger, "my_trigger"
        )
        assert child_wf is not None
        assert "my_trigger.yml" in caller["uses"]
        assert child_wf["on"] == {"workflow_call": {}}
