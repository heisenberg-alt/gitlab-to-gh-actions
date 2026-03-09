"""Embedding and vector store for GitLab CI pattern search.

Uses chromadb for local vector storage and sentence-transformers for embeddings.
Falls back to a simple TF-IDF approach if sentence-transformers is unavailable.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
GITLAB_CI_DIR = DATA_DIR / "gitlab_ci"
CONVERSIONS_DIR = DATA_DIR / "conversions"
CHROMA_DIR = DATA_DIR / "vectordb"

# GitLab CI keywords that indicate interesting patterns
PATTERN_KEYWORDS = {
    "extends",
    "include",
    "rules",
    "needs",
    "parallel",
    "services",
    "cache",
    "artifacts",
    "environment",
    "trigger",
    "resource_group",
    "interruptible",
    "release",
    "pages",
    "dind",
    "docker",
    "matrix",
    "only",
    "except",
    "when",
    "dependencies",
    "coverage",
    "retry",
    "timeout",
    "variables",
    "allow_failure",
}


def extract_patterns_from_yaml(content: str) -> list[str]:
    """Identify which GitLab CI patterns are present in a YAML file."""
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError:
        return []

    if not isinstance(data, dict):
        return []

    patterns: set[str] = set()

    def _scan(obj: Any, depth: int = 0) -> None:
        if depth > 10:
            return
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(key, str) and key in PATTERN_KEYWORDS:
                    patterns.add(key)
                if isinstance(key, str) and key.startswith("."):
                    patterns.add("template")
                _scan(value, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                _scan(item, depth + 1)

    _scan(data)

    # Detect higher-level patterns
    content_lower = content.lower()
    if "docker:dind" in content_lower or "docker build" in content_lower:
        patterns.add("docker_build")
    if "deploy" in content_lower and "environment" in content_lower:
        patterns.add("deployment")
    if "sast" in content_lower or "security" in content_lower:
        patterns.add("security_scanning")
    if "auto-devops" in content_lower:
        patterns.add("auto_devops")
    if "multi-project" in content_lower or "trigger:" in content_lower:
        patterns.add("multi_project")

    return sorted(patterns)


def yaml_to_text_description(content: str) -> str:
    """Convert a GitLab CI YAML file to a searchable text description."""
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError:
        return content[:500]

    if not isinstance(data, dict):
        return content[:500]

    parts: list[str] = []

    # Global config
    if "stages" in data:
        parts.append(f"stages: {', '.join(data['stages'])}")
    if "variables" in data:
        var_keys = (
            list(data["variables"].keys())
            if isinstance(data["variables"], dict)
            else []
        )
        parts.append(f"global variables: {', '.join(var_keys[:10])}")
    if "include" in data:
        parts.append("includes external templates")
    if "default" in data:
        parts.append("has default configuration")

    # Jobs
    global_keys = {
        "stages", "variables", "include", "default", "workflow",
        "image", "services", "before_script", "after_script", "cache",
    }
    for key, value in data.items():
        if key in global_keys or not isinstance(value, dict):
            continue
        job_desc = [f"job '{key}'"]
        if "stage" in value:
            job_desc.append(f"in stage '{value['stage']}'")
        if "image" in value:
            img = (
                value["image"]
                if isinstance(value["image"], str)
                else value["image"].get("name", "")
            )
            job_desc.append(f"using image {img}")
        if "services" in value:
            job_desc.append("with services")
        if "rules" in value:
            job_desc.append("with conditional rules")
        if "extends" in value:
            extends = (
                value["extends"]
                if isinstance(value["extends"], list)
                else [value["extends"]]
            )
            job_desc.append(f"extending {', '.join(extends)}")
        if "cache" in value:
            job_desc.append("with caching")
        if "artifacts" in value:
            job_desc.append("producing artifacts")
        if "environment" in value:
            env_name = (
                value["environment"]
                if isinstance(value["environment"], str)
                else value["environment"].get("name", "")
            )
            job_desc.append(f"deploying to {env_name}")
        if "parallel" in value:
            job_desc.append("with parallel execution")
        if "trigger" in value:
            job_desc.append("triggering downstream pipeline")
        if "needs" in value:
            job_desc.append("with explicit dependencies")

        # Script summary
        script = value.get("script", [])
        if isinstance(script, list):
            for cmd in script[:3]:
                if isinstance(cmd, str):
                    job_desc.append(f"runs: {cmd[:80]}")

        parts.append(" ".join(job_desc))

    patterns = extract_patterns_from_yaml(content)
    if patterns:
        parts.append(f"patterns: {', '.join(patterns)}")

    return "\n".join(parts)


class VectorStore:
    """ChromaDB-backed vector store for GitLab CI patterns."""

    def __init__(self, collection_name: str = "gitlab_ci_patterns") -> None:
        self.collection_name = collection_name
        self._collection = None
        self._client = None

    def _ensure_collection(self):
        if self._collection is not None:
            return
        try:
            import chromadb

            CHROMA_DIR.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except ImportError:
            logger.warning(
                "chromadb not installed. Install with: pip install chromadb"
            )
            raise

    def index_file(
        self,
        file_id: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Index a single GitLab CI file into the vector store."""
        self._ensure_collection()

        description = yaml_to_text_description(content)
        patterns = extract_patterns_from_yaml(content)

        doc_metadata = {
            "patterns": ",".join(patterns),
            "content_length": len(content),
            "source": (metadata or {}).get("source", "unknown"),
        }
        if metadata:
            for k, v in metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    doc_metadata[k] = v

        self._collection.upsert(
            ids=[file_id],
            documents=[description],
            metadatas=[doc_metadata],
        )

    def index_conversion_pair(
        self,
        pair_id: str,
        gitlab_content: str,
        github_workflows: dict[str, str],
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Index a GitLab -> GitHub conversion pair."""
        self._ensure_collection()

        gl_description = yaml_to_text_description(gitlab_content)
        patterns = extract_patterns_from_yaml(gitlab_content)

        gh_summary_parts = []
        for name, wf_content in github_workflows.items():
            gh_summary_parts.append(f"workflow: {name}")
            try:
                wf_data = yaml.safe_load(wf_content)
                if isinstance(wf_data, dict):
                    if "on" in wf_data:
                        on_val = wf_data["on"]
                        triggers = (
                            list(on_val.keys())
                            if isinstance(on_val, dict)
                            else on_val
                        )
                        gh_summary_parts.append(
                            f"triggers: {triggers}"
                        )
                    if "jobs" in wf_data:
                        job_keys = list(
                            wf_data["jobs"].keys()
                        )
                        gh_summary_parts.append(
                            f"jobs: {job_keys}"
                        )
            except yaml.YAMLError:
                pass

        full_description = (
            f"GITLAB CI:\n{gl_description}\n\n"
            f"GITHUB ACTIONS:\n" + "\n".join(gh_summary_parts)
        )

        doc_metadata = {
            "type": "conversion_pair",
            "patterns": ",".join(patterns),
            "has_github_equivalent": True,
            "workflow_count": len(github_workflows),
        }
        if metadata:
            for k, v in metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    doc_metadata[k] = v

        self._collection.upsert(
            ids=[f"pair_{pair_id}"],
            documents=[full_description],
            metadatas=[doc_metadata],
        )

    def search(
        self,
        query: str,
        n_results: int = 5,
        pattern_filter: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Search for similar GitLab CI patterns."""
        self._ensure_collection()

        where = None
        if pattern_filter:
            where = {"patterns": {"$contains": pattern_filter}}

        results = self._collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        matches: list[dict[str, Any]] = []
        if not results["ids"] or not results["ids"][0]:
            return matches

        for i, doc_id in enumerate(results["ids"][0]):
            match = {
                "id": doc_id,
                "description": (
                    results["documents"][0][i]
                    if results["documents"]
                    else ""
                ),
                "metadata": (
                    results["metadatas"][0][i]
                    if results["metadatas"]
                    else {}
                ),
                "distance": (
                    results["distances"][0][i]
                    if results["distances"]
                    else 1.0
                ),
            }
            matches.append(match)

        return matches

    def search_by_pattern(
        self, patterns: list[str], n_results: int = 5
    ) -> list[dict[str, Any]]:
        """Search for files that use specific GitLab CI patterns."""
        query = f"GitLab CI with patterns: {', '.join(patterns)}"
        return self.search(query, n_results=n_results)

    def get_conversion_pairs(
        self, query: str, n_results: int = 3
    ) -> list[dict[str, Any]]:
        """Search specifically for conversion pairs (before/after examples)."""
        self._ensure_collection()

        results = self._collection.query(
            query_texts=[query],
            n_results=n_results,
            where={"type": "conversion_pair"},
            include=["documents", "metadatas", "distances"],
        )

        matches: list[dict[str, Any]] = []
        if not results["ids"] or not results["ids"][0]:
            return matches

        for i, doc_id in enumerate(results["ids"][0]):
            pair_hash = doc_id.replace("pair_", "")
            pair_dir = CONVERSIONS_DIR / pair_hash

            gitlab_content = ""
            github_workflows: dict[str, str] = {}
            if pair_dir.exists():
                gl_file = pair_dir / "gitlab-ci.yml"
                if gl_file.exists():
                    gitlab_content = gl_file.read_text()
                for wf_file in pair_dir.glob("*.yml"):
                    if wf_file.name != "gitlab-ci.yml":
                        github_workflows[wf_file.name] = wf_file.read_text()
                for wf_file in pair_dir.glob("*.yaml"):
                    github_workflows[wf_file.name] = wf_file.read_text()

            matches.append({
                "id": doc_id,
                "description": (
                    results["documents"][0][i]
                    if results["documents"]
                    else ""
                ),
                "metadata": (
                    results["metadatas"][0][i]
                    if results["metadatas"]
                    else {}
                ),
                "distance": (
                    results["distances"][0][i]
                    if results["distances"]
                    else 1.0
                ),
                "gitlab_ci": gitlab_content,
                "github_workflows": github_workflows,
            })

        return matches

    def stats(self) -> dict[str, Any]:
        """Return stats about the vector store."""
        self._ensure_collection()
        count = self._collection.count()
        return {
            "total_documents": count,
            "collection": self.collection_name,
            "storage_path": str(CHROMA_DIR),
        }


def build_index_from_disk() -> VectorStore:
    """Rebuild the vector store from files already on disk."""
    store = VectorStore()
    indexed_count = 0

    # Index standalone GitLab CI files
    for yml_file in GITLAB_CI_DIR.glob("*.yml"):
        content = yml_file.read_text()
        try:
            yaml.safe_load(content)
        except yaml.YAMLError:
            continue
        store.index_file(yml_file.stem, content, {"source": "indexed"})
        indexed_count += 1

    # Index conversion pairs
    for pair_dir in CONVERSIONS_DIR.iterdir():
        if not pair_dir.is_dir():
            continue
        gl_file = pair_dir / "gitlab-ci.yml"
        if not gl_file.exists():
            continue
        gl_content = gl_file.read_text()
        gh_workflows: dict[str, str] = {}
        for wf in pair_dir.glob("*.yml"):
            if wf.name != "gitlab-ci.yml":
                gh_workflows[wf.name] = wf.read_text()
        for wf in pair_dir.glob("*.yaml"):
            gh_workflows[wf.name] = wf.read_text()

        if gh_workflows:
            store.index_conversion_pair(pair_dir.name, gl_content, gh_workflows)
            indexed_count += 1

    logger.info("Indexed %d documents into vector store", indexed_count)
    return store
