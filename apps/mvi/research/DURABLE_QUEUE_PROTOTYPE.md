# MVI durable work queue — local prototype (2026-10-19)

Status: **implemented and unit-tested, NOT integrated into the MVI HTTP server or deployed**.

The new `durable_queue.py` is a standard-library SQLite queue that can preserve work
across process restarts. The existing `server.py` still uses in-memory `JOBS`
and daemon threads; this prototype does not yet make MVI autonomous or cloud-ready.

## Verified behaviors

- Jobs survive closing and reopening the database.
- Repeated submission of the same job ID and identical payload is idempotent.
  Reusing an ID with different input is rejected.
- An atomic `BEGIN IMMEDIATE` claim prevents two workers from claiming the same job.
- Leases expire, enabling a different worker to retry interrupted work.
- A random lease token fences off late/stale workers: they cannot mark a
  re-claimed job completed or failed.
- Workers can renew a live lease; retry delays and a bounded attempt count
  prevent unbounded failure loops.
- A job whose final attempt expires is marked failed on the next claim sweep.
- The new queue directory requests mode 0700 and the SQLite database is set to
  mode 0600. These permissions are local safeguards, not cloud isolation.

## Critical integration steps before unattended use

1. Separate API ingestion from a supervised worker. Enqueue only after the
   upload is durably stored; do not enqueue an incomplete file.
2. Add a worker command that claims a job, invokes the existing media pipeline,
   heartbeats its lease during long FFmpeg jobs, and records completion/failure.
   Run it under a supervisor that restarts on crashes. Never use daemon threads
   as the sole worker.
3. Keep per-job media and reports in private durable storage; SQLite is not
   a substitute for object storage or backup.
4. Make report creation idempotent and atomic before enabling retries.
   A lease can expire while FFmpeg is still running, so duplicate attempts
   must not overwrite one another's output. Use per-attempt temporary directories
   and promote artifacts only after successful lease validation.
5. Add authentication and per-user authorization for uploads, polling, and
   reports. Limit upload size, parser resources, duration, queue depth, retries,
   and account usage. Audit URL ingestion for SSRF and unsafe redirects.
6. Test actual process kills, concurrent workers, corrupted media, and restart
   recovery against both uploaded video and URL flows. Unit tests alone do not
   establish a production-grade worker.

## Scope and constraints

No paid services, cloud resources, secrets, GitHub pushes, public deployments,
or user footage were modified by this queue prototype. No editorial observations
were generated. A private cloud pilot requires explicit approval and the
security controls in `CLOUD_READINESS_GATE.md`.
