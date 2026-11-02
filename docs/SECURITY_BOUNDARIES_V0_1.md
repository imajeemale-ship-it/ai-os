# AI-OS v0.1 security boundaries

## Reviewed scope

This review covers the local SQLite planning/task-acceptance demo, the approval registry, model proposal validation, and the optional provider adapter. It is a source review by the release implementer, not an independent security audit. It does not certify MVI, signal-watch, trading integrations, deployed services, or every historical file.

## Trust boundaries

| Boundary | Observed behavior | Limit |
|---|---|---|
| Local CLI and SQLite | SQL values are parameterized in the inspected store methods; status and priority inputs are checked | Any account able to edit the database can alter tasks, approvals, and events |
| Task acceptance | Default run leaves tasks unchanged; explicit acceptance must identify the current recommended task | A local state transition does not execute work or authorize an external system |
| Approval registry | Known gated actions require an approved, unexpired matching action/scope record | This helper only protects callers that use it; it is not a sandbox or monorepo-wide enforcement layer |
| Event journal | Store operations record events in SQLite transactions | The journal is editable by the database owner; it is not tamper-proof evidence |
| Model proposal | Selected IDs must belong to eligible local tasks; explicit acceptance is required | Model reasons remain untrusted text and should not become executable instructions |
| Optional model endpoint | HTTPS is required except loopback HTTP; credential URLs and redirects are rejected | Invoking a remote provider sends task IDs, titles, project names/goals, status, priority, and due dates to that configured endpoint |

## Local data handling

The database is not encrypted by the application. Its directory and file permissions depend on the operating system and process umask. Use a protected user account and disk encryption where appropriate. Keep credentials out of task text, project goals, logs, screenshots, and version control. The portfolio verifier uses a temporary database and does not invoke providers or integrations.

The optional provider can read local model configuration. Running that integration is a separate disclosure decision from running the offline portfolio demo. Existing integration commands can perform network activity; the core demo's lack of external effects must not be generalized to every CLI command.

## Evidence and remaining work

The root suite includes approval matching/expiry and model validation cases. Installed-CLI verification checks the nonempty plan, dry run, rejected acceptance, and accepted task state. Bounded history credential scanning and privacy findings are recorded in `OWNERSHIP_LICENSING_REVIEW.md`.

Remaining: independent security review, maintained full-history secret scanning, adjacent integration review, and verification against the exact revision proposed for merge. Do not report these as passed based on this document.
