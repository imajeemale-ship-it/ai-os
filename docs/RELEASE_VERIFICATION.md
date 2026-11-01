# AI-OS v0.1 verification (2026-11-01)

Status: release candidate in preparation; **not released**.

## Verified baseline

- Commit: `8186d546bbaa3ee4358249f47ba119ac16ccde4c`.
- macOS / Python 3.14.5.
- `python3 -m unittest discover -s tests -v`: **112 tests passed, zero failures** (1.733 seconds).
- With an isolated temporary SQLite database, `init`, `project add`, `projects`, `plan`, and `run` completed successfully. An empty plan did not change task state.

## Reproducible smoke test

Run from the repository root:

```sh
export AI_OS_DB="$(mktemp -d)/ai_os.db"
python3 -m ai_os init
python3 -m ai_os project add "Portfolio Demo" --priority 1 --goal "Demonstrate reviewable execution"
python3 -m ai_os projects
python3 -m ai_os plan
python3 -m ai_os run
python3 -m unittest discover -s tests -v
```

The default `run` behavior prepares a plan, not external execution. This smoke test uses no third-party services.

## Open release gates

- Clean Python 3.11 installation and package installation test.
- Tracked-file and Git-history secrets/privacy audit.
- Licensing and third-party provenance review (no root `LICENSE` file found).
- CI setup and cross-platform test coverage (no baseline `.github/workflows` directory found).
- Nonempty task lifecycle demonstration.
- Independent review of release documentation and claims.
- MVI under `apps/mvi` needs its own tests and video-to-report verification; the 112 root tests do not establish that.

Do not merge or publish a release until these gates have been evaluated.
