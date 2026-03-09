"""Extended CLI tests targeting uncovered branches."""

from pathlib import Path
from unittest import mock

from click.testing import CliRunner

from gl2gh.cli import (
    _check_gh_cli,
    _gh_create_repo,
    _gh_workflow_list,
    main,
    print_result,
)
from gl2gh.models import ConversionResult

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "gitlab"


class TestCLIExtended:
    def setup_method(self):
        self.runner = CliRunner()

    def test_migrate_verbose(self, tmp_path):
        result = self.runner.invoke(
            main,
            [
                "migrate",
                str(FIXTURES_DIR / "simple.yml"),
                "--verbose",
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0

    def test_migrate_json_format_dry_run(self, tmp_path):
        result = self.runner.invoke(
            main,
            [
                "migrate",
                str(FIXTURES_DIR / "simple.yml"),
                "--dry-run",
                "--format",
                "json",
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0

    def test_migrate_complex_file(self, tmp_path):
        result = self.runner.invoke(
            main,
            [
                "migrate",
                str(FIXTURES_DIR / "complex.yml"),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        yml_files = list(tmp_path.glob("*.yml"))
        assert len(yml_files) > 0

    def test_migrate_with_custom_name(self, tmp_path):
        result = self.runner.invoke(
            main,
            [
                "migrate",
                str(FIXTURES_DIR / "simple.yml"),
                "--name",
                "My Build",
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0

    def test_inspect_verbose(self):
        result = self.runner.invoke(
            main,
            [
                "inspect",
                str(FIXTURES_DIR / "complex.yml"),
                "--verbose",
            ],
        )
        assert result.exit_code == 0

    def test_inspect_docker_file(self):
        result = self.runner.invoke(
            main,
            [
                "inspect",
                str(FIXTURES_DIR / "docker.yml"),
            ],
        )
        assert result.exit_code == 0

    def test_inspect_invalid_file(self, tmp_path):
        bad_file = tmp_path / "bad.yml"
        bad_file.write_text("not: [valid: yaml: {{")
        result = self.runner.invoke(
            main,
            ["inspect", str(bad_file)],
        )
        assert result.exit_code != 0

    def test_validate_command(self, tmp_path):
        # Create a valid workflow file
        wf = tmp_path / "ci.yml"
        wf.write_text(
            "name: CI\non: push\njobs:\n  build:"
            "\n    runs-on: ubuntu-latest"
            "\n    steps:\n      - run: echo hi\n"
        )
        result = self.runner.invoke(
            main,
            ["validate", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_validate_invalid_file(self, tmp_path):
        bad = tmp_path / "bad.yml"
        bad.write_text("not: [valid: yaml: {{")
        result = self.runner.invoke(
            main,
            ["validate", str(tmp_path)],
        )
        assert result.exit_code != 0

    def test_validate_empty_dir(self, tmp_path):
        result = self.runner.invoke(
            main,
            ["validate", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "no yaml" in result.output.lower()

    def test_migrate_ai_no_token(self, tmp_path):
        with mock.patch.dict("os.environ", {}, clear=True):
            # Remove GITHUB_TOKEN if set
            env = {
                k: v for k, v in
                __import__("os").environ.items()
                if k != "GITHUB_TOKEN"
            }
            with mock.patch.dict("os.environ", env, clear=True):
                result = self.runner.invoke(
                    main,
                    [
                        "migrate",
                        str(FIXTURES_DIR / "simple.yml"),
                        "--ai",
                        "--output-dir",
                        str(tmp_path),
                    ],
                )
                assert result.exit_code != 0

    def test_migrate_repo_no_ai(self):
        """migrate-repo without --ai should print manual steps."""
        with mock.patch("gl2gh.cli._check_gh_cli", return_value=False):
            result = self.runner.invoke(
                main,
                [
                    "migrate-repo",
                    "gitlab.com/org/repo",
                    "github.com/org/repo",
                ],
            )
            assert result.exit_code == 0
            out = result.output.lower()
            assert "manual migration" in out or "git clone" in out

    def test_migrate_repo_no_ai_with_gh(self):
        """migrate-repo with gh CLI available should suggest gh repo create."""
        with mock.patch("gl2gh.cli._check_gh_cli", return_value=True):
            result = self.runner.invoke(
                main,
                [
                    "migrate-repo",
                    "gitlab.com/org/repo",
                    "github.com/org/repo",
                ],
            )
            assert result.exit_code == 0
            assert "gh repo create" in result.output

    def test_migrate_repo_ai_no_token(self):
        env = {k: v for k, v in __import__("os").environ.items() if k != "GITHUB_TOKEN"}
        with mock.patch.dict("os.environ", env, clear=True):
            result = self.runner.invoke(
                main,
                [
                    "migrate-repo",
                    "gitlab.com/org/repo",
                    "github.com/org/repo",
                    "--ai",
                ],
            )
            assert result.exit_code != 0

    def test_gh_status_no_gh(self):
        with mock.patch("gl2gh.cli._check_gh_cli", return_value=False):
            result = self.runner.invoke(main, ["gh-status"])
            assert result.exit_code == 0
            assert "not installed" in result.output.lower()

    def test_gh_status_with_gh(self):
        with mock.patch("gl2gh.cli._check_gh_cli", return_value=True):
            with mock.patch(
                "gl2gh.cli._gh_workflow_list",
                return_value=["CI", "Deploy"],
            ):
                with mock.patch("subprocess.run") as mock_run:
                    mock_run.return_value = mock.Mock(
                        stdout="gh-copilot\n", stderr="", returncode=0
                    )
                    result = self.runner.invoke(main, ["gh-status"])
                    assert result.exit_code == 0
                    assert "installed" in result.output.lower()

    def test_gh_status_with_gh_no_copilot(self):
        with mock.patch("gl2gh.cli._check_gh_cli", return_value=True):
            with mock.patch("gl2gh.cli._gh_workflow_list", return_value=[]):
                with mock.patch("subprocess.run") as mock_run:
                    mock_run.return_value = mock.Mock(
                        stdout="some-extension\n", stderr="", returncode=0
                    )
                    result = self.runner.invoke(main, ["gh-status"])
                    assert result.exit_code == 0


class TestPrintResult:
    """Test print_result with different ConversionResult states."""

    def test_print_failed_result(self, capsys):
        result = ConversionResult(source_file="test.yml")
        result.errors.append("Something went wrong")
        print_result(result)
        # Just check it doesn't crash — output goes to Rich console

    def test_print_success_with_all_fields(self, capsys):
        result = ConversionResult(source_file="test.yml")
        result.output_workflows = {"ci.yml": "name: CI"}
        result.warnings.append("Some warning")
        result.validation_issues.append("[WARNING] check this")
        result.conversion_notes.append("A note")
        result.unsupported_features.append("some.feature")
        result.ai_enhanced = True
        print_result(result, verbose=True)

    def test_print_success_non_verbose(self, capsys):
        result = ConversionResult(source_file="test.yml")
        result.output_workflows = {"ci.yml": "name: CI"}
        print_result(result, verbose=False)


class TestGhHelpers:
    """Test gh CLI helper functions."""

    def test_check_gh_cli_not_found(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError):
            assert _check_gh_cli() is False

    def test_check_gh_cli_found(self):
        with mock.patch("subprocess.run"):
            assert _check_gh_cli() is True

    def test_gh_create_repo_success(self):
        with mock.patch("subprocess.run"):
            assert _gh_create_repo("my-org/my-repo") is True

    def test_gh_create_repo_private(self):
        with mock.patch("subprocess.run") as mock_run:
            _gh_create_repo("my-org/my-repo", private=True)
            call_args = mock_run.call_args[0][0]
            assert "--private" in call_args

    def test_gh_create_repo_failure(self):
        import subprocess as _sp

        with mock.patch(
            "subprocess.run",
            side_effect=_sp.CalledProcessError(
                1, "gh", stderr="fail"
            ),
        ):
            assert _gh_create_repo("my-org/my-repo") is False

    def test_gh_workflow_list_success(self):
        mock_result = mock.Mock(stdout='[{"name": "CI", "state": "active"}]')
        with mock.patch("subprocess.run", return_value=mock_result):
            result = _gh_workflow_list()
            assert result == ["CI"]

    def test_gh_workflow_list_failure(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError):
            assert _gh_workflow_list() == []
