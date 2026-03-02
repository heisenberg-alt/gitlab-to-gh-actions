"""Tests for GitLab to GitHub Actions mapping rules."""

from gl2gh.mappings.rules import (
    image_to_runner,
    translate_variable,
    parse_timeout_minutes,
    parse_expire_in_days,
    translate_cache_key,
    stages_to_needs_graph,
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
