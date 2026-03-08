"""Tests for the Flask web API."""

import json
import os
import sys

import pytest

# Ensure the src/ directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from website.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


SIMPLE_GITLAB = """\
stages:
  - build

build:
  stage: build
  image: node:18
  script:
    - npm ci
    - npm run build
"""


class TestConvertEndpoint:
    def test_convert_success(self, client):
        resp = client.post(
            "/api/convert",
            data=json.dumps({"content": SIMPLE_GITLAB}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "workflow" in data
        assert "actions/checkout@v4" in data["workflow"]

    def test_convert_returns_all_workflows(self, client):
        """Trigger pipelines should return child workflows in the response."""
        gitlab_with_trigger = """\
stages:
  - build
  - deploy

build:
  stage: build
  script:
    - echo build

deploy_child:
  stage: deploy
  trigger:
    include: ci/deploy.yml
"""
        resp = client.post(
            "/api/convert",
            data=json.dumps({"content": gitlab_with_trigger}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "workflows" in data
        assert len(data["workflows"]) >= 2

    def test_convert_no_content(self, client):
        resp = client.post(
            "/api/convert",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_convert_empty_content(self, client):
        resp = client.post(
            "/api/convert",
            data=json.dumps({"content": "   "}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_convert_invalid_yaml(self, client):
        resp = client.post(
            "/api/convert",
            data=json.dumps({"content": "not: [valid: yaml: {{"}),
            content_type="application/json",
        )
        # Should return 500 or a success=False response
        data = resp.get_json()
        assert data["success"] is False

    def test_convert_no_json_body(self, client):
        resp = client.post("/api/convert", data="plain text")
        assert resp.status_code == 400

    def test_payload_too_large(self, client):
        huge = "a" * 2_000_000
        resp = client.post(
            "/api/convert",
            data=json.dumps({"content": huge}),
            content_type="application/json",
        )
        assert resp.status_code == 413
