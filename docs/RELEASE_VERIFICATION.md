# AI-OS v0.1 — reproducible verification

**Status:** release candidate under review; not published.

## Verified on 2026-11-01

Baseline: `8186d546bbaa3ee4358249f47ba119ac16ccde4c`, macOS Apple Silicon.

| Check | Evidence |
|---|---|
| Python 3.14.5 root suite | 112 passed, 0 failed, 1.733s |
| Python 3.11.15 root suite | 112 passed, 0 failed, 1.433s |
| Fresh Python 3.11 virtual environment | `pip install --no-deps -e .` succeeded; installed ai-os 0.1.0 |
| Installed CLI | `ai-os init` and `ai-os plan` exited 0 |
| Nonempty task lifecycle | project and task created; plan ranked task; dry-run made no change; explicit `run --accept-task` changed task to `in_progress` |
| External execution | Not performed; acceptance only updates local task state |

## Reproduce locally

From the repository root, with Python 3.11+:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
export AI_OS_DB="$(mktemp -d)/ai_os.db"
.venv/bin/ai-os init
.venv/bin/ai-os project add "Portfolio Demo" --priority 1 --goal "Demonstrate reviewable execution"
.venv/bin/ai-os projects
# Copy the project id from the previous output:
.venv/bin/ai-os task add PROJECT_ID "Review a safe task" --priority 1
.venv/bin/ai-os plan
.venv/bin/ai-os run
# Copy the recommended task id from the plan:
.venv/bin/ai-os run --accept-task TASK_ID
.venv/bin/ai-os tasks
.venv/bin/python -m unittest discover -s tests -v
```

On Windows, use the corresponding virtual environment activation and executable paths. The exact commands above were tested on macOS, not Windows.

## Unresolved gates

- Full repository **and history** secrets/personal-data audit; a filename check alone is not sufficient.
- Licensing and third-party provenance review; no root `LICENSE` was found. Vendored Vindex has its own license, which does not establish licensing for the whole repository.
- CI workflow and independent clean-platform verification; no root CI workflow found.
- MVI end-to-end workflow, deployment, and security checks are separate from the 112 root tests.
- Final README, architecture, release notes, and PR review.

Do not merge or tag a public release before evaluating these gates.
