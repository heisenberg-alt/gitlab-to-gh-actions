# gl2gh

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-green.svg)](pyproject.toml)

Convert GitLab CI/CD pipelines to GitHub Actions workflows. Rule-based conversion handles the common cases; optional AI-enhanced migration (GitHub Copilot) handles the rest.

## Install

```bash
uv sync --all-extras
gl2gh --version
```

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). Optional: [GitHub CLI](https://cli.github.com/) (`gh`) for repo operations, `GITHUB_TOKEN` for AI mode.

## Usage

```bash
# Convert a pipeline
gl2gh migrate .gitlab-ci.yml

# Preview without writing files
gl2gh migrate .gitlab-ci.yml --dry-run

# AI-enhanced conversion
export GITHUB_TOKEN="ghp_..."
gl2gh migrate .gitlab-ci.yml --ai

# Inspect a pipeline
gl2gh inspect .gitlab-ci.yml -v

# Validate generated workflows
gl2gh validate .github/workflows

# Full repo migration
gl2gh migrate-repo git@gitlab.com:org/repo.git org/repo --ai

# Check gh CLI status
gl2gh gh-status
```

### Key Options

| Flag | Description |
|---|---|
| `-o, --output-dir` | Output directory (default: `.github/workflows`) |
| `-n, --name` | Workflow name (default: `CI`) |
| `--ai` | Enable GitHub Copilot AI enhancement |
| `--model` | AI model override (default: `gpt-4.1`) |
| `--dry-run` | Print output without writing files |
| `--format json` | Output as JSON instead of YAML |
| `-v, --verbose` | Show conversion notes and unsupported features |

## How It Works

1. **Parse** -- Reads `.gitlab-ci.yml` via ruamel.yaml (preserving anchors/aliases), resolves `extends` templates, and builds a typed `GitLabPipeline` model.

2. **Convert** -- Maps GitLab concepts to GitHub Actions: stages become `needs` dependency graphs, variables are translated (30+ mappings), `only/except` and `rules` become `on:` triggers and `if:` conditions, cache becomes `actions/cache@v4`, artifacts become `actions/upload-artifact@v4`.

3. **Enhance** (optional) -- Sends the baseline output to GitHub Copilot with tool calling. The agent validates YAML, fixes issues, and iterates up to 8 times. Falls back to rule-based output on failure.

4. **Validate** -- Checks structure (required keys, valid runners, step definitions) and security (script injection patterns).

5. **Optimize** -- Scores the workflow (0-100) and suggests improvements: caching, timeouts, concurrency groups.

## Variable Translation

| GitLab CI | GitHub Actions |
|---|---|
| `$CI_COMMIT_SHA` | `${{ github.sha }}` |
| `$CI_COMMIT_REF_NAME` | `${{ github.ref_name }}` |
| `$CI_PROJECT_PATH` | `${{ github.repository }}` |
| `$CI_PIPELINE_ID` | `${{ github.run_id }}` |
| `$CI_REGISTRY` | `ghcr.io` |
| `$CI_REGISTRY_IMAGE` | `ghcr.io/${{ github.repository }}` |
| `$CI_REGISTRY_USER` | `${{ github.actor }}` |
| `$CI_REGISTRY_PASSWORD` | `${{ secrets.GITHUB_TOKEN }}` |
| `$CI_MERGE_REQUEST_IID` | `${{ github.event.pull_request.number }}` |
| `$CI_DEFAULT_BRANCH` | `${{ github.event.repository.default_branch }}` |
| `$CI_PROJECT_DIR` | `${{ github.workspace }}` |

Full table: [`src/gl2gh/mappings/rules.py`](src/gl2gh/mappings/rules.py)

## Project Structure

```
src/gl2gh/
  cli.py               # Click CLI with Rich output (5 commands)
  parser.py             # GitLab CI YAML parser
  converter.py          # Rule-based converter
  models.py             # Dataclasses: GitLabJob, GitLabPipeline, ConversionResult
  mappings/rules.py     # Variable translation, trigger mapping, pure functions
  agents/
    migration_agent.py  # Copilot-powered migration with tool use
    validator_agent.py  # Static + AI workflow validation
    optimizer_agent.py  # Workflow scoring and optimization
  utils/yaml_utils.py   # YAML load/dump helpers (ruamel.yaml)
```

## Development

```bash
# Tests (94 tests)
pytest
pytest --cov=gl2gh --cov-report=term-missing

# Lint and format
ruff check src/ tests/
ruff format src/ tests/

# Type check
mypy src/gl2gh/
```

## Examples

```bash
gl2gh migrate examples/simple.gitlab-ci.yml --dry-run
gl2gh migrate examples/complex.gitlab-ci.yml --dry-run -v
gl2gh inspect examples/complex.gitlab-ci.yml -v
```

- `simple.gitlab-ci.yml` -- Node.js pipeline: install, test, build, deploy with caching and artifacts.
- `complex.gitlab-ci.yml` -- Python pipeline: Docker, matrix testing, SAST, environments, extends, rules.

## Contributing

1. Fork and create a feature branch
2. `uv sync --all-extras`
3. Make changes, run `pytest`, `ruff check src/ tests/`, `mypy src/gl2gh/`
4. Submit a PR

## License

MIT
