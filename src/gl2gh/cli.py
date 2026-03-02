"""Command-line interface for gl2gh — integrates with gh CLI for GitHub operations."""

from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn
from dotenv import load_dotenv

from gl2gh.parser import GitLabCIParser
from gl2gh.converter import GitLabToGitHubConverter
from gl2gh.models import ConversionResult
from gl2gh.utils.yaml_utils import validate_yaml_syntax

console = Console()
load_dotenv()


def print_banner() -> None:
    console.print(Panel.fit(
        "[bold blue]gl2gh[/bold blue] — GitLab CI/CD -> GitHub Actions Migration Tool\n"
        "[dim]Powered by Claude AI | Uses gh CLI for GitHub ops[/dim]",
        border_style="blue",
    ))


def print_result(result: ConversionResult, verbose: bool = False) -> None:
    if result.success:
        console.print("\n[bold green]Conversion successful![/bold green]")
        console.print(f"  Generated {len(result.output_workflows)} workflow file(s):")
        for filename in result.output_workflows:
            console.print(f"    [cyan].github/workflows/{filename}[/cyan]")
        if result.ai_enhanced:
            console.print("  [yellow]AI-enhanced conversion applied[/yellow]")
    else:
        console.print("\n[bold red]Conversion failed[/bold red]")
    if result.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for err in result.errors:
            console.print(f"  [red]- {err}[/red]")
    if result.warnings:
        console.print("\n[bold yellow]Warnings:[/bold yellow]")
        for warn in result.warnings:
            console.print(f"  [yellow]- {warn}[/yellow]")
    if verbose and result.unsupported_features:
        console.print("\n[bold orange1]Unsupported features:[/bold orange1]")
        for feat in result.unsupported_features:
            console.print(f"  [orange1]- {feat}[/orange1]")
    if verbose and result.conversion_notes:
        console.print("\n[bold blue]Notes:[/bold blue]")
        for note in result.conversion_notes:
            console.print(f"  [blue]- {note}[/blue]")


def _check_gh_cli() -> bool:
    """Check if gh CLI is installed."""
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _gh_create_repo(name: str, private: bool = False) -> bool:
    """Create a GitHub repo using gh CLI."""
    cmd = ["gh", "repo", "create", name, "--confirm"]
    if private:
        cmd.append("--private")
    else:
        cmd.append("--public")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[red]gh repo create failed: {e.stderr}[/red]")
        return False


def _gh_workflow_list() -> list[str]:
    """List workflows using gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "workflow", "list", "--json", "name,state"],
            capture_output=True, text=True, check=True,
        )
        workflows = json.loads(result.stdout)
        return [w["name"] for w in workflows]
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return []


@click.group()
@click.version_option(version="1.0.0", prog_name="gl2gh")
def main() -> None:
    """gl2gh - Migrate GitLab CI/CD pipelines to GitHub Actions."""
    pass


@main.command()
@click.argument("input_file", default=".gitlab-ci.yml", type=click.Path(exists=True))
@click.option("-o", "--output-dir", default=".github/workflows", help="Output directory.")
@click.option("-n", "--name", default="CI", help="Workflow name.")
@click.option("--ai", is_flag=True, default=False, help="Use Claude AI for enhanced conversion.")
@click.option("--dry-run", is_flag=True, help="Print output without writing files.")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed conversion info.")
@click.option("--format", "output_format", type=click.Choice(["yaml", "json"]), default="yaml")
def migrate(input_file, output_dir, name, ai, dry_run, verbose, output_format):
    """Migrate a GitLab CI pipeline to GitHub Actions."""
    print_banner()
    console.print(f"\n[dim]Reading:[/dim] [cyan]{input_file}[/cyan]")

    parser = GitLabCIParser()
    try:
        pipeline = parser.parse_file(input_file)
    except Exception as exc:
        console.print(f"[bold red]Failed to parse {input_file}: {exc}[/bold red]")
        sys.exit(1)

    console.print(f"[dim]Found {len(pipeline.jobs)} jobs across {len(pipeline.stages)} stages[/dim]")

    if ai:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            console.print("[bold red]ANTHROPIC_API_KEY not set. Cannot use --ai mode.[/bold red]")
            sys.exit(1)
        from gl2gh.agents.migration_agent import MigrationAgent
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
            task = progress.add_task("Running AI-enhanced migration...", total=None)
            agent = MigrationAgent(api_key=api_key)
            result = agent.migrate(pipeline, source_file=input_file, workflow_name=name)
            progress.remove_task(task)
    else:
        converter = GitLabToGitHubConverter(workflow_name=name, source_file=input_file)
        result = converter.convert(pipeline)

    print_result(result, verbose=verbose)

    if not result.success:
        sys.exit(1)

    if dry_run:
        console.print("\n[bold yellow]Dry run - not writing files.[/bold yellow]")
        for filename, content in result.output_workflows.items():
            console.print(f"\n[bold cyan]--- {filename} ---[/bold cyan]")
            if output_format == "json":
                import yaml as _yaml
                data = _yaml.safe_load(content)
                console.print_json(json.dumps(data, indent=2))
            else:
                console.print(Syntax(content, "yaml", theme="monokai"))
        return

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    for filename, content in result.output_workflows.items():
        (out_path / filename).write_text(content, encoding="utf-8")
        console.print(f"[green]Written:[/green] {out_path / filename}")

    console.print(f"\n[bold green]Done![/bold green] Next steps:")
    console.print(f"  gl2gh validate {output_dir}")
    if _check_gh_cli():
        console.print("  gh workflow run ci.yml  # test the workflow")


@main.command()
@click.argument("input_file", default=".gitlab-ci.yml", type=click.Path(exists=True))
@click.option("-v", "--verbose", is_flag=True)
def inspect(input_file, verbose):
    """Inspect a GitLab CI pipeline without converting it."""
    print_banner()
    parser = GitLabCIParser()
    try:
        pipeline = parser.parse_file(input_file)
    except Exception as exc:
        console.print(f"[bold red]Failed to parse: {exc}[/bold red]")
        sys.exit(1)
    table = Table(title=f"Pipeline: {input_file}", show_header=True, header_style="bold blue")
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    table.add_row("Stages", ", ".join(pipeline.stages))
    table.add_row("Global Variables", str(len(pipeline.variables)))
    table.add_row("Jobs", str(len([j for j in pipeline.jobs.values() if not j.is_template])))
    table.add_row("Templates", str(len([j for j in pipeline.jobs.values() if j.is_template])))
    table.add_row("Default Image", pipeline.default_image or "[dim]none[/dim]")
    table.add_row("Includes", str(len(pipeline.includes)))
    console.print(table)
    if verbose:
        jt = Table(title="Jobs", show_header=True, header_style="bold green")
        jt.add_column("Job Name", style="cyan"); jt.add_column("Stage")
        jt.add_column("Image"); jt.add_column("When"); jt.add_column("Needs")
        for n, job in pipeline.jobs.items():
            if not job.is_template:
                jt.add_row(n, job.stage, job.image or "[dim]default[/dim]",
                           job.when, ", ".join(job.needs) or "-")
        console.print(jt)


@main.command()
@click.argument("workflow_dir", default=".github/workflows", type=click.Path(exists=True))
@click.option("-v", "--verbose", is_flag=True)
def validate(workflow_dir, verbose):
    """Validate generated GitHub Actions YAML files."""
    print_banner()
    wpath = Path(workflow_dir)
    files = list(wpath.glob("*.yml")) + list(wpath.glob("*.yaml"))
    if not files:
        console.print(f"[yellow]No YAML files in {workflow_dir}[/yellow]")
        return
    all_valid = True
    for f in files:
        content = f.read_text(encoding="utf-8")
        err = validate_yaml_syntax(content)
        if err:
            console.print(f"[red]x[/red] {f.name}: {err}")
            all_valid = False
        else:
            console.print(f"[green]v[/green] {f.name}: valid")
    if all_valid:
        console.print("\n[bold green]All workflow files valid![/bold green]")
    else:
        console.print("\n[bold red]Some files have errors.[/bold red]")
        sys.exit(1)


@main.command("migrate-repo")
@click.argument("source_gitlab_repo")
@click.argument("target_github_repo")
@click.option("--branch", default="main")
@click.option("--ai", is_flag=True)
@click.option("-v", "--verbose", is_flag=True)
def migrate_repo(source_gitlab_repo, target_github_repo, branch, ai, verbose):
    """Full repository migration from GitLab to GitHub.

    Uses gh CLI for GitHub operations when available."""
    print_banner()
    console.print(f"\n[bold]Repository Migration[/bold]")
    console.print(f"  From: [cyan]{source_gitlab_repo}[/cyan]")
    console.print(f"  To:   [cyan]{target_github_repo}[/cyan]")

    has_gh = _check_gh_cli()
    if not has_gh:
        console.print("[yellow]Install gh CLI for full automation: brew install gh[/yellow]")

    if ai:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            console.print("[bold red]ANTHROPIC_API_KEY not set.[/bold red]")
            sys.exit(1)
        from gl2gh.agents.migration_agent import MigrationAgent
        agent = MigrationAgent(api_key=api_key)
        success = agent.migrate_repository(source_gitlab_repo, target_github_repo, branch)
        if success:
            console.print("[bold green]Migration plan generated![/bold green]")
        else:
            console.print("[bold red]Migration failed.[/bold red]")
            sys.exit(1)
    else:
        console.print("\n[bold]Manual migration steps:[/bold]")
        console.print("  1. git clone " + source_gitlab_repo)
        console.print("  2. gl2gh migrate .gitlab-ci.yml --output-dir .github/workflows")
        if has_gh:
            console.print(f"  3. gh repo create {target_github_repo} --source . --push")
        else:
            console.print(f"  3. git remote set-url origin {target_github_repo}")
            console.print("  4. git push -u origin " + branch)


@main.command("gh-status")
def gh_status():
    """Check gh CLI and GitHub Copilot CLI availability."""
    print_banner()
    if _check_gh_cli():
        console.print("[green]gh CLI:[/green] installed")
        workflows = _gh_workflow_list()
        if workflows:
            console.print(f"  Active workflows: {', '.join(workflows)}")
        # Check for copilot extension
        try:
            r = subprocess.run(["gh", "extension", "list"], capture_output=True, text=True)
            if "copilot" in r.stdout.lower():
                console.print("[green]gh copilot:[/green] installed")
            else:
                console.print("[yellow]gh copilot:[/yellow] not installed")
                console.print("  Install: gh extension install github/gh-copilot")
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
    else:
        console.print("[red]gh CLI:[/red] not installed")
        console.print("  Install: brew install gh")


if __name__ == "__main__":
    main()
