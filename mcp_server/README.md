# gl2gh MCP Server — GitLab CI RAG (v0.2.0)

An MCP (Model Context Protocol) server providing **Retrieval-Augmented Generation** for converting GitLab CI/CD pipelines to GitHub Actions. Indexes real-world GitLab CI files and curated conversion pairs, then exposes semantic search tools for more accurate conversions.

## Architecture

```
┌──────────────────┐     ┌──────────────────────────┐     ┌─────────────────┐
│  gl2gh Agent     │────▶│  MCP Server (this)       │────▶│  ChromaDB       │
│  or any LLM      │◀────│  - pattern_search        │◀────│  Vector Store   │
│  with MCP support │     │  - conversion_examples   │     │  (embedded)     │
│                   │     │  - validate_corpus       │     └─────────────────┘
│                   │     │  - suggest_action        │
│                   │     │  - confidence_score  NEW │
│                   │     │  - workflow_split    NEW │
│                   │     │  - record_feedback   NEW │
└──────────────────┘     └──────────────────────────┘
                                    │
                                    ▼
                          ┌──────────────────┐
                          │  Indexed Data     │
                          │  - GitLab CI YAMLs│
                          │  - Conversion pairs│
                          │  - Pattern metadata│
                          │  - User feedback   │
                          └──────────────────┘
```

## Tools (8 total)

| Tool | Description |
|------|-------------|
| `find_similar_gitlab_pattern` | Search corpus for similar GitLab CI YAML snippets |
| `get_conversion_example` | Retrieve real before/after conversion examples |
| `validate_against_corpus` | Validate conversion output; confidence + warnings |
| `suggest_github_action` | Suggest Actions marketplace actions for a job type |
| `index_stats` | Corpus statistics |
| **`confidence_score`** | Score each job 0.0–1.0 on conversion confidence |
| **`suggest_workflow_split`** | Recommend splitting large pipelines into multiple files |
| **`record_feedback`** | Record user corrections for RAG improvement |

## Quick Start

```bash
# Install
cd mcp_server && pip install -e ".[dev]"

# Seed curated data
python -m mcp_server.seed_data

# Run the server
python -m mcp_server
```

## CLI Integration

```bash
gl2gh rag-status          # Check RAG store health
gl2gh index               # Re-index seed data
gl2gh index /path/to/dir  # Index local .gitlab-ci.yml files
gl2gh index --gitlab      # Crawl public GitLab projects
gl2gh index --github      # Find GitHub migration pairs
```

## VS Code Configuration

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "gl2gh-rag": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

## Data Sources

1. **Curated pairs** (included) — 10 verified before/after examples
2. **GitLab.com API** — Crawl public projects
3. **GitHub API** — Find repos migrated from GitLab
4. **Local files** — Index your own `.gitlab-ci.yml` files
5. **User feedback** — Corrections recorded via `record_feedback` tool
