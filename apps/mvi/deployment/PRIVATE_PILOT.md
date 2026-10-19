# MVI private single-host pilot deployment template

Not deployed. Do not expose port 8765 to the internet: HTTP endpoints have no authentication.
The two systemd units are templates for a Linux machine with `/opt/ai-os/apps/mvi`,
a dedicated unprivileged `mvi` user, and a private writable `/var/lib/mvi`.
Dependencies (ffmpeg, yt-dlp, Python environment) must be installed and verified.
Run the API and worker as separate supervised services. Both must share the same
private data directory on the same host. SQLite is not a distributed queue.
Do not enable external access or run on shared infrastructure before completing
security review, authentication, resource limits, and crash/recovery acceptance tests.
The worker does not require the user's Mac to stay awake once actually deployed.
