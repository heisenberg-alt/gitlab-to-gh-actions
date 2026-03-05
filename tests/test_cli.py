"""Tests for the CLI interface."""

from pathlib import Path

from click.testing import CliRunner

from gl2gh.cli import main

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "gitlab"


class TestCLI:
    def setup_method(self):
        self.runner = CliRunner()

    def test_version(self):
        result = self.runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "1.0.0" in result.output

    def test_help(self):
        result = self.runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "migrate" in result.output

    def test_migrate_dry_run(self, tmp_path):
        result = self.runner.invoke(
            main,
            [
                "migrate",
                str(FIXTURES_DIR / "simple.yml"),
                "--dry-run",
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0

    def test_migrate_writes_file(self, tmp_path):
        result = self.runner.invoke(
            main,
            [
                "migrate",
                str(FIXTURES_DIR / "simple.yml"),
                "--output-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        yml_files = list(tmp_path.glob("*.yml"))
        assert len(yml_files) > 0

    def test_inspect(self):
        result = self.runner.invoke(
            main,
            [
                "inspect",
                str(FIXTURES_DIR / "simple.yml"),
            ],
        )
        assert result.exit_code == 0

    def test_migrate_invalid_file(self, tmp_path):
        bad_file = tmp_path / "bad.yml"
        bad_file.write_text("not: [valid: yaml: {{")
        result = self.runner.invoke(
            main,
            [
                "migrate",
                str(bad_file),
                "--output-dir",
                str(tmp_path / "out"),
            ],
        )
        # Should handle gracefully
        assert (
            result.exit_code != 0
            or "Error" in result.output
            or "error" in result.output.lower()
        )
