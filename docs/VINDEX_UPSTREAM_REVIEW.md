# Vindex upstream provenance check

**Checked:** 2026-11-01

- Candidate upstream: https://github.com/vaibhav-space/vindex — public repository titled **vindex**, describing itself as an open-source video knowledge compiler.
- The upstream README identifies the project as MIT-licensed. The copy vendored at `apps/mvi/vendor-evaluation/vindex/` contains an MIT license attributing copyright to **Vaibhav Dubey (2026)**.
- The upstream project and vendored package both describe a local-first video compiler with structured artifacts, and the vendored package metadata declares MIT.
- **Not yet verified:** file-by-file identity, exact upstream commit or tag, whether local modifications were made, and any additional third-party asset notices. The matching project description and license do not establish a cryptographic source match.
- This is an **evaluation vendor copy**, not original AI-OS intellectual property. Its license must be retained, and the README should not imply it was created by the AI-OS author.
- **Important package-name collision:** https://pypi.org/project/vindex/ currently describes a different project associated with `dripston/vindex`. Do not assume `pip install vindex` installs the `vaibhav-space/vindex` project. Use a verified source URL and pinned revision if integration is later approved.

**Release disposition:** preserve the vendored license and treat the upstream origin as provisionally identified. Verify exact source commit and file differences before declaring provenance complete.
