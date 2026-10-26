# MVI private single-host pilot deployment template

Not deployed. Do not expose port 8765 to the internet: token authentication is prototype-only and does not replace production access controls.
The two systemd units are templates for a Linux machine with `/opt/ai-os/apps/mvi`,
a dedicated unprivileged `mvi` user, and a private writable `/var/lib/mvi`.
Dependencies (ffmpeg, yt-dlp, Python environment) must be installed and verified.
Run the API and worker as separate supervised services. Both must share the same
private data directory on the same host. SQLite is not a distributed queue.
Do not enable external access or run on shared infrastructure before completing
security review, authentication, resource limits, and crash/recovery acceptance tests.
The worker does not require the user's Mac to stay awake once actually deployed.

## Optional API bearer token
Set `MVI_API_TOKEN` in the API service environment through a private credential
mechanism (never commit a token). When set, all API and dashboard requests
require `Authorization: Bearer <token>`. The bundled HTML dashboard accepts the token in the browser session and supplies this header for API calls and report downloads.
The token is a defense-in-depth prototype, not production authentication:
there are no users, roles, rate limits, HTTPS termination, or secret rotation.
Keep the API bound to loopback and do not publish the service publicly.

Production-mode service template requires a private `/etc/mvi/api.env` containing `MVI_API_TOKEN`, readable only by the service administrator. Missing token now prevents API startup. The Linux unit templates set a 2 GiB memory cap, 150% CPU quota, and process/file limits. These limits have not been verified against representative video workloads.


## Queue snapshots

A consistent queue-only snapshot can be made while the worker is active:

`python deployment/backup_queue.py --root /var/lib/mvi --output /var/backups/mvi/queue-YYYYMMDD.db`

Each output name must be unique; the command refuses to overwrite an existing snapshot.
Snapshots contain queue metadata and payloads, **not video uploads, evidence, or reports**.
A recoverable installation also needs secure backups of `/var/lib/mvi` job media and
outputs, coordinated with queue state. Never claim full disaster recovery from a
queue-only snapshot. Do not restore a snapshot over a running service.

## Dual Brain UI (2026-10-26)

The same MVI web service now serves an analysis hemisphere and a separate source-learning hemisphere from `brain_studio.html`.
Both use the private bearer token for API requests; the shell remains readable without authorization so a token can be entered.
Teaching sources join the durable worker queue and candidate excerpts cannot influence editor reports until explicitly approved.
See `research/DUAL_BRAIN_PILOT.md` for routes, assumptions, test coverage and known limitations.
