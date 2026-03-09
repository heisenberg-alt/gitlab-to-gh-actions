"""Quick smoke test for the MCP server tools."""
from mcp_server.embeddings import build_index_from_disk
from mcp_server.tools.handlers import (
    ConversionExampleTool,
    PatternSearchTool,
    SuggestGitHubActionTool,
    ValidateAgainstCorpusTool,
)

store = build_index_from_disk()

# Test 1: Pattern search
print("=== Pattern Search ===")
tool = PatternSearchTool(store)
result = tool.run(
    snippet=(
        "test:\n  stage: test\n  services:\n"
        "    - postgres:16\n  script:\n    - pytest -v\n"
    ),
    limit=3,
)
for r in result["results"][:2]:
    print(f"  {r['id']} (sim: {r['similarity']}) -- patterns: {r['patterns']}")

# Test 2: Conversion examples
print("\n=== Conversion Examples ===")
ex_tool = ConversionExampleTool(store)
examples = ex_tool.run(feature="services", limit=2)
print(f"  Found {examples['total_found']} examples for 'services'")
for ex in examples["examples"][:1]:
    print(f"  Similarity: {ex['similarity']}")
    print(f"  GitLab CI preview: {ex['gitlab_ci'][:100]}...")
    print(f"  GH workflows: {list(ex['github_workflows'].keys())}")

# Test 3: Suggest actions
print("\n=== Suggest Actions ===")
suggest = SuggestGitHubActionTool(store)
suggestions = suggest.run(
    gitlab_snippet=(
        "build_docker:\n  image: docker:24\n"
        "  services:\n    - docker:24-dind\n"
        "  script:\n    - docker build -t img .\n"
        "    - docker push img\n"
    ),
)
print(f"  Detected: {suggestions['detected_patterns']}")
for s in suggestions["suggested_actions"][:4]:
    print(f"  {s['action']} -- {s['reason']}")

# Test 4: Validate against corpus
print("\n=== Validate Against Corpus ===")
validator = ValidateAgainstCorpusTool(store)
val_result = validator.run(
    gitlab_ci=(
        "stages:\n  - test\ntest:\n  services:\n"
        "    - postgres:16\n  script:\n    - pytest\n"
        "  cache:\n    paths:\n      - .cache/\n"
    ),
    github_actions=(
        "name: CI\non:\n  push:\njobs:\n  test:\n"
        "    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - run: pytest\n"
    ),
)
print(f"  Valid: {val_result['valid']}")
print(f"  Confidence: {val_result['confidence']}")
print(f"  Warnings: {val_result['warnings']}")
print(f"  Suggestions: {val_result['suggestions']}")

print("\n=== Stats ===")
print(f"  {store.stats()}")
print("\nAll tests passed!")
