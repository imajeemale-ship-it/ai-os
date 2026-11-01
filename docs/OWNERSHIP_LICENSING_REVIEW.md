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
