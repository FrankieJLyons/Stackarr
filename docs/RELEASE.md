# Release checklist

This repository remains private. Its Git history includes the original sanitized deployment snapshot, which is not suitable for a public project history. The public-release strategy is a new repository initialized from a clean, audited export of the portable source; do not change this repository's visibility.

Before a release:

- Review `docs/history-audit.json` as evidence that this private repository's historical snapshot must not be published. The current branch must have no `outputs/` directory.
- Confirm the clean source export and source package exclude historical audit reports, runtime databases, test screenshots, credentials, certificates, media, and downloaded payloads.
- Pin and review upstream container image digests, confirm their architecture manifests, and re-check licenses and logo attribution.
- Run `ruff`, the complete pytest suite, the browser smoke test, `pip-audit`, package build, and Docker build on both x86-64 and ARM64 builders.
- Run the Compose plan in clean disposable environments for fresh install, connect-only, mixed install, restart, failed credential, occupied port, permission, interrupted apply, rollback, and preserved-volume scenarios.
- Verify LAN HTTPS behind a real reverse proxy, allowed-host behavior, secure cookies, certificate trust guidance, notification delivery with the browser closed, and automatic startup after reboot.
- Exercise the native Windows runtime plan, staged apply, rollback, uninstall preservation, and a reboot-without-login test in an isolated Windows environment before calling that path supported. Confirm it does not alter autologon or adopt an existing app task/service without a separately reviewed migration.
- Review every external write in `wiring.py`; keep recovery, deletion, replacement search, update, and host-management actions disabled until they have their own preview, permission, audit, and rollback design.
- Verify installation detection never treats an open port as proof of application identity, never imports secrets silently, and never overwrites an existing app configuration. Test install, connect-only, mixed, and Seerr companion flows separately.
- Build the wheel and source archive, inspect their file lists, generate checksums, and create a private release draft. Do not publish the repository, images, packages, or remote history as part of this checklist.

The source packager scans the exact export manifest, including root files and CI
workflows, before writing an archive. It rejects linked inputs and excludes runtime
databases, SQLite sidecars, local environment files, keys, logs and caches. Fixed
ZIP timestamps and permissions make repeated archives of identical source bytes
identical; this does not yet claim bit-for-bit reproducible Windows executables.
The heuristic source scanner is a gate, not proof that all private data is absent.
