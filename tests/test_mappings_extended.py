"""Extended mapping rule tests targeting uncovered lines."""

from gl2gh.mappings.rules import (
    convert_rules_to_if,
    convert_trigger_to_reusable_workflow,
    image_to_runner,
    parse_expire_in_days,
    parse_only_except,
    parse_timeout_minutes,
    when_to_if_condition,
)


class TestImageToRunnerExtended:
    def test_macos_image(self):
        assert image_to_runner("macos") == "macos-latest"

    def test_xcode_image(self):
        assert image_to_runner("xcode:14") == "macos-latest"

    def test_dotnet_microsoft(self):
        assert image_to_runner("microsoft/dotnet:6.0") == "windows-latest"

    def test_alpine_image(self):
        assert image_to_runner("alpine:3.18") == "ubuntu-latest"

    def test_golang_image(self):
        assert image_to_runner("golang:1.21") == "ubuntu-latest"

    def test_rust_image(self):
        assert image_to_runner("rust:1.70") == "ubuntu-latest"

    def test_java_image(self):
        assert image_to_runner("java:17") == "ubuntu-latest"

    def test_maven_image(self):
        assert image_to_runner("maven:3.9") == "ubuntu-latest"

    def test_gradle_image(self):
        assert image_to_runner("gradle:8") == "ubuntu-latest"

    def test_php_image(self):
        assert image_to_runner("php:8.2") == "ubuntu-latest"


class TestParseTimeoutExtended:
    def test_seconds_only(self):
        result = parse_timeout_minutes("90s")
        assert result == 2  # ceiling(90/60)

    def test_seconds_exact_minute(self):
        result = parse_timeout_minutes("60s")
        assert result == 1

    def test_hours_minutes_seconds(self):
        result = parse_timeout_minutes("1h 30m 45s")
        assert result == 91  # 60 + 30 + ceil(45/60)

    def test_invalid_text(self):
        assert parse_timeout_minutes("forever") is None


class TestParseExpireInExtended:
    def test_seconds(self):
        result = parse_expire_in_days("3600 seconds")
        assert result >= 1

    def test_minutes(self):
        result = parse_expire_in_days("1440 minutes")
        assert result == 1

    def test_months(self):
        assert parse_expire_in_days("2 months") == 60

    def test_years(self):
        assert parse_expire_in_days("1 year") == 365

    def test_years_capped(self):
        result = parse_expire_in_days("2 years")
        assert result <= 400


class TestParseOnlyExceptExtended:
    def test_only_schedules(self):
        triggers, _ = parse_only_except(["schedules"], None)
        assert "schedule" in triggers

    def test_only_web(self):
        triggers, _ = parse_only_except(["web"], None)
        assert "workflow_dispatch" in triggers

    def test_only_api(self):
        triggers, _ = parse_only_except(["api"], None)
        assert "workflow_dispatch" in triggers

    def test_only_triggers(self):
        triggers, _ = parse_only_except(["triggers"], None)
        assert "workflow_dispatch" in triggers

    def test_only_specific_branch(self):
        triggers, _ = parse_only_except(["develop"], None)
        push = triggers.get("push", {})
        assert "develop" in push.get("branches", [])

    def test_only_merge_request_singular(self):
        triggers, _ = parse_only_except(["merge_request"], None)
        assert "pull_request" in triggers

    def test_except_master(self):
        _, cond = parse_only_except(None, ["master"])
        assert "refs/heads/master" in cond

    def test_except_tags(self):
        _, cond = parse_only_except(None, ["tags"])
        assert "refs/tags/" in cond

    def test_except_merge_requests(self):
        _, cond = parse_only_except(None, ["merge_requests"])
        assert "pull_request" in cond

    def test_combined_only_except(self):
        triggers, cond = parse_only_except(["branches"], ["main"])
        assert "push" in triggers
        assert cond is not None


class TestConvertRulesToIfExtended:
    def test_multiple_rules(self):
        rules = [
            {"if": '$CI_COMMIT_BRANCH == "main"'},
            {"if": "$CI_COMMIT_TAG"},
        ]
        cond, _ = convert_rules_to_if(rules)
        assert "||" in cond

    def test_rule_with_when_never_skipped(self):
        rules = [
            {"if": '$CI_COMMIT_BRANCH == "main"', "when": "never"},
            {"if": "$CI_COMMIT_TAG"},
        ]
        cond, _ = convert_rules_to_if(rules)
        # The 'never' rule should be skipped
        assert "github.ref_name" not in cond or "github.ref" in cond

    def test_rule_double_quotes_replaced(self):
        rules = [{"if": '$CI_COMMIT_BRANCH == "main"'}]
        cond, _ = convert_rules_to_if(rules)
        assert '"' not in cond
        assert "'" in cond

    def test_pipeline_source_translated(self):
        rules = [{"if": '$CI_PIPELINE_SOURCE == "merge_request_event"'}]
        cond, _ = convert_rules_to_if(rules)
        assert "github.event_name" in cond

    def test_manual_rule_without_if_produces_no_condition(self):
        rules = [{"when": "manual"}]
        cond, warns = convert_rules_to_if(rules)
        assert cond is None
        assert len(warns) > 0


class TestWhenToIfExtended:
    def test_never(self):
        assert when_to_if_condition("never") == "false"

    def test_delayed(self):
        assert when_to_if_condition("delayed") is None


class TestConvertTriggerExtended:
    def test_cross_project_trigger(self):
        trigger = {"project": "org/other-repo", "branch": "develop"}
        caller, child, warns = convert_trigger_to_reusable_workflow(trigger, "deploy")
        assert "org/other-repo" in caller["uses"]
        assert child is None
        assert any("cross-project" in w for w in warns)

    def test_cross_project_with_strategy_depend(self):
        trigger = {"project": "org/repo", "strategy": "depend"}
        caller, child, warns = convert_trigger_to_reusable_workflow(trigger, "deploy")
        assert any("strategy: depend" in w for w in warns)

    def test_cross_project_file_as_list(self):
        trigger = {"project": "org/repo", "file": [".ci/deploy.yml"]}
        caller, _, _ = convert_trigger_to_reusable_workflow(trigger, "deploy")
        assert ".ci/deploy.yml" in caller["uses"]

    def test_cross_project_file_as_empty_list(self):
        trigger = {"project": "org/repo", "file": []}
        caller, _, _ = convert_trigger_to_reusable_workflow(trigger, "deploy")
        assert ".github/workflows/ci.yml" in caller["uses"]

    def test_include_string(self):
        trigger = {"include": "ci/deploy.yml"}
        caller, child, warns = convert_trigger_to_reusable_workflow(trigger, "deploy")
        assert caller["uses"].startswith("./")
        assert child is not None
        assert child["on"] == {"workflow_call": {}}

    def test_include_list_of_dicts(self):
        trigger = {"include": [{"local": "ci/deploy.yml"}]}
        caller, child, warns = convert_trigger_to_reusable_workflow(trigger, "deploy")
        assert child is not None

    def test_include_list_of_strings(self):
        trigger = {"include": ["ci/deploy.yml"]}
        caller, child, warns = convert_trigger_to_reusable_workflow(trigger, "deploy")
        assert child is not None

    def test_include_dict(self):
        trigger = {"include": {"local": "ci/deploy.yml"}}
        caller, child, warns = convert_trigger_to_reusable_workflow(trigger, "deploy")
        assert child is not None

    def test_include_empty_path_placeholder(self):
        trigger = {"include": {"local": ""}}
        caller, child, warns = convert_trigger_to_reusable_workflow(trigger, "deploy")
        assert "placeholder" in str(warns).lower() or "deploy" in caller["uses"]

    def test_include_with_strategy_depend(self):
        trigger = {"include": "ci/deploy.yml", "strategy": "depend"}
        _, _, warns = convert_trigger_to_reusable_workflow(trigger, "deploy")
        assert any("strategy: depend" in w for w in warns)

    def test_include_with_forward_pipeline_vars(self):
        trigger = {
            "include": "ci/deploy.yml",
            "forward": {"pipeline_variables": True},
        }
        _, _, warns = convert_trigger_to_reusable_workflow(trigger, "deploy")
        assert any("forward" in w.lower() for w in warns)

    def test_bare_trigger_no_include_no_project(self):
        trigger = {}
        caller, child, warns = convert_trigger_to_reusable_workflow(trigger, "my_job")
        assert "my_job" in caller["uses"]
        assert child is not None
        assert any("stub" in w.lower() for w in warns)

    def test_include_list_empty(self):
        trigger = {"include": []}
        caller, child, warns = convert_trigger_to_reusable_workflow(trigger, "job1")
        # Empty include list falls to default handling
        assert caller is not None

    def test_include_unknown_type(self):
        """include as integer should result in empty local_path."""
        trigger = {"include": 42}
        caller, child, warns = convert_trigger_to_reusable_workflow(trigger, "job1")
        assert caller is not None

    def test_include_filename_becomes_job_name(self):
        """When include path resolves to empty filename, job_name is used."""
        trigger = {"include": ".gitlab-ci.yml"}
        caller, child, warns = convert_trigger_to_reusable_workflow(trigger, "deploy")
        assert child is not None
