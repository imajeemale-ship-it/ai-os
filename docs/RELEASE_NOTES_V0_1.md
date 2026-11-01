# AI-OS v0.1.0 — release candidate notes

**Status: draft; not tagged or published.**

## Demonstrated core

- Local SQLite project/task storage and CLI.
- Deterministic ranking of ready tasks.
- Dry-run planning without task mutation.
- Explicit task acceptance changes the recommended task to `in_progress`.
- Approval boundaries for consequential action categories.

## Verification

- 112 root tests passed on Python 3.11.15 and 3.14.5 locally.
- Fresh Python 3.11 virtual-environment editable install and CLI smoke test passed.
- A nonempty task acceptance lifecycle passed with an isolated SQLite database.
- GitHub Actions run #41360832002 succeeded on Ubuntu with Python 3.11 and 3.14 jobs, including tests, installation, and CLI smoke tests.

## Limitations

- The demonstrated control plane does not itself execute external actions or complete tasks autonomously.
- MVI video analysis and external integrations have not been validated as part of the core release.
- No root project license has been confirmed. The Vindex vendored component has a separate MIT license.
- Expanded pattern scanning of all 610 enumerated history blobs found no matches; comprehensive secrets/privacy clearance remains outstanding.
- Vindex local import patches are attributed in Git but have known missing-dependency error handling gaps; optional-stage execution is unverified.

See `docs/RELEASE_VERIFICATION.md` and `docs/ARCHITECTURE_V0_1.md`.
