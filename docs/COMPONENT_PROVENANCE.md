# AI-OS component provenance inventory

**Status:** initial inventory only; ownership and redistribution rights not fully verified.

| Component | Tracked files | Known origin / rights status | Release handling |
|---|---:|---|---|
| `ai_os/` | 23 | Original author/contributor ownership not yet independently established | Keep root license undecided |
| `apps/mvi/vendor-evaluation/vindex/` | 136 | Includes MIT license naming Vaibhav Dubey (2026); `pyproject.toml` declares MIT | Preserve license and attribution; verify upstream origin and modifications |
| `apps/mvi/` excluding Vindex | 70 | Original versus third-party provenance not independently established | Separate MVI release testing and provenance review |
| `apps/signal-watch/` | 17 | Includes local launch-agent installer and integration-specific scripts | Review configuration, machine-specific paths, and any rights in source data |
| `deploy/` | 8 | Deployment artifacts | Review environment references and deployment safety |

Counts reflect tracked paths on the release checkout as of 2026-11-01. The 290 tracked paths also include tests, docs, examples, and configuration.

## Dependency boundaries

- Root `pyproject.toml`: no declared runtime dependencies; Python >=3.11.
- MVI `requirements.txt`: av, diskcache, pillow, pydantic, scenedetect, opencv-python-headless, yt-dlp.
- Vendored Vindex `pyproject.toml`: separate dependencies including faster-whisper, mlx, paddleocr, sentence-transformers, FastAPI, and others. These are **not** automatically root AI-OS runtime dependencies.
- Dependency names and license declarations are not proof of redistribution compliance for every artifact.

## Identified portability concern

`apps/signal-watch/scripts/install-launch-agent.sh` contains absolute local paths for `REPO_ROOT` and `SIGNAL_WATCH_SUPERVIZOR_ROOT`, plus hard-coded chat filters. Changing these could affect existing local service behavior. **Do not rewrite the active installer merely to improve portfolio appearance without validating replacement configuration.** A safer next step is a separate portable example or targeted, tested change.

## Recommended portfolio boundary

Demonstrate the core `ai_os/` package and its 112 root tests as the flagship. Treat MVI, signal-watch, and vendored Vindex as adjacent/integration areas, not as capabilities validated by the core suite. This is a presentation boundary, **not** a proposal to delete or relicense files.

## Open decisions

- Owner reports the project began through ChatGPT-assisted development; recorded in `OWNERSHIP_LICENSING_REVIEW.md`. File-level provenance and rights remain subject to review.
- Vindex upstream comparison and local-patch static review completed; retain MIT notice and resolve the documented optional-stage handling gaps before claiming execution support.
- Audit sensitive history beyond narrow regex patterns.
- Choose final root license only after review and explicit owner approval.
