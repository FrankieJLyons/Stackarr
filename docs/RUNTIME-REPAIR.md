# Stackarr runtime repair and storage recovery

Open **Settings → Stackarr updates & rollback → Review Stackarr repair**, then
approve **Repair Stackarr**. Repair recreates only the Stackarr dashboard and
restarts its private controller using the same saved release. Media-app containers,
configuration volumes and media folders are never repair targets.
The first review can prepare a verified runtime record through the authenticated
controller; a separate status-check step is unnecessary. An offline local review
still requires an existing verified runtime record.

If the dashboard cannot open, first restore Docker and access to the Stackarr
state folder, then reopen **Start Stackarr.cmd** from a repair-capable package.
When normal managed startup fails, the helper opens a local repair review. The
review is encrypted, expires after five minutes and can be approved once.
An installation intentionally removed through Stackarr still requires **reinstall**.

Repair requires the saved release, intact account/encryption keys, exclusive
configuration volume, original private network and verified controller enrollment.
It supports a stopped or missing dashboard, stopped controller and a damaged
generated Compose file when the saved runtime recipe remains valid. Changed
containers, mounts, privileges, shared volumes, occupied saved ports or missing
keys/settings block repair. Restore lost configuration with whole-host recovery;
repair never creates a replacement account or adopts unknown storage.

## Preservation and failure handling

Review prepares the verified bundled image cache, checks local state storage for
available space and safe create/write/replace operations, and reads consistent
SQLite checkpoints through a read-only volume helper. Approval repeats ownership,
settings, account, key and storage checks before downtime. App installation,
maintenance or recovery jobs must finish first.

An independent packaged supervisor stops only the authenticated Stackarr controller
and owned dashboard. It verifies an encrypted checkpoint, starts a candidate on
new configuration storage, then checks the same release, account, settings, keys
and backup/configuration files. Promotion preserves the current password and
sessions. Original storage and the encrypted checkpoint remain available.

Release staging uses a temporary directory and an atomic commit. Failed copies
do not publish a partial release. Durable journal writes likewise keep the last
committed record when storage rejects replacement. Encrypted checkpoints are
authenticated and verified before candidate startup.

If space or permissions fail before downtime, repair cancels with existing settings
and running apps retained. If failure happens during candidate extraction or
startup, recovery brings back the original release and settings. If storage or a
saved port also prevents recovery, the operation stays pending: restore access or
free the port, then reopen the same repair-capable package. Startup recovers from
the retained checkpoint before ordinary operation. It does not retry app operations
or reset data to make the error disappear.

## Maintainer acceptance boundary

`tools/docker_runtime_repair_check.py` uses only
`test-results/docker-runtime-repair-20261018-r2`, with a separate dashboard/controller,
fresh Sonarr/Radarr volumes and copied original sample media. The existing main
installation is fingerprinted before testing and excluded from every repair target.

The matrix exercises packaged browser review/apply, one-use frozen local approval,
offline/missing dashboard recovery, damaged Compose regeneration, an actual read-only
candidate mount, a 64 KiB candidate filesystem that returns ENOSPC, a Windows
exclusive-file write denial, real candidate database writes, an actual worker exit,
fresh packaged recovery, release-admission retry and a late exclusive-port conflict.
Unavailable Docker is simulated only at the lab adapter boundary; the shared Docker
engine is never stopped. Real disk-full tests fill only the tiny disposable target,
not the host disks or existing application volumes.

Native-window walkthroughs, replacement Windows, lost encryption keys, corrupted
account databases, missing/changed enrollment and unknown storage remain separate
recovery/support boundaries. The same-release repair path does not certify major
state migrations or Docker Desktop reinstallation.

## Completed Docker acceptance — 18 October 2026

The final **Stackarr-Docker-Runtime-Repair-Preview-20261018-r2** package passes all
ten cases:

| Case | Verified result |
| --- | --- |
| First packaged browser repair | Verified runtime prepared without a prior status click; current session retained |
| Stopped dashboard and controller | Frozen local approval brings both back; replay of approval rejected |
| Missing dashboard and damaged Compose | Runtime reconstructed from the verified saved recipe |
| Read-only candidate storage | Actual extraction write denied; original runtime recovered |
| Full candidate storage | Actual ENOSPC after 61,487 candidate bytes; original runtime recovered |
| Windows file lock after candidate writes | Recovery waits for restored write access; fresh package restores the original |
| Worker exit after candidate writes | Durable pending operation recovered by a fresh packaged process |
| Release-admission write denial | Previous active release retained; retry succeeds after releasing the lock |
| Unavailable Docker adapter | Review refuses before downtime; shared Docker engine remains running |
| Port taken after preflight | Recovery waits for the exclusive listener to close; fresh startup restores the original |

The lab's two app container IDs, settings, generated logins, Stackarr account,
keys, backup/configuration files and three original media copies match the baseline.
Final acceptance freshly authenticates all nine main integrations and verifies
unchanged main containers, settings, credentials, nightly policy and 16 tracked
media/data files. The main dashboard/controller stay on Self-Removal r4.

Only this task's lab containers/networks and abandoned plaintext work directories
are removed. All configuration volumes, media, keys and encrypted checkpoints are
retained. Native approvals use the actual frozen executable interfaces; a human
walkthrough of the local window remains open.

Validation: **530 passed, 3 existing Windows filesystem-link skips**, **18 frozen
smoke checks outside the checkout**, Ruff passed, and **245 portable source files,
0 audit findings**. Nine package entries/eight payload hashes verify.
Image: `sha256:1f42e159fdb9c33f935deb3d56517f4cb2c9dd21f598d88c1bb098296b63a4d2`.
ZIP SHA-256: `5dab88989317c0dafd1f6192aea7067c179852882a02bd7e3267dedb355d0a31`.

Private evidence: `test-results/docker-runtime-repair-20261018-r2/cases.json`,
`acceptance.json`, `main-authenticated-monitoring.json`, `package-verification-r2.json`,
and `runtime-repair-browser-review.png` / `runtime-repair-browser-results.png`.
Regression/smoke records: `test-results/runtime-repair-regression-r2.xml` and
`test-results/runtime-repair-frozen-smoke-r2.json`.
