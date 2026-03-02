"""gl2gh — GitLab CI/CD to GitHub Actions migration tool."""

from gl2gh.parser import GitLabCIParser
from gl2gh.converter import GitLabToGitHubConverter
from gl2gh.models import ConversionResult, GitLabPipeline

__version__ = "1.0.0"
__all__ = [
    "GitLabCIParser",
    "GitLabToGitHubConverter",
    "ConversionResult",
    "GitLabPipeline",
]
