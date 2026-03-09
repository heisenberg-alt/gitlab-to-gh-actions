"""MCP Tools — Pattern search, conversion examples, and validation."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import yaml

from mcp_server.embeddings import (
    DATA_DIR,
    GITLAB_CI_DIR,
    VectorStore,
    extract_patterns_from_yaml,
    yaml_to_text_description,
)

logger = logging.getLogger(__name__)


class PatternSearchTool:
    """Find similar GitLab CI patterns in the indexed corpus."""

    def __init__(self, store: VectorStore) -> None:
        self.store = store

    def run(
        self,
        snippet: str,
        limit: int = 5,
        pattern_filter: Optional[str] = None,
    ) -> dict[str, Any]:
        description = yaml_to_text_description(snippet)
        detected_patterns = extract_patterns_from_yaml(snippet)

        results = self.store.search(
            query=description,
            n_results=limit,
            pattern_filter=pattern_filter,
        )

        output_results = []
        for r in results:
            file_id = r["id"]
            # Try to load the actual YAML content
            content = ""
            for suffix in (".yml", ".yaml"):
                candidate = GITLAB_CI_DIR / f"{file_id}{suffix}"
                if candidate.exists():
                    content = candidate.read_text()[:2000]
                    break

            output_results.append({
                "id": file_id,
                "similarity": round(1.0 - r.get("distance", 1.0), 3),
                "patterns": r.get("metadata", {}).get("patterns", "").split(","),
                "source": r.get("metadata", {}).get("source", "unknown"),
                "description": r.get("description", "")[:500],
                "content_preview": content[:1000] if content else "",
            })

        return {
            "query_patterns": detected_patterns,
            "results": output_results,
            "total_found": len(output_results),
        }


class ConversionExampleTool:
    """Retrieve real-world GitLab -> GitHub conversion examples."""

    def __init__(self, store: VectorStore) -> None:
        self.store = store

    def run(
        self,
        feature: str,
        limit: int = 3,
    ) -> dict[str, Any]:
        pairs = self.store.get_conversion_pairs(
            query=f"GitLab CI {feature} conversion to GitHub Actions",
            n_results=limit,
        )

        examples = []
        for pair in pairs:
            example = {
                "similarity": round(1.0 - pair.get("distance", 1.0), 3),
                "gitlab_ci": pair.get("gitlab_ci", "")[:3000],
                "github_workflows": {},
                "patterns": pair.get("metadata", {}).get("patterns", "").split(","),
            }
            for name, content in pair.get("github_workflows", {}).items():
                example["github_workflows"][name] = content[:3000]
            examples.append(example)

        return {
            "feature": feature,
            "examples": examples,
            "total_found": len(examples),
        }


class ValidateAgainstCorpusTool:
    """Validate a conversion output against known patterns in the corpus."""

    def __init__(self, store: VectorStore) -> None:
        self.store = store

    def run(
        self,
        gitlab_ci: str,
        github_actions: str,
    ) -> dict[str, Any]:
        gl_patterns = extract_patterns_from_yaml(gitlab_ci)

        # Find similar GitLab patterns and their conversions
        gl_description = yaml_to_text_description(gitlab_ci)
        similar_pairs = self.store.get_conversion_pairs(
            query=gl_description, n_results=3
        )

        warnings: list[str] = []
        suggestions: list[str] = []
        confidence = 0.8  # Base confidence

        # Parse the generated GitHub Actions
        try:
            gh_data = yaml.safe_load(github_actions)
        except yaml.YAMLError:
            return {
                "valid": False,
                "confidence": 0.0,
                "warnings": ["Generated GitHub Actions YAML is invalid"],
                "suggestions": ["Fix YAML syntax before validation"],
            }

        if not isinstance(gh_data, dict):
            return {
                "valid": False,
                "confidence": 0.0,
                "warnings": ["GitHub Actions output is not a valid workflow"],
                "suggestions": [],
            }

        # Check structural completeness
        if "on" not in gh_data and True not in gh_data:
            # PyYAML reads 'on:' as True (boolean), so check both
            warnings.append("Missing 'on:' trigger definition")
            confidence -= 0.2

        if "jobs" not in gh_data:
            warnings.append("Missing 'jobs:' section")
            confidence -= 0.3

        # Check pattern coverage
        if "services" in gl_patterns:
            jobs = gh_data.get("jobs", {})
            has_services = any(
                "services" in job_data
                for job_data in jobs.values()
                if isinstance(job_data, dict)
            )
            if not has_services:
                warnings.append(
                    "GitLab CI uses services but no"
                    " services found in GitHub Actions output"
                )
                suggestions.append(
                    "Add services: section to jobs that need database/cache containers"
                )
                confidence -= 0.1

        if "cache" in gl_patterns:
            gh_str = github_actions.lower()
            if "actions/cache" not in gh_str:
                warnings.append(
                    "GitLab CI uses caching but no actions/cache found in output"
                )
                suggestions.append("Add actions/cache@v4 step for dependency caching")
                confidence -= 0.1

        if "artifacts" in gl_patterns:
            gh_str = github_actions.lower()
            if "upload-artifact" not in gh_str and "download-artifact" not in gh_str:
                warnings.append(
                    "GitLab CI uses artifacts but no"
                    " upload/download-artifact actions found"
                )
                suggestions.append(
                    "Add actions/upload-artifact@v4 and actions/download-artifact@v4"
                )
                confidence -= 0.1

        if "environment" in gl_patterns:
            jobs = gh_data.get("jobs", {})
            has_env = any(
                "environment" in job_data
                for job_data in jobs.values()
                if isinstance(job_data, dict)
            )
            if not has_env:
                warnings.append(
                    "GitLab CI uses environments but none defined in GitHub Actions"
                )
                suggestions.append("Add environment: to deployment jobs")
                confidence -= 0.05

        # Compare against similar conversion pairs
        if similar_pairs:
            suggestions.append(
                f"Found {len(similar_pairs)} similar"
                " conversion(s) in corpus for reference"
            )
            confidence += 0.05 * len(similar_pairs)

        confidence = max(0.0, min(1.0, confidence))

        return {
            "valid": len(warnings) == 0,
            "confidence": round(confidence, 2),
            "source_patterns": gl_patterns,
            "warnings": warnings,
            "suggestions": suggestions,
            "similar_conversions_found": len(similar_pairs),
        }


class SuggestGitHubActionTool:
    """Suggest appropriate GitHub Actions marketplace actions for GitLab job types."""

    # Curated mapping of common GitLab job patterns to GitHub Actions
    ACTION_SUGGESTIONS: dict[str, list[dict[str, str]]] = {
        "docker_build": [
            {
                "action": "docker/build-push-action@v6",
                "description": "Build and push Docker images with BuildKit",
            },
            {
                "action": "docker/login-action@v3",
                "description": "Login to container registries (ghcr.io, Docker Hub)",
            },
            {
                "action": "docker/setup-buildx-action@v3",
                "description": "Set up Docker Buildx for multi-platform builds",
            },
        ],
        "security_scanning": [
            {
                "action": "github/codeql-action/analyze@v3",
                "description": "GitHub CodeQL SAST analysis",
            },
            {
                "action": "aquasecurity/trivy-action@master",
                "description": "Vulnerability scanner for containers and code",
            },
        ],
        "deployment": [
            {
                "action": "actions/deploy-pages@v4",
                "description": "Deploy to GitHub Pages",
            },
            {
                "action": "aws-actions/configure-aws-credentials@v4",
                "description": "Configure AWS credentials for deployment",
            },
        ],
        "cache": [
            {
                "action": "actions/cache@v4",
                "description": "Cache dependencies and build outputs",
            },
        ],
        "artifacts": [
            {
                "action": "actions/upload-artifact@v4",
                "description": "Upload build artifacts",
            },
            {
                "action": "actions/download-artifact@v4",
                "description": "Download artifacts from previous jobs",
            },
        ],
        "testing": [
            {
                "action": "dorny/test-reporter@v1",
                "description": "Display test results in PR checks",
            },
            {
                "action": "codecov/codecov-action@v4",
                "description": "Upload code coverage reports",
            },
        ],
        "node": [
            {
                "action": "actions/setup-node@v4",
                "description": "Set up Node.js environment",
            },
        ],
        "python": [
            {
                "action": "actions/setup-python@v5",
                "description": "Set up Python environment",
            },
        ],
        "pages": [
            {
                "action": "actions/configure-pages@v5",
                "description": "Configure GitHub Pages",
            },
            {
                "action": "actions/upload-pages-artifact@v3",
                "description": "Upload Pages artifact",
            },
            {
                "action": "actions/deploy-pages@v4",
                "description": "Deploy to GitHub Pages",
            },
        ],
        "release": [
            {
                "action": "softprops/action-gh-release@v2",
                "description": "Create GitHub releases with assets",
            },
        ],
        "matrix": [
            {
                "action": "actions/setup-python@v5",
                "description": "Python matrix builds with strategy.matrix",
            },
        ],
    }

    def __init__(self, store: VectorStore) -> None:
        self.store = store

    def run(self, gitlab_snippet: str) -> dict[str, Any]:
        patterns = extract_patterns_from_yaml(gitlab_snippet)

        # Also detect from script content
        content_lower = gitlab_snippet.lower()
        if any(k in content_lower for k in ("npm", "yarn", "node")):
            patterns.append("node")
        if any(k in content_lower for k in ("pip", "python", "pytest")):
            patterns.append("python")
        if any(k in content_lower for k in ("test", "pytest", "jest")):
            patterns.append("testing")

        suggestions: list[dict[str, Any]] = []
        seen_actions: set[str] = set()

        for pattern in patterns:
            if pattern in self.ACTION_SUGGESTIONS:
                for action in self.ACTION_SUGGESTIONS[pattern]:
                    if action["action"] not in seen_actions:
                        suggestions.append({
                            "action": action["action"],
                            "description": action["description"],
                            "reason": f"Detected pattern: {pattern}",
                        })
                        seen_actions.add(action["action"])

        # Always suggest checkout
        if "actions/checkout@v4" not in seen_actions:
            suggestions.insert(0, {
                "action": "actions/checkout@v4",
                "description": "Check out repository code",
                "reason": "Required for all workflows",
            })

        return {
            "detected_patterns": patterns,
            "suggested_actions": suggestions,
            "total_suggestions": len(suggestions),
        }


class ConfidenceScoreTool:
    """Score individual jobs on conversion confidence using RAG."""

    def __init__(self, store: VectorStore) -> None:
        self.store = store

    def run(
        self,
        gitlab_ci: str,
        github_actions: str,
    ) -> dict[str, Any]:
        try:
            gl_data = yaml.safe_load(gitlab_ci)
        except yaml.YAMLError:
            return {"jobs": [], "overall": 0.0}

        if not isinstance(gl_data, dict):
            return {"jobs": [], "overall": 0.0}

        try:
            gh_data = yaml.safe_load(github_actions)
        except yaml.YAMLError:
            gh_data = {}

        gh_jobs = (
            gh_data.get("jobs", {})
            if isinstance(gh_data, dict) else {}
        )

        global_keys = {
            "stages", "variables", "include", "default",
            "workflow", "image", "services", "before_script",
            "after_script", "cache",
        }

        job_scores: list[dict[str, Any]] = []
        for key, value in gl_data.items():
            if key in global_keys or not isinstance(value, dict):
                continue
            if key.startswith("."):
                continue

            score = self._score_job(key, value, gh_jobs)
            job_scores.append(score)

        overall = (
            sum(j["confidence"] for j in job_scores) / len(job_scores)
            if job_scores else 0.0
        )

        return {
            "jobs": job_scores,
            "overall": round(overall, 2),
            "total_jobs": len(job_scores),
        }

    def _score_job(
        self,
        name: str,
        gl_job: dict[str, Any],
        gh_jobs: dict[str, Any],
    ) -> dict[str, Any]:
        confidence = 0.9
        flags: list[str] = []

        # Check if job exists in GitHub output
        if name not in gh_jobs:
            confidence -= 0.3
            flags.append("job not found in GitHub Actions output")

        # Penalise complex features
        complex_keys = {
            "rules": 0.1, "trigger": 0.15,
            "include": 0.2, "extends": 0.05,
            "parallel": 0.05, "resource_group": 0.05,
        }
        for feature, penalty in complex_keys.items():
            if feature in gl_job:
                confidence -= penalty
                flags.append(f"uses {feature}")

        # Check RAG for similar patterns
        snippet = yaml.dump({name: gl_job}, default_flow_style=False)
        description = yaml_to_text_description(snippet)
        similar = self.store.search(query=description, n_results=1)
        if similar:
            best_sim = 1.0 - similar[0].get("distance", 1.0)
            if best_sim > 0.7:
                confidence += 0.05
            flags.append(
                f"corpus similarity: {round(best_sim, 2)}"
            )
        else:
            confidence -= 0.05
            flags.append("no similar pattern in corpus")

        confidence = max(0.0, min(1.0, confidence))

        return {
            "job": name,
            "confidence": round(confidence, 2),
            "flags": flags,
        }


class SuggestWorkflowSplitTool:
    """Recommend splitting a large pipeline into multiple workflows."""

    # Stage categories that map to separate workflow concerns
    WORKFLOW_CATEGORIES: dict[str, list[str]] = {
        "ci": [
            "build", "compile", "install", "deps",
            "lint", "test", "check", "verify",
        ],
        "deploy": [
            "deploy", "release", "publish", "production",
            "staging", "review",
        ],
        "security": [
            "sast", "dast", "security", "scan",
            "vulnerability", "audit",
        ],
        "pages": ["pages", "docs", "documentation"],
    }

    def __init__(self, store: VectorStore) -> None:
        self.store = store

    def run(self, gitlab_ci: str) -> dict[str, Any]:
        try:
            data = yaml.safe_load(gitlab_ci)
        except yaml.YAMLError:
            return {"should_split": False, "reason": "invalid YAML"}

        if not isinstance(data, dict):
            return {"should_split": False, "reason": "not a mapping"}

        global_keys = {
            "stages", "variables", "include", "default",
            "workflow", "image", "services", "before_script",
            "after_script", "cache",
        }
        jobs = {
            k: v for k, v in data.items()
            if k not in global_keys
            and isinstance(v, dict)
            and not k.startswith(".")
        }

        if len(jobs) <= 4:
            return {
                "should_split": False,
                "reason": f"only {len(jobs)} jobs — single workflow is fine",
                "workflows": [{"name": "ci.yml", "jobs": list(jobs.keys())}],
            }

        # Categorise jobs
        categorised: dict[str, list[str]] = {}
        uncategorised: list[str] = []
        for job_name, job_def in jobs.items():
            stage = job_def.get("stage", "")
            placed = False
            for wf_name, keywords in self.WORKFLOW_CATEGORIES.items():
                if any(
                    kw in job_name.lower() or kw in stage.lower()
                    for kw in keywords
                ):
                    categorised.setdefault(wf_name, []).append(job_name)
                    placed = True
                    break
            if not placed:
                uncategorised.append(job_name)

        # Merge uncategorised into 'ci'
        if uncategorised:
            categorised.setdefault("ci", []).extend(uncategorised)

        # Only suggest split if we get 2+ workflow files
        if len(categorised) < 2:
            return {
                "should_split": False,
                "reason": "all jobs belong to a single category",
                "workflows": [
                    {"name": "ci.yml", "jobs": list(jobs.keys())}
                ],
            }

        workflows = []
        for wf_name, wf_jobs in sorted(categorised.items()):
            workflows.append({
                "name": f"{wf_name}.yml",
                "jobs": wf_jobs,
                "trigger_hint": self._trigger_hint(wf_name),
            })

        return {
            "should_split": True,
            "reason": (
                f"{len(jobs)} jobs across {len(categorised)} categories"
            ),
            "workflows": workflows,
            "total_jobs": len(jobs),
        }

    @staticmethod
    def _trigger_hint(category: str) -> str:
        hints = {
            "ci": "on: [push, pull_request]",
            "deploy": "on: workflow_run (after CI) or workflow_dispatch",
            "security": "on: [pull_request] or schedule",
            "pages": "on: push to main",
        }
        return hints.get(category, "on: [push]")


class RecordFeedbackTool:
    """Record user corrections for future RAG improvement."""

    FEEDBACK_DIR = DATA_DIR / "feedback"

    def run(
        self,
        gitlab_ci: str,
        original_output: str,
        corrected_output: str,
        notes: str = "",
    ) -> dict[str, Any]:
        import datetime
        import hashlib

        self.FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)

        content_hash = hashlib.sha256(
            gitlab_ci.encode()
        ).hexdigest()[:12]
        ts = datetime.datetime.now(
            datetime.timezone.utc
        ).strftime("%Y%m%d_%H%M%S")
        entry_dir = self.FEEDBACK_DIR / f"{ts}_{content_hash}"
        entry_dir.mkdir(parents=True, exist_ok=True)

        (entry_dir / "gitlab-ci.yml").write_text(gitlab_ci)
        (entry_dir / "original.yml").write_text(original_output)
        (entry_dir / "corrected.yml").write_text(corrected_output)

        meta = {
            "timestamp": ts,
            "content_hash": content_hash,
            "notes": notes,
            "patterns": extract_patterns_from_yaml(gitlab_ci),
        }
        (entry_dir / "metadata.json").write_text(
            json.dumps(meta, indent=2)
        )

        return {
            "recorded": True,
            "feedback_id": f"{ts}_{content_hash}",
            "path": str(entry_dir),
        }
