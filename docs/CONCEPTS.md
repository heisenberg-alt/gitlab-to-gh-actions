# Architecture & Concepts

## Overview

gl2gh is a two-stage conversion system for migrating GitLab CI/CD pipelines to GitHub Actions workflows.

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────────┐
│  .gitlab-ci.yml │────>│  Parser      │────>│  GitLabPipeline  │
└─────────────────┘     │  (ruamel)    │     │  (data model)    │
                        └──────────────┘     └────────┬─────────┘
                                                      │
                                          ┌───────────┴───────────┐
                                          │                       │
                                   ┌──────▼──────┐     ┌─────────▼────────┐
                                   │  Rule-based  │     │  AI-Enhanced     │
                                   │  Converter   │     │  MigrationAgent  │
                                   │  (default)   │     │  (--ai flag)     │
                                   └──────┬──────┘     └─────────┬────────┘
                                          │                       │
                                          └───────────┬───────────┘
                                                      │
                                             ┌────────▼────────┐
                                             │ ConversionResult │
                                             │ (YAML output)    │
                                             └────────┬────────┘
                                                      │
                                             ┌────────▼────────┐
                                             │  .github/       │
                                             │  workflows/     │
                                             │  ci.yml         │
                                             └─────────────────┘
```

## Components

### Parser (`parser.py`)

The `GitLabCIParser` reads `.gitlab-ci.yml` files and produces a `GitLabPipeline` model.

Key responsibilities:
- **YAML parsing** with `ruamel.yaml` to preserve anchors and aliases
- **Template detection** — jobs starting with `.` are marked as templates
- **Extends resolution** — merges parent template fields into child jobs
- **Service normalization** — handles both string (`postgres:15`) and dict (`{name: postgres, alias: db}`) forms
- **Variable extraction** — handles both simple (`VAR: value`) and descriptive (`VAR: {value: v, description: d}`) forms
- **Global keyword filtering** — separates `stages`, `variables`, `default`, `include`, `workflow` from job definitions

### Models (`models.py`)

Pydantic-style dataclasses representing the intermediate representation:

- `GitLabJob` — name, stage, image, script, before/after_script, variables, cache, artifacts, services, rules, needs, environment, parallel, timeout, allow_failure, when, only/except, is_template
- `GitLabPipeline` — stages, jobs, variables, default_image, includes, workflow
- `GitLabArtifacts` — paths, reports, expire_in, when
- `GitLabCache` — key, paths, policy
- `GitLabEnvironment` — name, url, action
- `GitLabRetry` — max, when
- `GitLabParallel` — matrix list
- `ConversionResult` — success flag, output_workflows dict, errors, warnings, unsupported_features, conversion_notes, ai_enhanced flag

### Converter (`converter.py`)

The `GitLabToGitHubConverter` transforms a `GitLabPipeline` into GitHub Actions YAML.

Conversion pipeline:
1. **Build triggers** from `only/except` or default `push`/`pull_request`
2. **Add `workflow_dispatch`** for manual triggering
3. **Translate global variables** to workflow-level `env`
4. **Convert each job:**
   - Map `image` to `runs-on` + `container`
   - Convert `services` to GitHub Actions service containers
   - Build `needs` from explicit needs or stage ordering
   - Convert `cache` to `actions/cache@v4` step
   - Convert `artifacts` to `actions/upload-artifact@v4` step
   - Convert JUnit reports to `dorny/test-reporter@v1`
   - Map `environment` to GitHub environment
   - Convert `rules` to `if` conditions
   - Map `parallel.matrix` to `strategy.matrix`
   - Set `timeout-minutes` from `timeout`
   - Set `continue-on-error` from `allow_failure`
5. **Generate clean YAML** with header comment

### Mapping Rules (`mappings/rules.py`)

Pure functions for translating individual GitLab CI constructs:

- `image_to_runner(image)` — maps Docker images to GitHub-hosted runners
- `translate_variable(value)` — replaces `$CI_*` variables with `${{ github.* }}` equivalents
- `translate_variables_dict(vars)` — batch variable translation
- `parse_only_except(only, except_)` — converts to `on` trigger config
- `convert_rules_to_if(rules)` — converts rule conditions to `if` expression
- `parse_timeout_minutes(timeout)` — parses `1h 30m` to `90`
- `translate_cache_key(key)` — replaces CI variables in cache keys
- `stages_to_needs_graph(jobs, stages)` — converts stage ordering to dependency graph
- `parse_expire_in_days(expire_in)` — converts `1 week` to `7` (retention days)

### AI Agents (`agents/`)

#### MigrationAgent (`migration_agent.py`)

Uses Claude Opus with tool use for complex migrations:

```python
tools = [
    {"name": "validate_yaml", "description": "Validate workflow YAML"},
    {"name": "save_workflow", "description": "Save the final workflow"},
    {"name": "add_warning", "description": "Add a migration warning"},
    {"name": "add_conversion_note", "description": "Add a conversion note"},
]
```

The agent enters an agentic loop: Claude generates tool calls, the agent executes them, and feeds results back until the assistant produces a final response with `stop_reason == "end_turn"`.

Falls back to rule-based conversion if the API call fails.

#### ValidatorAgent (`validator_agent.py`)

Two-phase validation:
1. **Static checks** (no API call) — required fields, job structure, needs references
2. **AI validation** (optional) — semantic analysis of workflow correctness

#### OptimizerAgent (`optimizer_agent.py`)

Uses Claude with streaming to suggest workflow optimizations:
- Caching improvements
- Job parallelization opportunities
- Action version updates
- Security improvements

### CLI (`cli.py`)

Click-based CLI with Rich terminal output:

| Command | Description |
|---------|-------------|
| `gl2gh migrate` | Convert GitLab CI to GitHub Actions |
| `gl2gh inspect` | Analyze a GitLab CI file |
| `gl2gh validate` | Validate generated workflows |
| `gl2gh migrate-repo` | Full repository migration |
| `gl2gh gh-status` | Check gh CLI and Copilot status |

### Utilities (`utils/yaml_utils.py`)

- `load_yaml(text)` — safe YAML loading with PyYAML
- `load_yaml_with_anchors(text)` — YAML loading preserving anchors (ruamel)
- `dump_yaml(data)` — clean YAML output with sorted keys
- `validate_yaml_syntax(text)` — returns error string or None
- `add_yaml_header(text, source)` — adds "Generated by gl2gh" comment

## Design Decisions

### Why Two Conversion Modes?

Rule-based conversion is fast, deterministic, and doesn't require API keys. It handles 80%+ of common GitLab CI patterns. AI-enhanced mode exists for the remaining complex cases where pattern matching isn't sufficient (complex rules conditions, multi-project pipelines, custom runner configurations).

### Why ruamel.yaml?

GitLab CI heavily uses YAML anchors (`&anchor` / `*anchor`) for template reuse. PyYAML's `safe_load` doesn't preserve anchor information. `ruamel.yaml` maintains the full YAML structure including anchors, which is essential for resolving `extends` correctly.

### Why Click + Rich?

Click provides a clean command structure with automatic help generation, parameter validation, and shell completion. Rich adds formatted tables, syntax highlighting, progress spinners, and colored output for a professional CLI experience.

### Why Not Direct GitHub API?

gl2gh generates YAML files locally rather than pushing directly to GitHub. This gives users full control to review, modify, and test workflows before committing. The `gh` CLI integration is optional and used for convenience operations (repo creation, workflow triggering).
