"""
Simple Flask web server for the gl2gh converter UI.

Usage:
    pip install flask
    python website/app.py

Then open http://localhost:5000 in your browser.
"""

from __future__ import annotations

import os
import sys

# Ensure the src/ directory is on the path so gl2gh can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from flask import Flask, jsonify, request, send_from_directory

from gl2gh.converter import GitLabToGitHubConverter
from gl2gh.parser import GitLabCIParser

MAX_PAYLOAD_BYTES = 1_024_000  # 1 MB

app = Flask(__name__, static_folder=os.path.dirname(__file__))


@app.route("/")
def index() -> object:
    return send_from_directory(os.path.dirname(__file__), "index.html")


@app.route("/converter")
def converter() -> object:
    return send_from_directory(os.path.dirname(__file__), "converter.html")


@app.route("/api/convert", methods=["POST"])
def convert() -> object:
    if request.content_length and request.content_length > MAX_PAYLOAD_BYTES:
        return jsonify({"success": False, "errors": ["Payload too large."]}), 413

    data = request.get_json(silent=True)
    if not data or "content" not in data:
        return jsonify({"success": False, "errors": ["No YAML content provided."]}), 400

    content: str = data["content"]
    if not content.strip():
        return jsonify({"success": False, "errors": ["YAML content is empty."]}), 400

    try:
        parser = GitLabCIParser()
        pipeline = parser.parse_string(content)

        conv = GitLabToGitHubConverter(
            workflow_name="CI",
            source_file=".gitlab-ci.yml",
        )
        result = conv.convert(pipeline)

        if result.success:
            return jsonify(
                {
                    "success": True,
                    "workflow": next(iter(result.output_workflows.values()), ""),
                    "workflows": result.output_workflows,
                    "warnings": result.warnings,
                    "notes": result.conversion_notes,
                }
            )
        else:
            return jsonify(
                {
                    "success": False,
                    "errors": result.errors,
                    "warnings": result.warnings,
                }
            )

    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "errors": [str(exc)]}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"gl2gh converter UI running at http://localhost:{port}/converter")
    app.run(debug=True, port=port)
