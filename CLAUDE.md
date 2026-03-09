# CLAUDE.md -- Development Guide for gl2gh

This file provides context and guidelines for working on the gl2gh codebase with Claude Code.

## Project Overview

**gl2gh** converts GitLab CI/CD pipelines (`.gitlab-ci.yml`) into GitHub Actions workflows (`.github/workflows/*.yml`). It is a Python 3.11+ CLI tool and library that uses a hybrid approach: deterministic rule-based translation for common CI constructs, and AI-powered agents (GitHub Copilot) for complex patterns that lack direct one-to-one mappings.

## Directory Structure

```
gitlab-to-gh-actions/
  src/
    gl2gh/
      __init__.py              # Package init, version ("1.0.0"), public API exports
      cli.py                   # Click CLI with Rich output (5 commands: migrate, inspect, validate, migrate-repo, gh-status)
      converter.py             # Rule-based GitLab -> GitHub Actions converter (GitLabToGitHubConverter)
      parser.py                # GitLab CI YAML parser using ruamel.yaml (GitLabCIParser)
      models.py                # Dataclasses: GitLabJob, GitLabPipeline, ConversionResult, GitLabCache, etc.
      mappings/
        __init__.py
        rules.py               # 30+ variable translation entries, trigger mapping, cache/artifact rules, all pure functions
      utils/
        __init__.py
        yaml_utils.py          # YAML load/dump/validate helpers (ruamel.yaml for anchors, PyYAML for validation)
      agents/
        __init__.py
        migration_agent.py     # GitHub Copilot-powered migration agent with tool use loop (up to 8 iterations)
        validator_agent.py     # Static validation + optional AI review of generated workflows
        optimizer_agent.py     # Workflow scoring (0-100) and optimization suggestions
  tests/
    conftest.py                # Shared fixtures: simple_gitlab_content, docker_gitlab_content, minimal_pipeline_yaml, temp_output_dir
    fixtures/
      gitlab/                  # Sample .gitlab-ci.yml files for testing (simple.yml, docker.yml)
    test_parser.py             # Parser tests
    test_converter.py          # Converter tests
    test_mappings.py           # Mapping rule tests
    test_cli.py                # CLI integration tests
  examples/
    simple.gitlab-ci.yml       # Simple Node.js pipeline (install, test, build, deploy)
    complex.gitlab-ci.yml      # Complex Python pipeline (Docker, matrix, SAST, environments, extends)
  docs/
    MIGRATION_GUIDE.md         # Step-by-step migration walkthrough with before/after examples
  website/
    index.html                 # Landing page
  pyproject.toml               # Project metadata, dependencies, tool config
  CLAUDE.md                    # This file
  README.md                    # Project README
```

## How to Run Tests

```bash
# Install in development mode (first time)
uv sync --all-extras

# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/test_parser.py -v

# Run tests matching a name pattern
pytest -k "test_cache" -v

# Run with coverage
pytest --cov=gl2gh --cov-report=term-missing

# Run with HTML coverage report
pytest --cov=gl2gh --cov-report=html
```

## How to Lint and Type Check

```bash
# Lint
ruff check src/ tests/

# Auto-fix lint issues
ruff check --fix src/ tests/

# Check formatting
ruff format --check src/ tests/

# Format code
ruff format src/ tests/

# Also supported: black
black src/ tests/

# Type check
mypy src/gl2gh/
```

## Key Design Decisions

1. **Hybrid conversion approach.** Rule-based handles the ~80% common case (variables, cache, artifacts, services, stages). AI agents handle the remaining complex cases (multi-project pipelines, advanced `rules:` conditions, custom runner configurations). The AI path is opt-in via `--ai` flag.

2. **Dataclass models as intermediate representation.** `GitLabJob`, `GitLabPipeline`, `ConversionResult` and related classes in `models.py` are plain Python dataclasses (not Pydantic). They provide typed, structured intermediate representations between parsing and conversion.

3. **ruamel.yaml for parsing, PyYAML for validation.** GitLab CI heavily uses YAML anchors (`&anchor`) and aliases (`*anchor`) for template reuse. `ruamel.yaml` preserves these structures, which is critical for resolving `extends` correctly. PyYAML (`yaml.safe_load`) is used for simpler validation tasks.

4. **Pure mapping functions.** All functions in `mappings/rules.py` are pure (no side effects, no I/O). They take GitLab CI values and return GitHub Actions equivalents. This makes them independently testable and easy to extend.

5. **Multi-agent tool-use loop.** The AI migration agent (`migration_agent.py`) uses GitHub Copilot with tool definitions (`validate_yaml`, `save_workflow`, `add_warning`, `add_conversion_note`). It enters an agentic loop: GitHub Copilot emits tool calls, the agent executes them, feeds results back, repeating for up to 8 iterations until `stop_reason == "end_turn"`.

6. **Click + Rich CLI.** Click provides command structure, parameter validation, and shell completion. Rich adds tables, syntax highlighting, progress spinners, and panels.

7. **Local-first output.** Workflows are written to disk for user review, not pushed directly to GitHub. The `gh` CLI integration is optional convenience.

8. **Stage-to-needs graph conversion.** The `stages_to_needs_graph` function in `rules.py` converts GitLab's sequential stage model into an explicit dependency graph. Jobs in stage N depend on all jobs in stage N-1.

9. **Template resolution in the parser.** The `_resolve_extends` method in `parser.py` resolves `extends` by merging template properties into jobs. This is done at parse time so the converter only sees fully resolved jobs.

10. **Graceful AI fallback.** If AI enhancement fails for any reason, the system falls back to the rule-based result with a warning appended. The user always gets output.

## Adding New Mapping Rules

To add support for a new GitLab CI feature:

1. **Identify the GitLab CI feature** and its GitHub Actions equivalent. Check the [GitHub Actions documentation](https://docs.github.com/en/actions).

2. **Add model fields if needed** in `src/gl2gh/models.py`. For example, if adding support for `coverage` keyword, add a field to `GitLabJob`.

3. **Update the parser** in `src/gl2gh/parser.py`. Add extraction logic in `_parse_job()` to populate the new model field from raw YAML data.

4. **Add mapping rules** in `src/gl2gh/mappings/rules.py`. Write pure functions that translate the GitLab concept to GitHub Actions. For variable translations, add entries to the `GITLAB_TO_GHA_VARS` dictionary.

5. **Update the converter** in `src/gl2gh/converter.py`. Add conversion logic in the appropriate method (`_convert_job`, `_build_steps`, etc.) that uses the new mapping rules.

6. **Add tests.** Add test cases in:
   - `tests/test_mappings.py` -- Unit tests for the pure mapping functions.
   - `tests/test_parser.py` -- Tests for parsing the new feature from YAML.
   - `tests/test_converter.py` -- Tests for the full conversion output.

7. **Update documentation.** Add the new mapping to the concept mapping table in `docs/MIGRATION_GUIDE.md` and the variable translation table in `README.md` if applicable.

### Example: Adding a New Variable Translation

```python
# In src/gl2gh/mappings/rules.py, add to GITLAB_TO_GHA_VARS:
GITLAB_TO_GHA_VARS["$CI_ENVIRONMENT_NAME"] = "${{ github.event.deployment.environment }}"
GITLAB_TO_GHA_VARS["${CI_ENVIRONMENT_NAME}"] = "${{ github.event.deployment.environment }}"
```

### Example: Adding a New Converter Feature

```python
# In src/gl2gh/converter.py, add logic in _convert_job:
if job.resource_group:
    gha_job["concurrency"] = {
        "group": translate_variable(job.resource_group),
        "cancel-in-progress": job.interruptible,
    }
```

## Adding New Agent Capabilities

The AI agents in `src/gl2gh/agents/` use GitHub Copilot with tool calling. To add a new tool:

1. **Define the tool schema** in `_get_tools()` in the relevant agent. Each tool has a name, description, and JSON Schema for inputs:

   ```python
   {
       "name": "my_new_tool",
       "description": "Description of what the tool does",
       "input_schema": {
           "type": "object",
           "properties": {
               "param1": {"type": "string", "description": "..."},
               "param2": {"type": "integer", "description": "..."},
           },
           "required": ["param1"],
       },
   }
   ```

2. **Implement the tool handler** in `_execute_tool()`:

   ```python
   elif name == "my_new_tool":
       param1 = inp.get("param1", "")
       param2 = inp.get("param2", 0)
       # Do something useful
       return json.dumps({"success": True, "result": "..."})
   ```

3. **Update the system prompt** if the new tool changes the agent's capabilities. The system prompt in `MigrationAgent.SYSTEM_PROMPT` tells GitHub Copilot what tools are available and how to use them.

4. **Test the tool** by mocking the Copilot client in tests. Use `pytest-mock` to mock `CopilotClient` and simulate tool use responses.

### Agent Architecture

```
User calls agent.migrate(pipeline) or agent.migrate_repository(source, target)
  |
  v
Rule-based converter produces baseline result
  |
  v
Agent checks if AI enhancement is needed (warnings, unsupported features, complex patterns)
  |
  v
Agent sends pipeline summary + baseline to GitHub Copilot with tool definitions
  |
  v
Agentic loop (up to 8 iterations):
  GitHub Copilot response -> extract tool_use blocks -> execute tools -> feed results back
  Loop exits when stop_reason == "end_turn"
  |
  v
Return enhanced ConversionResult (or fall back to baseline on failure)
```

## Environment Variables

| Variable | Purpose | Required |
|---|---|---|
| `GITHUB_TOKEN` | GitHub token for AI-enhanced migration (needs Copilot access) and GitHub API calls in validation | For `--ai` mode only |
| `GL2GH_MODEL` | AI model override (default: gpt-4.1) | No |
| `GL2GH_LOG_LEVEL` | Logging verbosity: DEBUG, INFO, WARNING, ERROR | No |
| `GL2GH_MAX_TOKENS` | Max tokens per agent call (default: 4096) | No |
| `GL2GH_OUTPUT_DIR` | Default output directory (default: `.github/workflows`) | No |

## Important Files to Know

- **`src/gl2gh/mappings/rules.py`** -- This is the core of the rule-based conversion. The `GITLAB_TO_GHA_VARS` dictionary, `translate_variable()`, `stages_to_needs_graph()`, and `parse_only_except()` functions handle the majority of the translation work. Any new GitLab CI feature support starts here.

- **`src/gl2gh/models.py`** -- All data models. `ConversionResult.success` is a computed property: `len(errors) == 0 and len(output_workflows) > 0`.

- **`src/gl2gh/parser.py`** -- The `GLOBAL_KEYWORDS` set determines which YAML root keys are treated as global configuration vs. job definitions. Any key not in this set and whose value is a dict is treated as a job. Template jobs (`.dot` prefix) have `is_template=True`.

- **`src/gl2gh/converter.py`** -- The `_build_steps()` method defines the step ordering: checkout -> cache -> before_script -> script -> after_script -> artifacts -> reports. Every job gets `actions/checkout@v4` as its first step.

- **`tests/conftest.py`** -- Shared fixtures. The `minimal_pipeline_yaml` fixture is useful for quick converter tests. Test fixture YAML files live in `tests/fixtures/gitlab/`.
