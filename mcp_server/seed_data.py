"""Seed data — curated GitLab CI -> GitHub Actions conversion pairs.

Run this script to populate the data/ directory with initial conversion
examples that give the RAG system ground truth to work from.

Usage:
    python -m mcp_server.seed_data
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
GITLAB_CI_DIR = DATA_DIR / "gitlab_ci"
CONVERSIONS_DIR = DATA_DIR / "conversions"

# ---------------------------------------------------------------------------
# Conversion Pairs: Each dict has a name, gitlab_ci, and github_actions
# ---------------------------------------------------------------------------

CONVERSION_PAIRS: list[dict] = [
    # -----------------------------------------------------------------------
    # 1. Simple Node.js pipeline
    # -----------------------------------------------------------------------
    {
        "name": "node_simple",
        "description": "Simple Node.js CI with install, test, build, deploy stages",
        "gitlab_ci": """\
stages:
  - install
  - test
  - build
  - deploy

variables:
  NODE_VERSION: "20"

install:
  stage: install
  image: node:20
  script:
    - npm ci
  cache:
    key: ${CI_COMMIT_REF_SLUG}
    paths:
      - node_modules/

test:
  stage: test
  image: node:20
  script:
    - npm test
  artifacts:
    reports:
      junit: test-results.xml

build:
  stage: build
  image: node:20
  script:
    - npm run build
  artifacts:
    paths:
      - dist/
    expire_in: 1 week

deploy:
  stage: deploy
  image: node:20
  script:
    - npm run deploy
  environment:
    name: production
  only:
    - main
""",
        "github_actions": {
            "ci.yml": """\
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  NODE_VERSION: "20"

jobs:
  install:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
      - uses: actions/cache@v4
        with:
          path: node_modules/
          key: ${{ github.ref_name }}-${{ hashFiles('package-lock.json') }}
      - run: npm ci

  test:
    needs: [install]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
      - run: npm ci
      - run: npm test
      - uses: dorny/test-reporter@v1
        if: always()
        with:
          name: Test Results
          path: test-results.xml
          reporter: java-junit

  build:
    needs: [test]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
      - run: npm ci
      - run: npm run build
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
          retention-days: 7

  deploy:
    needs: [build]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
      - run: npm ci
      - run: npm run deploy
"""
        },
    },
    # -----------------------------------------------------------------------
    # 2. Python with services, matrix, and extends
    # -----------------------------------------------------------------------
    {
        "name": "python_complex",
        "description": (
            "Python CI with services (postgres, redis),"
            " matrix builds, extends, Docker,"
            " SAST, environments"
        ),
        "gitlab_ci": """\
stages:
  - build
  - test
  - security
  - staging
  - production

variables:
  DOCKER_HOST: tcp://docker:2376
  DOCKER_TLS_CERTDIR: "/certs"

.python_base:
  image: python:3.12
  before_script:
    - pip install -r requirements.txt
  cache:
    key:
      files:
        - requirements.txt
    paths:
      - .cache/pip

build:
  extends: .python_base
  stage: build
  script:
    - python -m build
  artifacts:
    paths:
      - dist/
    expire_in: 30 days

test:
  extends: .python_base
  stage: test
  services:
    - name: postgres:16
      alias: db
    - name: redis:7
      alias: cache
  variables:
    DATABASE_URL: postgresql://postgres:postgres@db:5432/testdb
    REDIS_URL: redis://cache:6379
  parallel:
    matrix:
      - PYTHON_VERSION: ["3.10", "3.11", "3.12"]
  script:
    - pytest -v --junitxml=report.xml --cov=src
  artifacts:
    reports:
      junit: report.xml

sast:
  stage: security
  image: python:3.12
  script:
    - pip install bandit safety
    - bandit -r src/ -f json -o bandit-report.json
    - safety check --json --output safety-report.json
  artifacts:
    paths:
      - bandit-report.json
      - safety-report.json
  allow_failure: true
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH

build_docker:
  stage: build
  image: docker:24
  services:
    - docker:24-dind
  script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    - docker build -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA .
    - docker push $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
  only:
    - main
    - tags

deploy_staging:
  stage: staging
  script:
    - echo "Deploying to staging..."
  environment:
    name: staging
    url: https://staging.example.com
  rules:
    - if: $CI_COMMIT_BRANCH == "develop"

deploy_production:
  stage: production
  script:
    - echo "Deploying to production..."
  environment:
    name: production
    url: https://example.com
  when: manual
  only:
    - main
""",
        "github_actions": {
            "ci.yml": """\
name: CI
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  workflow_dispatch: {}

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: actions/cache@v4
        with:
          path: .cache/pip
          key: pip-${{ hashFiles('requirements.txt') }}
      - run: pip install -r requirements.txt
      - run: python -m build
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
          retention-days: 30

  test:
    needs: [build]
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    services:
      db:
        image: postgres:16
        env:
          POSTGRES_DB: testdb
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      cache:
        image: redis:7
        ports:
          - 6379:6379
    env:
      DATABASE_URL: postgresql://postgres:postgres@localhost:5432/testdb
      REDIS_URL: redis://localhost:6379
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - uses: actions/cache@v4
        with:
          path: .cache/pip
          key: pip-${{ hashFiles('requirements.txt') }}
      - run: pip install -r requirements.txt
      - run: pytest -v --junitxml=report.xml --cov=src
      - uses: dorny/test-reporter@v1
        if: always()
        with:
          name: Test Results (Python ${{ matrix.python-version }})
          path: report.xml
          reporter: java-junit

  sast:
    needs: [build]
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request' || github.ref == format('refs/heads/{0}', github.event.repository.default_branch)  # noqa: E501
        with:
          python-version: "3.12"
      - run: pip install bandit safety
      - run: bandit -r src/ -f json -o bandit-report.json
      - run: safety check --json --output safety-report.json
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: security-reports
          path: |
            bandit-report.json
            safety-report.json

  build_docker:
    needs: [build]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/')
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          push: true
          tags: ghcr.io/${{ github.repository }}:${{ github.sha }}

  deploy_staging:
    needs: [test, sast]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/develop'
    environment:
      name: staging
      url: https://staging.example.com
    steps:
      - uses: actions/checkout@v4
      - run: echo "Deploying to staging..."

  deploy_production:
    needs: [test, sast, build_docker]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    environment:
      name: production
      url: https://example.com
    steps:
      - uses: actions/checkout@v4
      - run: echo "Deploying to production..."
"""
        },
    },
    # -----------------------------------------------------------------------
    # 3. Docker build with multi-stage and registry push
    # -----------------------------------------------------------------------
    {
        "name": "docker_registry",
        "description": "Docker build with DIND, registry login, multi-tag push",
        "gitlab_ci": """\
stages:
  - build
  - push

variables:
  DOCKER_HOST: tcp://docker:2376
  DOCKER_TLS_CERTDIR: "/certs"
  IMAGE_TAG: $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA

build:
  stage: build
  image: docker:24
  services:
    - docker:24-dind
  script:
    - docker build --pull -t $IMAGE_TAG .
    - docker tag $IMAGE_TAG $CI_REGISTRY_IMAGE:latest
  rules:
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
    - if: $CI_COMMIT_TAG

push:
  stage: push
  image: docker:24
  services:
    - docker:24-dind
  script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    - docker push $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
    - docker push $CI_REGISTRY_IMAGE:latest
  rules:
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
""",
        "github_actions": {
            "docker.yml": """\
name: Docker Build & Push
on:
  push:
    branches: [main]
    tags: ["v*"]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-buildx-action@v3

      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=sha
            type=raw,value=latest,enable={{is_default_branch}}

      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
"""
        },
    },
    # -----------------------------------------------------------------------
    # 4. Rules with changes (path filtering)
    # -----------------------------------------------------------------------
    {
        "name": "rules_changes",
        "description": "Rules with changes/paths filtering and multiple conditions",
        "gitlab_ci": """\
stages:
  - lint
  - test

lint:frontend:
  stage: lint
  image: node:20
  script:
    - npm ci
    - npm run lint
  rules:
    - changes:
        paths:
          - "src/frontend/**"
          - "package.json"
          - "package-lock.json"

lint:backend:
  stage: lint
  image: python:3.12
  script:
    - pip install ruff
    - ruff check src/
  rules:
    - changes:
        paths:
          - "src/backend/**"
          - "requirements.txt"

test:
  stage: test
  image: python:3.12
  script:
    - pytest
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
      changes:
        paths:
          - "src/**"
          - "tests/**"
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
""",
        "github_actions": {
            "lint.yml": """\
name: Lint
on:
  push:
    paths:
      - 'src/**'
      - 'package.json'
      - 'package-lock.json'
      - 'requirements.txt'
  pull_request:
    paths:
      - 'src/**'
      - 'package.json'
      - 'package-lock.json'
      - 'requirements.txt'

jobs:
  lint-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm ci
      - run: npm run lint

  lint-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff
      - run: ruff check src/

  test:
    needs: [lint-frontend, lint-backend]
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request' || github.ref == format('refs/heads/{0}', github.event.repository.default_branch)  # noqa: E501
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: pytest
"""
        },
    },
    # -----------------------------------------------------------------------
    # 5. Cache with multiple policies
    # -----------------------------------------------------------------------
    {
        "name": "cache_policies",
        "description": "Advanced caching with pull/push policies and fallback keys",
        "gitlab_ci": """\
stages:
  - deps
  - build
  - test

install_deps:
  stage: deps
  image: node:20
  script:
    - npm ci
  cache:
    key:
      files:
        - package-lock.json
      prefix: $CI_COMMIT_REF_SLUG
    paths:
      - node_modules/
    policy: push

build:
  stage: build
  image: node:20
  script:
    - npm run build
  cache:
    key:
      files:
        - package-lock.json
      prefix: $CI_COMMIT_REF_SLUG
    paths:
      - node_modules/
    policy: pull
  artifacts:
    paths:
      - dist/

test:
  stage: test
  image: node:20
  script:
    - npm test
  cache:
    key:
      files:
        - package-lock.json
      prefix: $CI_COMMIT_REF_SLUG
    paths:
      - node_modules/
    policy: pull
    fallback_keys:
      - main-node-modules
""",
        "github_actions": {
            "ci.yml": """\
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  install_deps:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - uses: actions/cache/save@v4
        with:
          path: node_modules/
          key: ${{ github.ref_name }}-${{ hashFiles('package-lock.json') }}
      - run: npm ci

  build:
    needs: [install_deps]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - uses: actions/cache/restore@v4
        with:
          path: node_modules/
          key: ${{ github.ref_name }}-${{ hashFiles('package-lock.json') }}
      - run: npm run build
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/

  test:
    needs: [install_deps]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - uses: actions/cache/restore@v4
        with:
          path: node_modules/
          key: ${{ github.ref_name }}-${{ hashFiles('package-lock.json') }}
          restore-keys: |
            main-node-modules
      - run: npm test
"""
        },
    },
    # -----------------------------------------------------------------------
    # 6. Multi-project / trigger pipeline
    # -----------------------------------------------------------------------
    {
        "name": "trigger_pipeline",
        "description": "Multi-project trigger and downstream pipeline",
        "gitlab_ci": """\
stages:
  - build
  - trigger

build:
  stage: build
  script:
    - make build

trigger_deploy:
  stage: trigger
  trigger:
    project: team/deploy-service
    branch: main
    strategy: depend
  rules:
    - if: $CI_COMMIT_BRANCH == "main"

trigger_docs:
  stage: trigger
  trigger:
    include: docs/.gitlab-ci.yml
    strategy: depend
""",
        "github_actions": {
            "ci.yml": """\
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make build

  trigger_deploy:
    needs: [build]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - name: Trigger deploy service workflow
        uses: actions/github-script@v7
        with:
          github-token: ${{ secrets.DEPLOY_TOKEN }}
          script: |
            await github.rest.actions.createWorkflowDispatch({
              owner: 'team',
              repo: 'deploy-service',
              workflow_id: 'deploy.yml',
              ref: 'main',
            });

  trigger_docs:
    needs: [build]
    uses: ./.github/workflows/docs.yml
    # NOTE: Child pipeline (include:) maps to reusable workflow (workflow_call)
"""
        },
    },
    # -----------------------------------------------------------------------
    # 7. GitLab Pages
    # -----------------------------------------------------------------------
    {
        "name": "pages",
        "description": "GitLab Pages deployment",
        "gitlab_ci": """\
stages:
  - build
  - deploy

build_site:
  stage: build
  image: node:20
  script:
    - npm ci
    - npm run build
  artifacts:
    paths:
      - public/

pages:
  stage: deploy
  script:
    - echo "Deploying to GitLab Pages"
  artifacts:
    paths:
      - public/
  only:
    - main
""",
        "github_actions": {
            "pages.yml": """\
name: Deploy to GitHub Pages
on:
  push:
    branches: [main]

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm ci
      - run: npm run build
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: public/

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
"""
        },
    },
    # -----------------------------------------------------------------------
    # 8. Include with templates
    # -----------------------------------------------------------------------
    {
        "name": "include_templates",
        "description": "Include remote and local templates with extends",
        "gitlab_ci": """\
include:
  - local: '/ci/base.yml'
  - project: 'shared-group/ci-templates'
    file: '/templates/security.yml'
    ref: v2.0
  - template: 'Auto-DevOps.gitlab-ci.yml'

stages:
  - build
  - test
  - deploy

build:
  extends: .build_template
  stage: build
  script:
    - make build

test:
  extends: .test_template
  stage: test
  script:
    - make test
""",
        "github_actions": {
            "ci.yml": """\
# NOTE: GitLab 'include' with templates has no direct equivalent.
# Options:
#   1. Inline the template content into this workflow
#   2. Use reusable workflows (workflow_call) for shared logic
#   3. Use composite actions for shared step sequences
#
# include:local -> inline or local reusable workflow
# include:project -> uses: org/repo/.github/workflows/file.yml@ref
# include:template -> use equivalent starter workflow or action

name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  build:
    # If shared-group/ci-templates has a reusable workflow:
    # uses: shared-group/ci-templates/.github/workflows/security.yml@v2.0
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make build

  test:
    needs: [build]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make test

  # Security scanning (was: include:template Auto-DevOps)
  security:
    needs: [build]
    uses: shared-group/ci-templates/.github/workflows/security.yml@v2.0
"""
        },
    },
    # -----------------------------------------------------------------------
    # 9. Parallel matrix with allow_failure
    # -----------------------------------------------------------------------
    {
        "name": "parallel_matrix",
        "description": "Parallel matrix builds with multiple variables and allow_failure",
        "gitlab_ci": """\
stages:
  - test

test:
  stage: test
  image: $IMAGE
  parallel:
    matrix:
      - IMAGE: ["python:3.10", "python:3.11", "python:3.12"]
        DB: ["postgres", "mysql"]
      - IMAGE: ["python:3.12"]
        DB: ["sqlite"]
  services:
    - name: ${DB}:latest
  script:
    - pip install -r requirements.txt
    - pytest -v
  allow_failure:
    exit_codes: [137]
""",
        "github_actions": {
            "test.yml": """\
name: Test Matrix
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        include:
          - python-version: "3.10"
            db: postgres
          - python-version: "3.10"
            db: mysql
          - python-version: "3.11"
            db: postgres
          - python-version: "3.11"
            db: mysql
          - python-version: "3.12"
            db: postgres
          - python-version: "3.12"
            db: mysql
          - python-version: "3.12"
            db: sqlite
    services:
      db:
        image: ${{ matrix.db }}:latest
        ports:
          - 5432:5432
          - 3306:3306
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -r requirements.txt
      - run: pytest -v
        # NOTE: allow_failure with exit_codes has no direct equivalent.
        # Using continue-on-error as a rough approximation.
        continue-on-error: true
"""
        },
    },
    # -----------------------------------------------------------------------
    # 10. Environment with approvals and resource_group
    # -----------------------------------------------------------------------
    {
        "name": "environments_advanced",
        "description": "Environments with protection rules, resource_group, and auto_stop_in",
        "gitlab_ci": """\
stages:
  - deploy
  - cleanup

deploy_review:
  stage: deploy
  script:
    - deploy_to_review_app $CI_COMMIT_REF_SLUG
  environment:
    name: review/$CI_COMMIT_REF_SLUG
    url: https://$CI_COMMIT_REF_SLUG.review.example.com
    on_stop: stop_review
    auto_stop_in: 2 days
  resource_group: review/$CI_COMMIT_REF_SLUG
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"

stop_review:
  stage: cleanup
  script:
    - teardown_review_app $CI_COMMIT_REF_SLUG
  environment:
    name: review/$CI_COMMIT_REF_SLUG
    action: stop
  when: manual
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
      when: manual
""",
        "github_actions": {
            "review.yml": """\
name: Review App
on:
  pull_request:
    types: [opened, synchronize, reopened, closed]

concurrency:
  group: review-${{ github.head_ref }}
  cancel-in-progress: false

jobs:
  deploy_review:
    if: github.event.action != 'closed'
    runs-on: ubuntu-latest
    environment:
      name: review/${{ github.head_ref }}
      url: https://${{ github.head_ref }}.review.example.com
    steps:
      - uses: actions/checkout@v4
      - run: deploy_to_review_app ${{ github.head_ref }}

  # NOTE: auto_stop_in has no direct equivalent.
  # Use a scheduled workflow or GitHub API to clean up stale environments.
  stop_review:
    if: github.event.action == 'closed'
    runs-on: ubuntu-latest
    environment:
      name: review/${{ github.head_ref }}
    steps:
      - uses: actions/checkout@v4
      - run: teardown_review_app ${{ github.head_ref }}
"""
        },
    },
]

# ---------------------------------------------------------------------------
# Standalone GitLab CI files (no conversion pair, just patterns to learn from)
# ---------------------------------------------------------------------------

STANDALONE_GITLAB_CI: list[dict] = [
    {
        "name": "go_microservice",
        "content": """\
stages:
  - build
  - test
  - deploy

variables:
  GOPATH: $CI_PROJECT_DIR/.go
  CGO_ENABLED: "0"

.go_base:
  image: golang:1.22
  before_script:
    - mkdir -p .go
  cache:
    key: ${CI_COMMIT_REF_SLUG}
    paths:
      - .go/pkg/mod/

build:
  extends: .go_base
  stage: build
  script:
    - go build -o bin/app ./cmd/server
  artifacts:
    paths:
      - bin/

test:
  extends: .go_base
  stage: test
  services:
    - name: postgres:16
      alias: db
  variables:
    DB_HOST: db
  script:
    - go test -race -coverprofile=coverage.out ./...
  artifacts:
    reports:
      junit: report.xml
  coverage: '/coverage: \\d+\\.\\d+% of statements/'
""",
    },
    {
        "name": "monorepo_include",
        "content": """\
include:
  - local: '/apps/frontend/.gitlab-ci.yml'
  - local: '/apps/backend/.gitlab-ci.yml'
  - local: '/libs/shared/.gitlab-ci.yml'
  - project: 'platform/ci-templates'
    file: '/templates/deploy.yml'
    ref: v3.0

stages:
  - build
  - test
  - deploy

variables:
  DEPLOY_ENV: staging

workflow:
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_TAG
""",
    },
    {
        "name": "auto_devops_override",
        "content": """\
include:
  - template: Auto-DevOps.gitlab-ci.yml

variables:
  AUTO_DEVOPS_BUILD_IMAGE_EXTRA_ARGS: "--build-arg NODE_ENV=production"
  POSTGRES_ENABLED: "true"
  TEST_DISABLED: "false"
  CODE_QUALITY_DISABLED: "true"
  REVIEW_DISABLED: "false"
  DAST_DISABLED: "true"

test:
  variables:
    DATABASE_URL: postgresql://postgres:postgres@postgres:5432/$POSTGRES_DB
  services:
    - name: postgres:15
      alias: postgres
""",
    },
]


def seed() -> None:
    """Write all seed data to disk."""
    GITLAB_CI_DIR.mkdir(parents=True, exist_ok=True)
    CONVERSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Write conversion pairs
    for pair in CONVERSION_PAIRS:
        name = pair["name"]
        pair_dir = CONVERSIONS_DIR / name
        pair_dir.mkdir(parents=True, exist_ok=True)

        (pair_dir / "gitlab-ci.yml").write_text(pair["gitlab_ci"])

        for wf_name, wf_content in pair["github_actions"].items():
            (pair_dir / wf_name).write_text(wf_content)

        metadata = {
            "name": name,
            "description": pair["description"],
            "workflows": list(pair["github_actions"].keys()),
        }
        (pair_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    # Write standalone GitLab CI files
    for entry in STANDALONE_GITLAB_CI:
        out_path = GITLAB_CI_DIR / f"{entry['name']}.yml"
        out_path.write_text(entry["content"])

    # Also copy project example files
    project_examples = Path(__file__).parent.parent / "examples"
    if project_examples.exists():
        for example in project_examples.glob("*.yml"):
            dest = GITLAB_CI_DIR / f"example_{example.stem}.yml"
            dest.write_text(example.read_text())

    print(f"Seeded {len(CONVERSION_PAIRS)} conversion pairs")
    print(f"Seeded {len(STANDALONE_GITLAB_CI)} standalone GitLab CI files")
    print(f"Data directory: {DATA_DIR}")


if __name__ == "__main__":
    seed()
