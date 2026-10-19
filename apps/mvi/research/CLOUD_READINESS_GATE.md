# MVI cloud readiness — security and reliability gate

Status: **NOT READY FOR PUBLIC DEPLOYMENT**. The current prototype intentionally binds to 127.0.0.1, has no user authentication, stores job state in a process-global dictionary, and runs analysis in daemon threads. It is a local development service, not an unattended cloud worker.

## Before any private cloud pilot

1. Authentication and authorization on upload, job, report, and health-sensitive endpoints. Random job IDs are not authorization. Deny cross-user access.
2. Use durable queue and worker processes with retries, deadlines, cancellation, and per-job resource limits. Do not depend on the owner's Mac, browser, or a sleeping session.
3. Keep footage in private encrypted object storage with short-lived signed access, explicit retention/deletion, and no public buckets. Keep derived frames and transcripts equally private.
4. Sandbox FFmpeg and any media parsers with CPU/memory/time limits. Validate content with ffprobe; reject unsupported media and mismatched extension/MIME. Enforce request and account quotas.
5. Lock down URL ingestion against SSRF and internal network access; restrict destinations to intended public video hosts and disallow redirects to private addresses.
6. Keep all external AI, publishing, and paid services disabled by default. Local/Ollama tests should not silently switch to paid APIs.
7. Use secrets manager, least-privilege service identities, TLS, structured audit logs, health/readiness checks, and alerting. Never commit credentials.
8. Use job-specific statuses and provenance in reports: technical extraction, scene boundaries, audio signal, sampled-frame vision, human-verified claims, and unavailable stages.
9. Test restarts and failure recovery; enforce idempotency; verify that an uploaded clip and a URL clip both produce editor report + David handoff, or an explicit failure state.
10. Private pilot only after explicit approval. No public deployment, GitHub push, or credential provisioning from this run.

## Current local verification

- Uploaded videos now enter the same report-producing pipeline as URL jobs, with persisted job state and a pollable report URL.
- HTTP-level synthetic-video test verifies upload, completion, editor report, handoff, timeline, and invalid job-ID rejection.
- Scene/shot segmentation and low-volume audio detection work locally on the 60.88-second intro.
- Vision remains an optional best-effort stage. On this M1 8GB Mac, the 3-frame run produced no usable output after 219s, and a single downsampled-frame retry timed out after 75s. The server therefore disables local vision by default; opt in only with `MVI_ENABLE_LOCAL_VISION=1` on suitable hardware. Missing output never becomes invented feedback or a numeric creative score.

## Next cloud-ready milestone

Build a local durable job queue prototype (e.g. SQLite + supervised worker) and tests for restart/retry behavior before choosing any paid infrastructure. Do not deploy until authentication, storage isolation, and resource limits are implemented.

## Local hardening verified on 2026-10-19

- Job directories created through upload and URL intake now request mode 0700; HTTP tests check these permissions.
- Job state is written to a temporary file and atomically replaced, reducing the risk of a truncated `job.json` after a crash.
- After a server restart, previously active persisted jobs report `interrupted` instead of falsely remaining `running`; automatic recovery is NOT implemented.
- The browser continues polling through the URL `retrieving` state; previously this stage could strand a report in the UI.
- Upload and mocked-URL HTTP flows are covered by end-to-end tests; the URL test does not download a real YouTube video.
- Full local test suite: 33 passing tests (reverify after subsequent changes). This is not a cloud security audit.
- The next meaningful cloud milestone remains an authenticated private worker with a durable queue, storage isolation, retry policy, and resource quotas. No deployment is authorized.

## Additional evidence-integrity guard

Optional human_review.json annotations are bound to the exact media SHA-256 and an extracted frame timestamp. A mismatch causes exclusion and a visible warning, preventing accidental reuse on a different clip. This is a local provenance check, not cloud authentication. No deployment was made.

## Cross-modal evidence integrity — 2026-10-19

The editor report can now rank measured shot/low-audio overlaps as explicit human A/V review checkpoints. It rejects non-finite or out-of-range overlap evidence and does not infer dialogue, humor, edit defects, or creative scores. Three additional tests cover real-valued overlap, absent evidence, and invalid/tiny overlaps. Full local suite: 40 passing tests. This is still not a complete audiovisual semantic review or a cloud-ready service.
