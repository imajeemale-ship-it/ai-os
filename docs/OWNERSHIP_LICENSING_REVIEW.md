# AI-OS ownership and licensing review

**Status:** in progress. No root license chosen or granted.

## Scope and policy

The repository is already public. Public visibility does **not** by itself authorize general commercial reuse of original code. The owner selected **review ownership first**, before deciding whether to license original AI-OS code under MIT or retain exclusive rights.

Do not add a root MIT license, represent the entire repository as MIT-licensed, or tag a public release until the review is complete.

## Confirmed repository facts (2026-11-01)

- Root `pyproject.toml` declares the `ai-os` package, version `0.1.0`, Python >=3.11, and no runtime dependencies for the core package.
- No root `LICENSE` file was present in the inspected release baseline.
- `apps/mvi/vendor-evaluation/vindex/LICENSE` is an MIT license with copyright attributed to **Vaibhav Dubey (2026)**.
- The vendored Vindex `pyproject.toml` declares MIT and lists its own substantial dependencies. Its MIT license applies to that component, **not automatically to all AI-OS source**.
- The repository also contains MVI, signal-watch, Robinhood/paper-research, and deployment material beyond the narrow local-first control plane.
- Core tests and CI verify functionality, **not** ownership, permission to redistribute, or privacy compliance.

## Review before publication or relicensing

1. Identify the original authors and any contributors or employers/clients with possible rights in each major component.
2. Inventory third-party vendored code, assets, copied snippets, sample data, and generated files. Retain required copyright and license notices.
3. Determine whether all vendored files were lawfully obtained and can be redistributed in this repository; review upstream license and modifications.
4. Review the **entire Git history** and tracked files for secrets, tokens, personal data, proprietary content, and accidental publication. Pattern-only scans are insufficient.
5. Decide whether AI-OS core should be split into a clean, independently licensable portfolio package, leaving sensitive or unrelated applications out.
6. Only after these checks, obtain the owner's explicit license selection and approval for any material publication/rewrite.

## Preliminary security observations — not a clearance

A limited tracked-file regex check for several credential token formats outside Vindex returned no matching files. A search of core code found environment-variable credential handling. These findings neither prove secrets absent nor validate historical commits. No history-wide scanner or manual complete review has yet passed.

## Release decision

**HOLD** root licensing and final release pending the above. Continue reversible documentation, tests, and review in the draft PR.

## Automated history and privacy triage (2026-11-01)

- Inspected **290 tracked paths** and enumerated **1,321 Git objects** across all locally available refs, including **586 blobs** (none exceeded 2 MB).
- Scanned all enumerated blobs for selected high-confidence private-key headers and AWS/GitHub/Slack token formats: **zero matches**. This is a narrow pattern-based check, **not** a comprehensive secret scanner or manual audit.
- Current tracked-file heuristics flagged two test files containing email-shaped strings, 17 files containing IPv4-shaped strings, and one shell script containing a token assignment. The token assignment interpolates a shell environment variable rather than containing an obvious hard-coded token.
- The signal-watch installation script includes an absolute local filesystem path. Review/redact machine-specific paths before presenting the repository as polished public source.
- **No credential values were printed or copied into this document.** False negatives remain possible; do not claim the repository is security-cleared.

## Expanded bounded review, 2026-11-01

After fetching available remote refs, enumerated 1,368 reachable Git objects including 610 blobs. Scanned every enumerated blob for private-key headers, selected GitHub/AWS/OpenAI/Slack token patterns, JWT-shaped strings, Telegram bot-token patterns, credential-bearing URLs, and quoted literal credential assignments. **Zero blobs matched these rules.** No matched values were output. This custom heuristic scan does not replace a maintained secret scanner, entropy analysis, manual full-history review, or credential validity checks; no full security clearance is claimed. Neither gitleaks nor trufflehog was available in the inspected shell; no tool installation was performed.

Current tree: 293 tracked files; no candidate `.env`, private-key, credential-named, or database files under the filename rules checked. Email-shaped strings occurred in two core test files and were manually confirmed as `example.com` fixtures. IPv4-shaped strings occurred in 17 files; those counts alone do not establish sensitivity. Machine paths occurred in 15 files, including third-party examples, deployment paths, three signal-watch installers, operations documentation, and M3 workflow documentation. Operational scripts were preserved because changing their paths can affect existing installations. These portability/privacy findings remain open for any claim that the entire monorepo is polished for redistribution.

Static inspection of the core execution loop confirmed task acceptance only changes local task state. The optional provider adapter requires HTTPS except loopback HTTP, rejects credential-bearing URLs, disables redirects, and sends project/task text to the explicitly configured model endpoint. Users must treat that optional invocation as disclosure of task information. Telegram control and trading integrations were inspected as source only; no network calls, sends, trading actions, service changes, or production credential reads were performed by this audit.

The Vindex modifications have recorded Git attribution and known missing-dependency handling defects; see `VINDEX_UPSTREAM_REVIEW.md`. Recorded commit authorship is not proof of ownership. Root license selection and confirmation of contributor rights still require owner judgment.

## Follow-up privacy cleanup

Replaced the personal macOS home prefix with `$HOME` in signal-watch operations and M3 workflow documentation. Existing operational installers and service files remain unchanged. This removes those explicit personal paths from the current documentation; it does not remove their historical versions or resolve installer portability. Git commit metadata can also contain personal author/committer identity and hostnames; no history rewrite or global Git identity change was performed.

## Owner-reported development origin

KD stated in this release review: “there is no original code. i started everything on chat gpt”. Record this as **owner-reported ChatGPT-assisted project development**, rather than independently verified authorship. It answers the immediate project-origin question; it is not a file-by-file assurance that generated outputs contain no third-party material, nor a legal determination of copyright or licensing rights. No employer/client contribution was identified by the owner in this exchange. Existing Vindex upstream attribution and MIT notice remain applicable. No root license was selected or granted.

## Maintained scanner follow-up

Gitleaks 8.30.1 was obtained from the official release, verified against its published asset SHA-256, and executed temporarily without a system-wide installation. Available-ref history and the tracked snapshot at `38f78fc` both returned zero findings and exit code 0. See `SECRET_SCAN_V0_1.md` for exact scope, options, sizes, counts, and limits. This supersedes the earlier statement that no maintained scanner had run; earlier bounded scan results remain historical evidence. Known operational metadata and licensing decisions are not cleared by a secret scanner.
