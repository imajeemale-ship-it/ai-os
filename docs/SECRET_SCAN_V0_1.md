# AI-OS v0.1 maintained secret scan

## Tool and integrity

- Tool: Gitleaks 8.30.1, official `gitleaks/gitleaks` release `v8.30.1`.
- Source: https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1
- Artifact: `gitleaks_8.30.1_darwin_arm64.tar.gz`.
- SHA-256: `b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5`, matched the official release API asset digest before execution.
- Executed from a temporary directory; no system-wide installation, service change, or production credential access.

## Scope and results

Scanned release HEAD `38f78fcb03135a879599d7e94e90ffd0e021cee4` and all refs available in the local repository. The repository had 173 reachable commits, including two merge commits. Gitleaks reported 171 scanned commits; its reported count should not be confused with the reachable-commit inventory.

| Scan | Reported input size | Findings | Exit code |
|---|---:|---:|---:|
| Git history, `--log-opts=--all` | 4.17 MB | 0 | 0 |
| Tracked HEAD snapshot exported with `git archive` | 2.27 MB, 296 tracked paths | 0 | 0 |

Used default Gitleaks rules with scanner-configuration environment overrides removed. No repository `.gitleaks.toml` or `.gitleaksignore` was present. Inline allow comments were ignored, archive traversal depth was 3, and secrets were fully redacted. Reports/logs stayed outside the repository; no raw matched values were printed. No findings required triage.

Commands after obtaining and integrity-checking the pinned executable:

```sh
gitleaks git --log-opts=--all REPOSITORY_PATH --redact=100 --no-banner --no-color --ignore-gitleaks-allow --max-archive-depth=3 --report-format=json --report-path=HISTORY_REPORT --timeout=120
gitleaks dir TRACKED_SNAPSHOT_PATH --redact=100 --no-banner --no-color --ignore-gitleaks-allow --max-archive-depth=3 --report-format=json --report-path=TRACKED_REPORT --timeout=120
```

Run outside the repository with scanner configuration overrides removed, and export the tracked snapshot using `git archive HEAD`. Do not substitute a live home directory or credential directory as the scan target.

## Privacy follow-up and limits

IPv4-shaped candidates outside loopback/wildcard addresses were manually checked in the vendored lockfile and website: they were package versions/wheel filenames and SVG path coordinates, not identified network destinations. Known personal machine paths remain in operational installers, and historical Git metadata can contain personal identity/hostnames; neither was rewritten. Earlier documentation home-prefix cleanup remains in place.

**Result:** the maintained secret-scanner check passed for the stated inputs and rules. This is not proof that all secrets, personal data, proprietary content, or legal issues are absent. Unreachable/deleted remote refs, untracked files, external services, credential validity, and changes after the scanned revision are outside this result. A privacy/redistribution decision for known operational metadata and a root-license decision remain separate.

## Independent evidence recheck

A separate read-only AI reviewer checked the retained scanner version, official release digest, summary, logs, empty JSON reports, tracked-path inventory, and evidence diff. No substantive inconsistency was found. A follow-up scan at `41fb48c` also produced empty history/snapshot reports; the reviewer checked those retained logs and reports. The reviewer did not independently rerun the scanner or certify every invocation flag/environment value, privacy, legal ownership, or credential validity. Exact follow-up revision and exit codes were reported by the implementing agent and were consistent with the retained evidence.
