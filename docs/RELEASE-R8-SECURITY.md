# R8 publication security review — 20 October 2026

This release belongs in the existing **private** development repository. The
[public-source boundary](PUBLICATION.md) still applies; no history was rewritten
and repository visibility was not changed.

## Checked publication payload

- Gitleaks 8.30.1, downloaded from its official release with checksum verification,
  scanned reachable Git history: **86 commits, no credential findings** before
  the release commit. The staged release source was scanned separately.
- The repository's portable-source audit reports **zero findings**. Machine-bound
  acceptance harnesses remain in ignored local storage, alongside private test
  evidence, rather than entering Git or source exports.
- R8's ZIP, all 35 embedded image blobs, decoded image layers and constants from
  70 bundled Stackarr Python modules were inspected. No private build paths were
  present in the compiled project code.
- A separate read-only comparison against **42 locally stored credential values
  across 19 state stores** found **zero matches** in source, release payloads,
  decoded executable constants or image-layer file contents. The scan inspected
  over 62,000 files; no private application-state entries were found.
- Adjacent ignored legacy exports were scanned and had no credential findings.
  Existing installation state and private test/recovery data remain local and
  excluded from publication. They were not deleted or uploaded.

Raw layer-scanner findings were reviewed, rather than silently suppressed. They
were limited to Python's public signing-key fingerprint, pinned source checksums,
Seerr's publicly distributed catalog-service constants and test fixtures,
framework build identifiers, a C++ constant and crypto format-marker strings.
Flagged upstream source files matched Seerr's exact public v3.5.0 source; the
flagged JavaScript chunks contained no complete private keys. None were local
account credentials. Private audit reports and all credential values stay local.

The source scanner has one narrowly scoped exception: the exact SHA-256 of the
pinned upstream `api/plexapi.js` file in `platform/seerr/upstream.lock.json`.
That integrity checksum is not an API key. Other findings still fail the scan.

## Ongoing boundaries

CI runs a checksum-pinned Gitleaks scan of source/history, with redacted output.
Source exports exclude runtime databases/keys, environment overrides, private
JSON/JSONL evidence, and local cloud/SSH/agent configuration directories. Browser
artifacts use explicit synthetic-test paths instead of recursive catch-all paths.
Git ignore rules provide an additional boundary; ignored files are not release
inputs. The main installation remains unchanged.

## Exact uploaded build

- File: `Stackarr-One-App-Preview-20261020-r8.zip`
- Size: **342,555,645 bytes**
- SHA-256: `fb0335fba892bb668c91a498a420e790339c2ba94a7804051433a32a6e63b31b`
- Image: `stackarr:auto-import-20261020-r2`
- Package verification: eight payload hashes, nine ZIP entries, 35 image-blob
  hashes and a matching Windows executable.

R8 is an unsigned engineering prerelease built from the audited development
working tree before its publication commit. Its manifest records that provenance.
Security publication cleanup changes fixtures, packaging boundaries, CI and
documentation; it does not replace the already tested R8 product binaries.
See [automatic import acceptance](AUTOMATIC-IMPORT-TEST.md) for functional evidence
and remaining clean-machine, second-device and existing-stack replacement gates.
