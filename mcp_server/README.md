# gl2gh MCP Server — GitLab CI RAG

An MCP (Model Context Protocol) server that provides **Retrieval-Augmented Generation** for converting GitLab CI/CD pipelines to GitHub Actions. It indexes real-world GitLab CI files and curated conversion pairs, then exposes semantic search tools that AI agents can use for more accurate conversions.

## Architecture

```
┌──────────────────┐     ┌──────────────────────────┐     ┌─────────────────┐
│  gl2gh Agent     │────▶│  MCP Server (this)       │────▶│  ChromaDB       │
│  or any LLM      │◀────│  - pattern_search        │◀────│  Vector Store   │
│  with MCP support │     │  - conversion_examples   │     │  (embedded)     │
│                   │     │  - validate_corpus       │     └─────────────────┘
│                   │     │  - suggest_action        │
└──────────────────┘     └──────────────────────────┘
                                    │
                                    ▼
                          ┌──────────────────┐
                          │  Indexed Data     │
                          │  - GitLab CI YAMLs│
                          │  - Conversion pairs│
                          │  - Pattern metadata│
                          └──────────────────┘
```

## Tools Exposed

| Tool | Description |
|------|-------------|
| `find_similar_gitlab_pattern` | Search the corpus for GitLab CI patterns similar to a YAML snippet |
| `get_conversion_example` | Retrieve real before/after conversion examples for a GitLab CI feature |
| `validate_against_corpus` | Validate a conversion output against known patterns; returns confidence + warnings |
| `suggest_github_action` | Suggest GitHub Actions marketplace actions for a GitLab CI job type |
| `index_stats` | Return stats about the indexed corpus |

## Quick Start

### 1. Install dependencies

```bash
cd mcp_server
uv sync --all-extras
```

### 2. Seed the data

Populate the corpus with curated conversion pairs and example GitLab CI files:

```bash
python -m mcp_server.seed_data
```

### 3. Build the vector index

```bash
python -c "from mcp_server.embeddings import build_index_from_disk; build_index_from_disk()"
```

### 4. Run the MCP server

```bash
python -m mcp_server
```

### 5. (Optional) Crawl more data

Fetch GitLab CI files from public GitLab projects:

```bash
python -c "
from mcp_server.indexer import GitLabCIIndexer
idx = GitLabCIIndexer()
idx.crawl_gitlab_projects(min_stars=100, max_pages=5)
idx.save_index()
"
```

## VS Code Configuration

Add to your VS Code `settings.json`:

```json
{
  "mcp": {
    "servers": {
      "gl2gh-gitlab-ci-rag": {
        "command": "python",
        "args": ["-m", "mcp_server"],
        "cwd": "/path/to/gitlab-to-gh-actions"
      }
    }
  }
}
```

## Claude Desktop Configuration

Add to `~/.config/claude/claude_desktop_config.json` (Linux/Mac) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "gl2gh-gitlab-ci-rag": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/gitlab-to-gh-actions"
    }
  }
}
```

## Data Sources

The corpus can be populated from multiple sources:

1. **Curated conversion pairs** (included) — 10 hand-verified before/after examples covering common patterns
2. **GitLab.com API** — Crawl public projects for `.gitlab-ci.yml` files
3. **GitHub API** — Find repos that migrated from GitLab (have both `.gitlab-ci.yml` and `.github/workflows/`)
4. **Local files** — Index your own `.gitlab-ci.yml` files

## Integration with gl2gh

The MCP server is designed to work alongside the `gl2gh` migration agent. When the agent encounters a complex GitLab CI pattern, it can query the MCP server for:

- Similar patterns from real projects
- Reference conversion examples
- Validation of its generated output
- Recommended GitHub Actions to use

This RAG approach grounds the AI's output in real-world examples, significantly improving conversion accuracy for complex pipelines.
