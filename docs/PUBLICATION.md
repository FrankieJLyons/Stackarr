# Public-source boundary

## Decision

The public beta lives in `FrankieJLyons/Stackarr`, starting from an audited clean
export with no inherited development history. Version 0.1.0 is an unsigned beta;
see [acceptance scope](BETA-0.1.0.md). The procedure below remains the boundary
between private development material and public release inputs.

`FrankieJLyons/MyMediaStack` remains a private archival and development repository. Its reachable Git history includes the original sanitized Windows deployment snapshot. This is useful private project context but not an appropriate public source history.

When Stackarr is ready for public release, create a **new public repository** from an audited clean export of the portable branch. Do not make this repository public, and do not mirror its Git history into the public repository.

## Clean export procedure

1. Start from the approved portable commit in this private repository.
2. Verify the current tree has no `outputs/` directory, runtime state, test screenshots, `.env`, certificates, private keys, databases, media, or downloaded payloads.
3. Run `python tools/audit_source.py --working-tree`. It must report zero findings.
4. Run all release checks, then build the source ZIP with `python tools/package_release.py`.
5. Inspect the ZIP file list. It must not contain `outputs/`, `history-audit.json`, private runtime state, secrets, certificates, or generated test artifacts.
6. Initialize the public repository from the inspected export as its first commit. Add the Apache-2.0 license, third-party attribution, security policy, contribution guide, support matrix, and release documentation.
7. Re-run CI in the new repository before enabling public issues, releases, images, packages, or pages.

## Boundaries

- The public repository contains Stackarr product source, tests, supported platform installers, documentation, and license notices only.
- Historical deployment scripts remain available only in the private archival repository, never in release packages or public Git history.
- GitHub Actions runs the current-tree audit and fails when it finds a private path, private address, legacy hostname, private key, GitHub token, or credential assignment.
- The heuristic audit is not proof of absence. Every release still requires human review of generated artifacts and changed files.
- The R8 private prerelease was checked separately across source, history,
  decoded image layers and compiled project constants; see
  [RELEASE-R8-SECURITY.md](RELEASE-R8-SECURITY.md). Local installation credentials
  and private test/recovery evidence remain outside Git and release assets.
