"""Vercel serverless function for /api/convert endpoint."""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

# Add src/ to path so gl2gh can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gl2gh.converter import GitLabToGitHubConverter
from gl2gh.parser import GitLabCIParser

MAX_PAYLOAD_BYTES = 1_024_000  # 1 MB


class handler(BaseHTTPRequestHandler):
    """Vercel Python handler for GitLab CI → GitHub Actions conversion."""

    def _set_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, data: dict, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self.send_response(204)
        self._set_cors_headers()
        self.end_headers()

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > MAX_PAYLOAD_BYTES:
            self._send_json({"success": False, "errors": ["Payload too large."]}, 413)
            return

        body = self.rfile.read(content_length)
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            self._send_json({"success": False, "errors": ["Invalid JSON."]}, 400)
            return

        content: str = (data.get("content") or "").strip()
        if not content:
            self._send_json(
                {"success": False, "errors": ["No YAML content provided."]}, 400
            )
            return

        try:
            parser = GitLabCIParser()
            pipeline = parser.parse_string(content)

            conv = GitLabToGitHubConverter(
                workflow_name="CI",
                source_file=".gitlab-ci.yml",
            )
            result = conv.convert(pipeline)

            if result.success:
                self._send_json(
                    {
                        "success": True,
                        "workflow": next(
                            iter(result.output_workflows.values()), ""
                        ),
                        "workflows": result.output_workflows,
                        "warnings": result.warnings,
                        "notes": result.conversion_notes,
                    }
                )
            else:
                self._send_json(
                    {
                        "success": False,
                        "errors": result.errors,
                        "warnings": result.warnings,
                    }
                )

        except Exception as exc:  # noqa: BLE001
            self._send_json({"success": False, "errors": [str(exc)]}, 500)
