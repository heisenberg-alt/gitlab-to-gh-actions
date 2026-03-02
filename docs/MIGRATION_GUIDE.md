# Migration Guide: GitLab CI/CD to GitHub Actions

This guide provides a comprehensive reference for migrating GitLab CI/CD pipelines to GitHub Actions using `gl2gh`. It covers concept mapping, variable translation, step-by-step migration instructions, common patterns with before/after examples, and troubleshooting.

---

## Table of Contents

1. [Concept Mapping](#concept-mapping)
2. [Variable Translation Reference](#variable-translation-reference)
3. [Step-by-Step Migration Process](#step-by-step-migration-process)
4. [Common Patterns](#common-patterns)
   - [Stages and Job Dependencies](#stages-and-job-dependencies)
   - [Docker Builds](#docker-builds)
   - [Matrix Builds](#matrix-builds)
   - [Caching](#caching)
   - [Artifacts](#artifacts)
   - [Services](#services)
   - [Environments and Deployments](#environments-and-deployments)
   - [Rules and Conditional Execution](#rules-and-conditional-execution)
   - [Templates and Extends](#templates-and-extends)
   - [Manual Jobs](#manual-jobs)
5. [Troubleshooting Common Issues](#troubleshooting-common-issues)

---

## Concept Mapping

The following table maps core GitLab CI/CD concepts to their GitHub Actions equivalents:

| GitLab CI/CD | GitHub Actions | Notes |
|---|---|---|
| `.gitlab-ci.yml` | `.github/workflows/*.yml` | GitHub supports multiple workflow files |
| `stages` (sequential ordering) | `needs` (explicit dependency graph) | gl2gh converts stage order to `needs` automatically |
| `image` | `container.image` | Used with `runs-on: ubuntu-latest` |
| `services` | `services` | Same concept, slightly different syntax |
| `variables` | `env` | At workflow, job, or step level |
| `cache` | `actions/cache@v4` | Converted to a dedicated step |
| `artifacts.paths` | `actions/upload-artifact@v4` | Converted to a dedicated step |
| `artifacts.reports.junit` | `dorny/test-reporter@v1` | Third-party action for test reports |
| `rules` | `if` conditions on jobs | Variable names are translated |
| `only` / `except` | `on` trigger filters | Branch/tag patterns in trigger config |
| `parallel.matrix` | `strategy.matrix` | Direct equivalent |
| `environment` | `environment` | Create environments in repo settings |
| `allow_failure` | `continue-on-error` | Direct equivalent |
| `timeout` | `timeout-minutes` | Converted from string to integer minutes |
| `when: manual` | `workflow_dispatch` trigger | Or environment protection rules |
| `when: always` | `if: always()` | GitHub Actions status function |
| `when: on_failure` | `if: failure()` | GitHub Actions status function |
| `extends` / `.template` | Resolved and flattened | No direct equivalent; gl2gh inlines templates |
| `before_script` | Separate step before main script | Named "Before script" |
| `after_script` | Separate step with `if: always()` | Named "After script" |
| `include` | Reusable workflows / composite actions | Requires manual conversion |
| `trigger` (multi-project) | `workflow_dispatch` + repository dispatch | Requires manual review |
| `retry` | No direct built-in equivalent | Consider third-party retry actions |
| `resource_group` | `concurrency` groups | Similar purpose, different syntax |
| `interruptible` | `concurrency.cancel-in-progress` | Workflow-level setting |
| `tags` (runner selection) | `runs-on` labels | Use GitHub-hosted or self-hosted runners |
| CI/CD Settings variables | GitHub Secrets / Variables | Must be migrated manually |

---

## Variable Translation Reference

gl2gh automatically translates GitLab CI predefined variables to their GitHub Actions equivalents:

| GitLab CI Variable | GitHub Actions Equivalent | Description |
|---|---|---|
| `$CI_COMMIT_SHA` | `${{ github.sha }}` | Full commit SHA |
| `$CI_COMMIT_SHORT_SHA` | `${{ github.sha }}` | Short SHA (GitHub has no built-in short SHA) |
| `$CI_COMMIT_REF_NAME` | `${{ github.ref_name }}` | Branch or tag name |
| `$CI_COMMIT_REF_SLUG` | `${{ github.ref_name }}` | URL-safe branch/tag name |
| `$CI_COMMIT_BRANCH` | `${{ github.ref_name }}` | Branch name |
| `$CI_COMMIT_TAG` | `${{ github.ref_name }}` | Tag name |
| `$CI_DEFAULT_BRANCH` | `${{ github.event.repository.default_branch }}` | Default branch |
| `$CI_PIPELINE_ID` | `${{ github.run_id }}` | Pipeline/run ID |
| `$CI_JOB_ID` | `${{ github.job }}` | Job identifier |
| `$CI_JOB_NAME` | `${{ github.job }}` | Job name |
| `$CI_PROJECT_NAME` | `${{ github.event.repository.name }}` | Repository name |
| `$CI_PROJECT_PATH` | `${{ github.repository }}` | owner/repo |
| `$CI_PROJECT_URL` | `${{ github.event.repository.html_url }}` | Repository URL |
| `$CI_PROJECT_NAMESPACE` | `${{ github.repository_owner }}` | Organization/user |
| `$CI_PROJECT_DIR` | `${{ github.workspace }}` | Working directory |
| `$CI_BUILDS_DIR` | `${{ github.workspace }}` | Build directory |
| `$CI_REGISTRY` | `ghcr.io` | Container registry host |
| `$CI_REGISTRY_IMAGE` | `ghcr.io/${{ github.repository }}` | Container image path |
| `$CI_REGISTRY_USER` | `${{ github.actor }}` | Registry username |
| `$CI_REGISTRY_PASSWORD` | `${{ secrets.GITHUB_TOKEN }}` | Registry password |
| `$CI_MERGE_REQUEST_IID` | `${{ github.event.pull_request.number }}` | MR/PR number |
| `$CI_MERGE_REQUEST_SOURCE_BRANCH_NAME` | `${{ github.head_ref }}` | Source branch |
| `$CI_MERGE_REQUEST_TARGET_BRANCH_NAME` | `${{ github.base_ref }}` | Target branch |
| `$CI_SERVER_HOST` | `github.com` | Server hostname |

Custom variables defined in GitLab CI/CD Settings must be manually added as GitHub Secrets or repository variables.

---

## Step-by-Step Migration Process

### Step 1: Inspect Your Pipeline

Before converting, understand your pipeline structure:

```bash
gl2gh inspect .gitlab-ci.yml -v
```

This displays stages, jobs, templates, global variables, default image, and include references. Review this output to identify any complex patterns that may need special attention.

### Step 2: Preview the Conversion

Run a dry conversion to see what gl2gh will produce:

```bash
gl2gh migrate .gitlab-ci.yml --dry-run --verbose
```

Pay attention to:
- **Warnings** -- Features that were converted but may need manual review.
- **Unsupported features** -- GitLab CI features with no direct GitHub Actions equivalent.
- **Conversion notes** -- Decisions made during conversion (e.g., which action was chosen for JUnit reports).

### Step 3: Run the Migration

```bash
# Rule-based migration
gl2gh migrate .gitlab-ci.yml -n "CI Pipeline" -o .github/workflows

# AI-enhanced migration for complex pipelines
export GITHUB_TOKEN="ghp_your-token-here"
gl2gh migrate .gitlab-ci.yml --ai -n "CI Pipeline" -o .github/workflows
```

### Step 4: Validate the Output

```bash
gl2gh validate .github/workflows/
```

This checks YAML syntax, required fields, job structure, and runner names.

### Step 5: Migrate Secrets and Variables

GitLab CI/CD variables stored in project or group settings must be manually added to GitHub:

```bash
# Using the gh CLI
gh secret set DATABASE_URL --body "postgres://..."
gh secret set DEPLOY_KEY --body "..."
gh secret set DOCKER_PASSWORD --body "..."

# For non-sensitive variables, use repository variables
gh variable set NODE_ENV --body "production"
```

Update your workflow to reference these:

```yaml
env:
  DATABASE_URL: ${{ secrets.DATABASE_URL }}
  NODE_ENV: ${{ vars.NODE_ENV }}
```

### Step 6: Create GitHub Environments

If your pipeline uses GitLab environments, create corresponding GitHub environments:

1. Go to your repository Settings > Environments.
2. Create environments matching your GitLab environment names (e.g., `staging`, `production`).
3. Configure protection rules (required reviewers, wait timers, branch restrictions).

### Step 7: Review and Adjust

Open each generated workflow file and verify:
- Trigger conditions (`on:`) match your branching strategy.
- Secret names match what you configured in GitHub.
- Service container configurations are correct (GitHub uses `localhost` for service access when not using a container job).
- Docker registry references use `ghcr.io` instead of GitLab Container Registry.

### Step 8: Push and Test

```bash
# Add the workflow files
git add .github/workflows/
git commit -m "Add GitHub Actions workflows (migrated from GitLab CI)"
git push

# Monitor the workflow run
gh run list
gh run watch
```

---

## Common Patterns

### Stages and Job Dependencies

GitLab CI uses `stages` for sequential ordering. All jobs in a stage run in parallel, and the next stage waits for all previous stage jobs to complete. GitHub Actions uses explicit `needs` for dependency graphs.

**Before (GitLab CI):**

```yaml
stages:
  - build
  - test
  - deploy

build_app:
  stage: build
  script:
    - make build

run_tests:
  stage: test
  script:
    - make test

deploy_app:
  stage: deploy
  script:
    - make deploy
```

**After (GitHub Actions):**

```yaml
jobs:
  build_app:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run script
        run: make build

  run_tests:
    runs-on: ubuntu-latest
    needs: [build_app]
    steps:
      - uses: actions/checkout@v4
      - name: Run script
        run: make test

  deploy_app:
    runs-on: ubuntu-latest
    needs: [run_tests]
    steps:
      - uses: actions/checkout@v4
      - name: Run script
        run: make deploy
```

---

### Docker Builds

GitLab CI uses Docker-in-Docker (DinD) with a service container. GitHub Actions provides Docker natively on runners, and the community `docker/build-push-action` is the recommended approach.

**Before (GitLab CI):**

```yaml
build_docker:
  stage: build
  image: docker:24
  services:
    - docker:24-dind
  variables:
    DOCKER_HOST: tcp://docker:2376
    DOCKER_TLS_CERTDIR: "/certs"
  script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    - docker build -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA .
    - docker push $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
```

**After (GitHub Actions):**

```yaml
build_docker:
  runs-on: ubuntu-latest
  permissions:
    contents: read
    packages: write
  steps:
    - uses: actions/checkout@v4

    - name: Log in to GitHub Container Registry
      uses: docker/login-action@v3
      with:
        registry: ghcr.io
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Build and push Docker image
      uses: docker/build-push-action@v5
      with:
        context: .
        push: true
        tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
```

---

### Matrix Builds

Both platforms support matrix strategies. The syntax is very similar.

**Before (GitLab CI):**

```yaml
test:
  stage: test
  image: python:${PYTHON_VERSION}
  parallel:
    matrix:
      - PYTHON_VERSION: ["3.10", "3.11", "3.12"]
  script:
    - pytest tests/ -v
```

**After (GitHub Actions):**

```yaml
test:
  runs-on: ubuntu-latest
  strategy:
    matrix:
      PYTHON_VERSION: ["3.10", "3.11", "3.12"]
    fail-fast: false
  container:
    image: python:${{ matrix.PYTHON_VERSION }}
  steps:
    - uses: actions/checkout@v4
    - name: Run script
      run: pytest tests/ -v
```

---

### Caching

GitLab CI has built-in `cache` at the job level. GitHub Actions uses the `actions/cache` action as a step.

**Before (GitLab CI):**

```yaml
build:
  image: node:20
  cache:
    key: ${CI_COMMIT_REF_SLUG}-node
    paths:
      - node_modules/
  script:
    - npm ci
    - npm run build
```

**After (GitHub Actions):**

```yaml
build:
  runs-on: ubuntu-latest
  container:
    image: node:20
  steps:
    - uses: actions/checkout@v4

    - name: Cache dependencies
      uses: actions/cache@v4
      with:
        path: node_modules/
        key: ${{ github.ref_name }}-node
        restore-keys: |
          ${{ github.ref_name }}-node
          ${{ runner.os }}-

    - name: Run script
      run: |
        npm ci
        npm run build
```

---

### Artifacts

GitLab CI artifacts are built into the job definition. GitHub Actions uses the `actions/upload-artifact` and `actions/download-artifact` actions.

**Before (GitLab CI):**

```yaml
build:
  stage: build
  script:
    - npm run build
  artifacts:
    paths:
      - dist/
    expire_in: 1 week

deploy:
  stage: deploy
  dependencies:
    - build
  script:
    - deploy dist/
```

**After (GitHub Actions):**

```yaml
build:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Run script
      run: npm run build
    - name: Upload artifacts
      uses: actions/upload-artifact@v4
      with:
        name: build-artifacts
        path: dist/
        retention-days: 7

deploy:
  runs-on: ubuntu-latest
  needs: [build]
  steps:
    - uses: actions/checkout@v4
    - name: Download artifacts
      uses: actions/download-artifact@v4
      with:
        name: build-artifacts
        path: dist/
    - name: Run script
      run: deploy dist/
```

---

### Services

Both platforms support service containers. GitLab uses the `services` keyword at the job level, and GitHub Actions has a similar `services` keyword.

**Before (GitLab CI):**

```yaml
test:
  image: python:3.12
  services:
    - name: postgres:16
      alias: db
    - name: redis:7
      alias: cache
  variables:
    DATABASE_URL: postgresql://postgres:postgres@db:5432/testdb
    REDIS_URL: redis://cache:6379
  script:
    - pytest tests/
```

**After (GitHub Actions):**

```yaml
test:
  runs-on: ubuntu-latest
  container:
    image: python:3.12
  services:
    postgres:
      image: postgres:16
      env:
        POSTGRES_PASSWORD: postgres
    redis:
      image: redis:7
  env:
    DATABASE_URL: postgresql://postgres:postgres@postgres:5432/testdb
    REDIS_URL: redis://redis:6379
  steps:
    - uses: actions/checkout@v4
    - name: Run script
      run: pytest tests/
```

**Important difference:** In GitLab CI, services are accessible by their `alias`. In GitHub Actions, when running in a container, services are accessible by their service name (the key under `services`). When running directly on the runner (no `container`), services are accessible at `localhost` with mapped ports.

---

### Environments and Deployments

GitLab CI `environment` maps to GitHub Actions `environment`. Both support environment names and URLs.

**Before (GitLab CI):**

```yaml
deploy_staging:
  stage: deploy
  script:
    - deploy --target staging
  environment:
    name: staging
    url: https://staging.example.com
  rules:
    - if: $CI_COMMIT_BRANCH == "develop"
```

**After (GitHub Actions):**

```yaml
deploy_staging:
  runs-on: ubuntu-latest
  environment:
    name: staging
    url: https://staging.example.com
  if: github.ref_name == 'develop'
  steps:
    - uses: actions/checkout@v4
    - name: Run script
      run: deploy --target staging
```

**Note:** GitHub environments must be created in your repository settings. You can add protection rules, required reviewers, and deployment branch restrictions there.

---

### Rules and Conditional Execution

GitLab CI `rules` with `if` conditions are translated to GitHub Actions `if` expressions.

**Before (GitLab CI):**

```yaml
sast:
  stage: security
  script:
    - bandit -r src/
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
  allow_failure: true
```

**After (GitHub Actions):**

```yaml
sast:
  runs-on: ubuntu-latest
  if: github.event_name == 'pull_request' || github.ref_name == github.event.repository.default_branch
  continue-on-error: true
  steps:
    - uses: actions/checkout@v4
    - name: Run script
      run: bandit -r src/
```

---

### Templates and Extends

GitLab CI supports reusable templates via hidden jobs (`.dot` prefix) and `extends`. GitHub Actions does not have a direct equivalent; gl2gh resolves templates by inlining the inherited properties.

**Before (GitLab CI):**

```yaml
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
```

**After (GitHub Actions):**

```yaml
build:
  runs-on: ubuntu-latest
  container:
    image: python:3.12
  steps:
    - uses: actions/checkout@v4
    - name: Cache dependencies
      uses: actions/cache@v4
      with:
        path: .cache/pip
        key: requirements.txt
    - name: Before script
      run: pip install -r requirements.txt
      shell: bash
    - name: Run script
      run: python -m build
      shell: bash
```

For complex template hierarchies, consider converting to [reusable workflows](https://docs.github.com/en/actions/using-workflows/reusing-workflows) or [composite actions](https://docs.github.com/en/actions/creating-actions/creating-a-composite-action).

---

### Manual Jobs

GitLab CI `when: manual` creates jobs that require a manual click to run. The closest GitHub Actions equivalent is the `workflow_dispatch` trigger or environment protection rules with required reviewers.

**Before (GitLab CI):**

```yaml
deploy_production:
  stage: deploy
  script:
    - deploy --target production
  environment:
    name: production
  when: manual
  only:
    - main
```

**After (GitHub Actions):**

```yaml
# Option 1: Use environment protection rules (recommended)
deploy_production:
  runs-on: ubuntu-latest
  environment:
    name: production  # Configure required reviewers in repo settings
  steps:
    - uses: actions/checkout@v4
    - name: Run script
      run: deploy --target production

# Option 2: Use workflow_dispatch for manual triggering
on:
  workflow_dispatch:
    inputs:
      confirm:
        description: "Type 'deploy' to confirm production deployment"
        required: true
```

---

## Troubleshooting Common Issues

### "No such file or directory" errors in scripts

**Cause:** The checkout step is missing or placed incorrectly.

**Fix:** Ensure `actions/checkout@v4` is the first step in every job. gl2gh adds this automatically, but verify it was not accidentally removed.

```yaml
steps:
  - uses: actions/checkout@v4  # Must be first
  - run: ./scripts/build.sh
```

---

### Service containers are not accessible

**Cause:** GitLab CI services use their `alias` as the hostname. GitHub Actions uses the service key name when running in a container, or `localhost` with port mapping when running on the host.

**Fix (running in a container):**
```yaml
services:
  db:  # Accessible as hostname "db"
    image: postgres:16
container:
  image: python:3.12
env:
  DATABASE_URL: postgresql://postgres@db:5432/testdb
```

**Fix (running on the host):**
```yaml
services:
  db:
    image: postgres:16
    ports:
      - 5432:5432  # Map port to localhost
env:
  DATABASE_URL: postgresql://postgres@localhost:5432/testdb
```

---

### Environment variables are not available

**Cause:** Variables defined in GitLab CI/CD project settings are not automatically available in GitHub Actions.

**Fix:** Add them as GitHub Secrets or repository variables:

```bash
gh secret set MY_SECRET --body "secret-value"
gh variable set MY_VAR --body "non-secret-value"
```

Reference in workflows:
```yaml
env:
  MY_SECRET: ${{ secrets.MY_SECRET }}
  MY_VAR: ${{ vars.MY_VAR }}
```

---

### Docker-in-Docker does not work

**Cause:** GitHub Actions runners have Docker pre-installed. The GitLab DinD pattern (using `docker:dind` as a service) is unnecessary.

**Fix:** Use Docker directly on the runner, or use the `docker/build-push-action`:

```yaml
steps:
  - uses: actions/checkout@v4
  - uses: docker/setup-buildx-action@v3
  - uses: docker/build-push-action@v5
    with:
      context: .
      push: true
      tags: ghcr.io/${{ github.repository }}:latest
```

---

### Workflow does not trigger

**Cause:** The `on` trigger configuration does not match your branch or event.

**Fix:** Check the following:
1. The workflow file must be in `.github/workflows/` on the repository's default branch for `push` and `pull_request` triggers to work.
2. Branch patterns must match your branch names:
   ```yaml
   on:
     push:
       branches: [main, develop]
     pull_request:
       branches: [main]
   ```
3. For tag triggers:
   ```yaml
   on:
     push:
       tags: ["v*"]
   ```

---

### Cache is not being restored

**Cause:** Cache keys do not match between save and restore.

**Fix:** Use consistent cache keys. Note that `$CI_COMMIT_REF_SLUG` translates to `${{ github.ref_name }}`:

```yaml
- uses: actions/cache@v4
  with:
    path: node_modules/
    key: ${{ runner.os }}-node-${{ hashFiles('package-lock.json') }}
    restore-keys: |
      ${{ runner.os }}-node-
```

---

### Artifacts are not passed between jobs

**Cause:** GitHub Actions requires explicit upload and download of artifacts between jobs, unlike GitLab CI where artifacts are automatically available to subsequent stages.

**Fix:** Add both upload and download steps:

```yaml
# Job 1: Upload
- uses: actions/upload-artifact@v4
  with:
    name: my-artifact
    path: dist/

# Job 2: Download
- uses: actions/download-artifact@v4
  with:
    name: my-artifact
    path: dist/
```

---

### `include` directives are not supported

**Cause:** GitLab CI `include` (local, remote, template, project) has no direct equivalent in a single workflow file.

**Fix:**
- **`include:local`** -- Inline the included file contents into the main workflow, or convert to a [reusable workflow](https://docs.github.com/en/actions/using-workflows/reusing-workflows).
- **`include:remote`** -- Download the file and inline it, or use a composite action.
- **`include:template`** -- Replace with equivalent GitHub Actions or third-party actions.
- **`include:project`** -- Convert to reusable workflows in the source repository.

---

### Getting Help

```bash
# Inspect pipeline structure to understand what needs migration
gl2gh inspect .gitlab-ci.yml -v

# Run verbose migration to see all warnings and notes
gl2gh migrate .gitlab-ci.yml --dry-run -v

# Use AI-enhanced mode for complex pipelines
gl2gh migrate .gitlab-ci.yml --ai -v

# Check GitHub CLI integration status
gl2gh gh-status
```
