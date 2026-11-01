# Vindex upstream provenance check

**Checked:** 2026-11-01

- Candidate upstream: https://github.com/vaibhav-space/vindex — public repository titled **vindex**, describing itself as an open-source video knowledge compiler.
- The upstream README identifies the project as MIT-licensed. The copy vendored at `apps/mvi/vendor-evaluation/vindex/` contains an MIT license attributing copyright to **Vaibhav Dubey (2026)**.
- The upstream project and vendored package both describe a local-first video compiler with structured artifacts, and the vendored package metadata declares MIT.
- **Not yet verified:** file-by-file identity, exact upstream commit or tag, whether local modifications were made, and any additional third-party asset notices. The matching project description and license do not establish a cryptographic source match.
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
