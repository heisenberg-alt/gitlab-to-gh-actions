"""GitLab CI file indexer — crawls public GitLab repos for .gitlab-ci.yml files.

Two indexing modes:
  1. GitLab API: Search public projects on gitlab.com for CI configs
  2. GitHub API: Find repos that migrated from GitLab (have both .gitlab-ci.yml remnants
     and .github/workflows/)

Indexed files are stored locally in data/gitlab_ci/ as YAML and in the vector store.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote_plus

import requests
import yaml

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
GITLAB_CI_DIR = DATA_DIR / "gitlab_ci"
CONVERSIONS_DIR = DATA_DIR / "conversions"
INDEX_FILE = DATA_DIR / "index.json"

GITLAB_API = "https://gitlab.com/api/v4"
GITHUB_API = "https://api.github.com"


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _load_index() -> dict[str, Any]:
    if INDEX_FILE.exists():
        return json.loads(INDEX_FILE.read_text())
    return {"files": [], "total": 0, "last_updated": None}


def _save_index(index: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(index, indent=2))


class GitLabCIIndexer:
    """Crawl and index GitLab CI configuration files from public repositories."""

    def __init__(
        self,
        gitlab_token: Optional[str] = None,
        github_token: Optional[str] = None,
        rate_limit_delay: float = 1.0,
    ) -> None:
        self.gitlab_token = gitlab_token or os.environ.get("GITLAB_TOKEN", "")
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN", "")
        self.rate_limit_delay = rate_limit_delay
        self.index = _load_index()

        GITLAB_CI_DIR.mkdir(parents=True, exist_ok=True)
        CONVERSIONS_DIR.mkdir(parents=True, exist_ok=True)

    def _gitlab_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.gitlab_token:
            headers["PRIVATE-TOKEN"] = self.gitlab_token
        return headers

    def _github_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers

    def crawl_gitlab_projects(
        self,
        min_stars: int = 50,
        max_pages: int = 10,
        per_page: int = 20,
        topics: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Fetch .gitlab-ci.yml from popular public GitLab projects."""
        collected: list[dict[str, Any]] = []
        params: dict[str, Any] = {
            "visibility": "public",
            "order_by": "star_count",
            "sort": "desc",
            "min_access_level": 0,
            "per_page": per_page,
            "with_programming_language": "",
        }
        if topics:
            params["topic"] = ",".join(topics)

        for page in range(1, max_pages + 1):
            params["page"] = page
            try:
                resp = requests.get(
                    f"{GITLAB_API}/projects",
                    headers=self._gitlab_headers(),
                    params=params,
                    timeout=30,
                )
                resp.raise_for_status()
                projects = resp.json()
            except requests.RequestException as e:
                logger.warning("GitLab API request failed (page %d): %s", page, e)
                break

            if not projects:
                break

            for project in projects:
                star_count = project.get("star_count", 0)
                if star_count < min_stars:
                    continue
                ci_file = self._fetch_gitlab_ci_file(project)
                if ci_file:
                    collected.append(ci_file)

            time.sleep(self.rate_limit_delay)

        logger.info("Crawled %d GitLab CI files", len(collected))
        return collected

    def _fetch_gitlab_ci_file(self, project: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Fetch the .gitlab-ci.yml content for a single GitLab project."""
        pid = project["id"]
        name = project.get("path_with_namespace", f"project-{pid}")
        default_branch = project.get("default_branch", "main")

        file_path = quote_plus(".gitlab-ci.yml")
        url = f"{GITLAB_API}/projects/{pid}/repository/files/{file_path}/raw"
        params = {"ref": default_branch}

        try:
            resp = requests.get(
                url, headers=self._gitlab_headers(), params=params, timeout=15
            )
            if resp.status_code != 200:
                return None
            content = resp.text
        except requests.RequestException:
            return None

        # Validate it's actual YAML
        try:
            yaml.safe_load(content)
        except yaml.YAMLError:
            return None

        content_hash = _sha256(content)
        entry = {
            "source": "gitlab",
            "project": name,
            "stars": project.get("star_count", 0),
            "url": project.get("web_url", ""),
            "branch": default_branch,
            "content_hash": content_hash,
            "filename": f"gitlab_{content_hash}.yml",
            "topics": project.get("topics", []),
            "language": project.get("predominant_language", ""),
        }

        # Save to disk
        out_path = GITLAB_CI_DIR / entry["filename"]
        out_path.write_text(content)

        # Update index
        existing_hashes = {f["content_hash"] for f in self.index["files"]}
        if content_hash not in existing_hashes:
            self.index["files"].append(entry)
            self.index["total"] = len(self.index["files"])

        time.sleep(self.rate_limit_delay)
        return entry

    def crawl_github_migrated_repos(
        self,
        query: str = "github actions migration gitlab",
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """Search GitHub for repos that migrated from GitLab (have both configs).

        Looks for repos containing .gitlab-ci.yml that also have
        .github/workflows/ — these are likely migration candidates with
        before/after pairs.
        """
        collected: list[dict[str, Any]] = []
        params = {
            "q": f"filename:.gitlab-ci.yml {query}",
            "per_page": min(max_results, 30),
        }

        try:
            resp = requests.get(
                f"{GITHUB_API}/search/code",
                headers=self._github_headers(),
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            results = resp.json().get("items", [])
        except requests.RequestException as e:
            logger.warning("GitHub search failed: %s", e)
            return []

        for item in results[:max_results]:
            repo = item.get("repository", {})
            full_name = repo.get("full_name", "")
            if not full_name:
                continue

            pair = self._fetch_github_conversion_pair(full_name)
            if pair:
                collected.append(pair)
            time.sleep(self.rate_limit_delay)

        logger.info("Found %d conversion pairs from GitHub", len(collected))
        return collected

    def _fetch_github_conversion_pair(
        self, repo_full_name: str
    ) -> Optional[dict[str, Any]]:
        """Try to fetch both .gitlab-ci.yml and .github/workflows/*.yml from a repo."""
        headers = self._github_headers()

        # Fetch .gitlab-ci.yml
        try:
            gl_resp = requests.get(
                f"{GITHUB_API}/repos/{repo_full_name}/contents/.gitlab-ci.yml",
                headers=headers,
                timeout=15,
            )
            if gl_resp.status_code != 200:
                return None
            gl_data = gl_resp.json()
            # Content is base64-encoded
            import base64

            gl_content = base64.b64decode(gl_data.get("content", "")).decode("utf-8")
        except (requests.RequestException, Exception):
            return None

        # Validate YAML
        try:
            yaml.safe_load(gl_content)
        except yaml.YAMLError:
            return None

        # Fetch GitHub Actions workflows
        try:
            wf_resp = requests.get(
                f"{GITHUB_API}/repos/{repo_full_name}/contents/.github/workflows",
                headers=headers,
                timeout=15,
            )
            if wf_resp.status_code != 200:
                return None
            wf_files = wf_resp.json()
        except requests.RequestException:
            return None

        gh_workflows: dict[str, str] = {}
        for wf in wf_files:
            if not wf.get("name", "").endswith((".yml", ".yaml")):
                continue
            try:
                import base64

                wf_detail = requests.get(
                    wf["url"], headers=headers, timeout=15
                ).json()
                wf_content = base64.b64decode(
                    wf_detail.get("content", "")
                ).decode("utf-8")
                gh_workflows[wf["name"]] = wf_content
            except Exception:
                continue
            time.sleep(self.rate_limit_delay * 0.5)

        if not gh_workflows:
            return None

        content_hash = _sha256(gl_content)
        pair = {
            "source": "github_migration",
            "repo": repo_full_name,
            "gitlab_ci": gl_content,
            "github_workflows": gh_workflows,
            "content_hash": content_hash,
        }

        # Save conversion pair
        pair_dir = CONVERSIONS_DIR / content_hash
        pair_dir.mkdir(parents=True, exist_ok=True)
        (pair_dir / "gitlab-ci.yml").write_text(gl_content)
        for wf_name, wf_content in gh_workflows.items():
            (pair_dir / wf_name).write_text(wf_content)
        (pair_dir / "metadata.json").write_text(
            json.dumps({"repo": repo_full_name, "workflows": list(gh_workflows.keys())})
        )

        return pair

    def index_local_files(self, directory: str | Path) -> list[dict[str, Any]]:
        """Index .gitlab-ci.yml files from a local directory."""
        directory = Path(directory)
        collected: list[dict[str, Any]] = []

        for yml_path in directory.rglob("*.gitlab-ci.yml"):
            content = yml_path.read_text()
            try:
                yaml.safe_load(content)
            except yaml.YAMLError:
                continue

            content_hash = _sha256(content)
            entry = {
                "source": "local",
                "path": str(yml_path),
                "content_hash": content_hash,
                "filename": f"local_{content_hash}.yml",
            }

            out_path = GITLAB_CI_DIR / entry["filename"]
            out_path.write_text(content)

            existing_hashes = {f["content_hash"] for f in self.index["files"]}
            if content_hash not in existing_hashes:
                self.index["files"].append(entry)
                self.index["total"] = len(self.index["files"])
            collected.append(entry)

        return collected

    def save_index(self) -> None:
        """Persist the index to disk."""
        import datetime

        self.index["last_updated"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()
        _save_index(self.index)
        logger.info("Index saved: %d files", self.index["total"])
