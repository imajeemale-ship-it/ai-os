# Vindex upstream provenance check

**Checked:** 2026-11-01

- Candidate upstream: https://github.com/vaibhav-space/vindex — public repository titled **vindex**, describing itself as an open-source video knowledge compiler.
- The upstream README identifies the project as MIT-licensed. The copy vendored at `apps/mvi/vendor-evaluation/vindex/` contains an MIT license attributing copyright to **Vaibhav Dubey (2026)**.
- The upstream project and vendored package both describe a local-first video compiler with structured artifacts, and the vendored package metadata declares MIT.
- **Initial identification:** superseded by the pinned file comparison below. Additional third-party asset rights remain unverified.
- This is an **evaluation vendor copy**, not original AI-OS intellectual property. Its license must be retained, and the README should not imply it was created by the AI-OS author.
- **Important package-name collision:** https://pypi.org/project/vindex/ currently describes a different project associated with `dripston/vindex`. Do not assume `pip install vindex` installs the `vaibhav-space/vindex` project. Use a verified source URL and pinned revision if integration is later approved.

**Release disposition:** preserve the vendored license and treat the upstream origin as provisionally identified. Verify exact source commit and file differences before declaring provenance complete.

## File-by-file comparison against upstream HEAD

On 2026-11-01, cloned `https://github.com/vaibhav-space/vindex.git` at upstream HEAD `174f0247907fe6e2d56e8d06d67872d1519e52e4` into a temporary review directory. Compared SHA-256 hashes of all regular files with the vendored directory:

- **136** files in each tree, identical relative path sets.
- **134** files byte-for-byte identical.
- **2** locally modified files: `vindex/compiler/pipeline.py` (26 insertions, 6 deletions) and `vindex/compiler/scheduler.py` (31 insertions, 7 deletions), compared with upstream HEAD.
- No vendor-only or upstream-only paths.

**Conclusion:** The vendored tree is a close match to this upstream revision but **not an unmodified copy**. Modification authorship, correctness, and upstream licensing obligations still need review. Do not overwrite these local changes during a vendor refresh.

## Local patch review, 2026-11-01

Git attributes the pipeline patch to `c9be916e11daacd14cfee0e0573bf1d1c0ce6670` (commit author display name Nova Robotics; purpose: optional imports for lightweight Render scene/frame analysis), and the scheduler patch to `8186d546bbaa3ee4358249f47ba119ac16ccde4c` (same author display name). Git metadata establishes recorded attribution, not legal ownership or human authorship.

Both changes replace eager imports with `try/except ImportError` and `None` sentinels. No other differences from the pinned upstream files were found. The intended lightweight import behavior is reasonable, but the patches are **incomplete**:

- `pipeline.py` still calls optional extractor/narrator symbols without checking whether they are `None`.
- `scheduler.py` stores unavailable runtime classes as `None` and calls them without an availability check. Requesting one can produce `TypeError` instead of a useful missing-dependency message.
- Broad `ImportError` handling can hide an internal import defect as an unavailable optional dependency.
- Despite its comment, the scheduler still attempts imports at module load time; it is not true request-time lazy loading.

These are static review findings, not a passed Vindex execution test. Keep both patches and upstream MIT attribution intact. MVI/Vindex is outside the verified core release; before claiming its optional stages work, add explicit availability errors, dependency-isolated tests, and an MVI regression run in a separate scoped change. No vendor code or production service was modified during this review.
