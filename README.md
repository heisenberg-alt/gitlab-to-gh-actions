# gl2gh -- GitLab CI/CD to GitHub Actions Migration Tool

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-1.0.0-green.svg)](pyproject.toml)

A production-grade migration tool that converts GitLab CI/CD pipelines (`.gitlab-ci.yml`) to GitHub Actions workflows. Combines deterministic rule-based conversion with optional AI-enhanced migration powered by Claude for handling complex patterns.

---

## Features

- **Rule-based conversion engine** -- Deterministic mapping of GitLab CI concepts to GitHub Actions equivalents, covering stages, jobs, variables, caching, artifacts, services, environments, matrix builds, and more.
- **AI-enhanced migration** -- Optional Claude-powered agent that handles complex patterns like templates (`extends`), advanced `rules:`, multi-project pipelines, and edge cases that pure rules cannot cover.
- **Full CLI interface** -- Five commands (`migrate`, `inspect`, `validate`, `migrate-repo`, `gh-status`) for every stage of the migration workflow.
- **Comprehensive variable translation** -- Automatically maps `$CI_COMMIT_SHA`, `$CI_REGISTRY_IMAGE`, and 30+ other GitLab CI predefined variables to their GitHub Actions equivalents.
- **Validation and optimization** -- Built-in validator checks generated workflows for structural correctness, security issues (script injection patterns), and best practices. Optimizer agent suggests caching, concurrency, and cost improvements.
- **gh CLI integration** -- Works with the GitHub CLI (`gh`) for repository creation, workflow listing, and end-to-end repository migration.
- **Template resolution** -- Handles YAML anchors (`&anchor`/`*anchor`), `extends`, and hidden job templates (`.dot` prefix) through ruamel.yaml.

---

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/gl2gh.git
cd gl2gh

# Install in development mode with all dev dependencies
pip install -e ".[dev]"

# Verify installation
gl2gh --version
```

### Requirements

- Python 3.11 or later
- (Optional) [GitHub CLI](https://cli.github.com/) (`gh`) for repository operations
- (Optional) `ANTHROPIC_API_KEY` for AI-enhanced migration

---

## Usage

### migrate -- Convert a Pipeline

Convert a `.gitlab-ci.yml` file to GitHub Actions:

```bash
# Basic conversion (rule-based)
gl2gh migrate .gitlab-ci.yml

# Specify output directory and workflow name
gl2gh migrate .gitlab-ci.yml -o .github/workflows -n "CI/CD Pipeline"

# Dry run -- print output without writing files
gl2gh migrate .gitlab-ci.yml --dry-run

# AI-enhanced conversion (requires ANTHROPIC_API_KEY)
gl2gh migrate .gitlab-ci.yml --ai

# Verbose output with conversion notes and unsupported feature details
gl2gh migrate .gitlab-ci.yml -v

# Output as JSON instead of YAML
gl2gh migrate .gitlab-ci.yml --dry-run --format json
```

### inspect -- Analyze a Pipeline

Examine a GitLab CI file without converting:

```bash
# Summary view (stages, variable count, job count, templates, default image)
gl2gh inspect .gitlab-ci.yml

# Detailed view with per-job breakdown (image, stage, when, needs)
gl2gh inspect .gitlab-ci.yml -v
```

### validate -- Check Generated Workflows

Validate generated GitHub Actions YAML files for correctness:

```bash
gl2gh validate .github/workflows
gl2gh validate .github/workflows -v
```

The validator checks YAML syntax, required top-level keys (`name`, `on`, `jobs`), job structure (`runs-on`, `steps`), step validity, and runner names.

### migrate-repo -- Full Repository Migration

Migrate an entire repository from GitLab to GitHub:

```bash
# Guided manual migration steps
gl2gh migrate-repo git@gitlab.com:org/repo.git org/repo

# AI-assisted full migration plan
gl2gh migrate-repo git@gitlab.com:org/repo.git org/repo --ai

# Specify branch
gl2gh migrate-repo git@gitlab.com:org/repo.git org/repo --branch develop
```

### gh-status -- Check GitHub CLI Availability

```bash
gl2gh gh-status
```

Reports whether `gh` CLI and the GitHub Copilot extension are installed.

---

## AI-Enhanced Mode

For complex pipelines with templates, advanced rules, matrix builds, or multi-project triggers, enable AI-enhanced migration:

```bash
# Set your Anthropic API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Run with AI enhancement
gl2gh migrate .gitlab-ci.yml --ai
```

The AI agent works as follows:

1. **Baseline** -- Runs the rule-based converter first to produce a baseline workflow.
2. **Analysis** -- Examines warnings, unsupported features, and complex patterns (rules, parallel, extends).
3. **Enhancement** -- Uses Claude with tool calling (`validate_yaml`, `save_workflow`, `add_warning`, `add_conversion_note`) in an agentic loop to iteratively improve the output.
4. **Validation** -- Validates the final YAML before saving.
5. **Fallback** -- If AI enhancement fails, falls back gracefully to the rule-based result with a warning.

The migration agent uses Claude Opus with adaptive thinking for deep reasoning about pipeline semantics. The validator and optimizer agents provide additional AI-powered review.

---

## Architecture

```
src/gl2gh/
  __init__.py              # Package entry point, version, public API
  cli.py                   # Click-based CLI with 5 commands, Rich output
  parser.py                # GitLab CI YAML parser -> GitLabPipeline model
  converter.py             # Rule-based GitLabPipeline -> GitHub Actions converter
  models.py                # Data models (GitLabJob, GitLabPipeline, ConversionResult)
  mappings/
    __init__.py
    rules.py               # Variable translation, trigger mapping, cache/artifact rules
  agents/
    __init__.py
    migration_agent.py     # Claude-powered migration with tool use (agentic loop)
    validator_agent.py     # Static + AI workflow validation
    optimizer_agent.py     # Workflow optimization analysis and scoring
  utils/
    __init__.py
    yaml_utils.py          # YAML parsing/serialization (ruamel.yaml for anchors)
```

### How It Works

1. **Parse** -- `GitLabCIParser` reads `.gitlab-ci.yml` using ruamel.yaml (preserving anchors and aliases) and builds a structured `GitLabPipeline` object with typed dataclass fields for every GitLab CI concept: jobs, stages, variables, cache, artifacts, services, environments, rules, parallel matrix, and more.

2. **Convert** -- `GitLabToGitHubConverter` walks the pipeline model and applies deterministic mapping rules: stages become job dependency graphs via `needs`, variables are translated through a 30+ entry lookup table, `only/except` and `rules` become `on:` triggers and `if:` conditions, services become container service definitions, cache becomes `actions/cache@v4` steps, and artifacts become `actions/upload-artifact@v4` steps.

3. **Enhance (optional)** -- `MigrationAgent` sends the rule-based output along with warnings and unsupported features to Claude. The agent uses tool calling to validate YAML, save improved workflows, and annotate manual review items. It runs for up to 8 iterations until Claude signals completion.

4. **Validate** -- `ValidatorAgent` checks the output for structural correctness (required keys, valid runners, step definitions) and security issues (script injection patterns in PR head ref, issue title, issue body, and comment body).

5. **Optimize** -- `OptimizerAgent` scores the workflow (0-100) and suggests improvements: adding caching, setting timeouts, enabling concurrency groups, and verifying parallelism is intentional.

---

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=gl2gh --cov-report=term-missing

# Run with HTML coverage report
pytest --cov=gl2gh --cov-report=html

# Run a specific test file
pytest tests/test_parser.py -v

# Run tests matching a pattern
pytest -k "test_convert" -v

# Run a specific test class
pytest tests/test_converter.py::TestConverterComplex -v
```

### Linting and Type Checking

```bash
# Format code with black
black src/ tests/

# Lint with ruff
ruff check src/ tests/

# Auto-fix lint issues
ruff check --fix src/ tests/

# Type check with mypy
mypy src/gl2gh/
```

### Project Configuration

All project configuration lives in `pyproject.toml`:

- **Build system**: Hatchling
- **Test runner**: pytest (with pytest-asyncio, pytest-cov, pytest-mock)
- **Linter**: ruff (rules: E, F, I, W; target: Python 3.11)
- **Formatter**: black
- **Type checker**: mypy (Python 3.11 target, strict return type warnings)

---

## Examples

The `examples/` directory contains sample GitLab CI files for testing:

- **`simple.gitlab-ci.yml`** -- A straightforward Node.js pipeline with install, test, build, and deploy stages. Demonstrates caching, artifacts, JUnit reports, environments, and `only` branch filters.
- **`complex.gitlab-ci.yml`** -- A multi-stage Python pipeline with Docker builds, matrix testing across Python versions, security scanning (SAST), multi-environment deployments, manual production gates, `extends` templates, and `rules` conditions.

Try them out:

```bash
gl2gh migrate examples/simple.gitlab-ci.yml --dry-run
gl2gh migrate examples/complex.gitlab-ci.yml --dry-run -v
gl2gh inspect examples/complex.gitlab-ci.yml -v
```

---

## Variable Translation Reference

30+ GitLab CI predefined variables are automatically translated:

| GitLab CI Variable | GitHub Actions Equivalent |
|---|---|
| `$CI_COMMIT_SHA` | `${{ github.sha }}` |
| `$CI_COMMIT_REF_NAME` | `${{ github.ref_name }}` |
| `$CI_COMMIT_BRANCH` | `${{ github.ref_name }}` |
| `$CI_COMMIT_TAG` | `${{ github.ref_name }}` |
| `$CI_PROJECT_PATH` | `${{ github.repository }}` |
| `$CI_PROJECT_NAME` | `${{ github.event.repository.name }}` |
| `$CI_PROJECT_NAMESPACE` | `${{ github.repository_owner }}` |
| `$CI_PIPELINE_ID` | `${{ github.run_id }}` |
| `$CI_JOB_ID` | `${{ github.job }}` |
| `$CI_REGISTRY` | `ghcr.io` |
| `$CI_REGISTRY_IMAGE` | `ghcr.io/${{ github.repository }}` |
| `$CI_REGISTRY_USER` | `${{ github.actor }}` |
| `$CI_REGISTRY_PASSWORD` | `${{ secrets.GITHUB_TOKEN }}` |
| `$CI_MERGE_REQUEST_IID` | `${{ github.event.pull_request.number }}` |
| `$CI_DEFAULT_BRANCH` | `${{ github.event.repository.default_branch }}` |
| `$CI_PROJECT_DIR` | `${{ github.workspace }}` |

See `src/gl2gh/mappings/rules.py` for the complete mapping table.

---

## Contributing

Contributions are welcome. Here is how to get started:

1. Fork the repository and create a feature branch.
2. Install in development mode: `pip install -e ".[dev]"`
3. Make your changes, ensuring all tests pass: `pytest`
4. Run linting: `ruff check src/ tests/` and `black --check src/ tests/`
5. Run type checking: `mypy src/gl2gh/`
6. Submit a pull request with a clear description of the change.

### Areas for Contribution

- **New mapping rules** -- Add support for additional GitLab CI features in `src/gl2gh/mappings/rules.py`.
- **Agent improvements** -- Enhance the AI agents with better prompts, additional tools, or new optimization checks.
- **Test coverage** -- Add test cases for edge cases and complex pipeline patterns in `tests/`.
- **Documentation** -- Improve the migration guide, add more examples, or document advanced use cases.
- **New CLI commands** -- Add commands for diff comparison, batch migration, or configuration profiles.

---

## Configuration

Create a `.env` file in your project root for optional configuration:

```bash
# Required only for --ai mode
ANTHROPIC_API_KEY=sk-ant-...

# GitHub CLI is auto-detected
```

---

## License

This project is licensed under the MIT License. See [pyproject.toml](pyproject.toml) for details.
