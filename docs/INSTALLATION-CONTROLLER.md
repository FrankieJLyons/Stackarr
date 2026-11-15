# Installation controller implementation

Whole-host recovery now has a packaged, isolated Docker route described in
[HOST-RECOVERY.md](HOST-RECOVERY.md). Private `host-backup-review` plus the existing
single-use managed approval queue consistent app snapshots and both SQLite
checkpoints. The dashboard never uploads host paths or recovery keys. The local
**Recover Stackarr** entry point verifies a complete encrypted file and recreates
only absent, fixed-recipe Docker resources. A new enrollment, revoked sessions,
preserved owner/app logins and paused backup schedules complete reconstruction.
Retry verifies the exact new container identities and unshared owned volumes.

## Docker core connection slice on 17 October 2026

The controller now provides a read-only runtime check and a private Plex credential
candidate operation. Plex handoff is limited to a completed owned deployment, the
reviewed local Docker context, exact inspected container identity and bounded fixed
preferences file. Public installation status contains no credentials. Plex browser
links open `/web`.

The dashboard records the installation ID, reviewed ports and settings revision
after a successful install response. Finish connecting checks that binding, verifies
Plex from the dashboard through `host.docker.internal`, and saves the credential
encrypted. Activation and the configuration/credential save now share one database
transaction. Newer settings and existing credentials are preserved. An unclaimed Plex
server produces account guidance and stays unconfigured. Credential handoff for
older operations or an install whose response was lost does not yet have this
binding and requires a separate recovery path; no ownership is guessed.

A private Docker preview bundle now supplies the prebuilt dashboard, frozen controller
and startup helper. Its host folder dialog grants approved media roots; automated package
acceptance supplies an explicit isolated root instead of exercising the native dialog.
See [DOCKER-PLEX-PREVIEW.md](DOCKER-PLEX-PREVIEW.md) and PROGRESS.md for exact evidence.
The fixed private `app-connections` operation now returns only the checkpointed
credentials for newly owned Sonarr, Radarr, Prowlarr and qBittorrent containers whose
receipt, context, running state, mounts, image, ports, network and saved host settings
still match. The dashboard checks the exact app set and ports, verifies every API,
and saves the batch atomically. Dashboard and app-to-app routes use the Docker
Desktop host gateway; browser links use localhost. This also supports later batches
on separate owned networks. Generated qBittorrent and Arr login reveal requires the owner
password and an unchanged owned credential. Fixed `arr-logins` and `arr-login`
operations prepare initially empty Arr logins and verify a selected saved login.
Host and dashboard checkpoints are encrypted. Existing logins are preserved; reveal
never writes authentication settings. Public progress and normal browser
responses contain no credentials.

The fixed private `seerr-connection` operation uses the same receipt, context,
container and bounded-file boundary after Seerr account initialization. Its API key
may use Seerr’s printable format rather than the Arr hexadecimal format. Dashboard
handoff verifies authenticated request counts and encrypts the credential.

Fixed `installation-check`, `managed-review`, `managed-apply` and `app-backups`
operations now bridge lifecycle and maintenance to the Docker UI. Private review
references are wrapped in session-bound, single-use browser tokens. Start/stop/restart
checks the receipt again and uses an immutable container ID. App backup/restore shares
the durable action journal and installation exclusion, verifies volume labels and
exclusive consumers, and never exposes commands or archive uploads. One dashboard's
RPC requests are serialized so a status poll cannot interrupt a user action.

Configuration snapshots use reviewed downtime, chunked authenticated encryption,
SHA-256 archive checks and path/link validation. Restore verifies all archives first,
saves a separate safety snapshot, and attempts rollback on extraction failure.
Helpers have no network and mount only one exact configuration volume and private
staging folder. Media/download binds never enter the helper. Failed rollback leaves
apps stopped; controller restart marks unfinished maintenance interrupted and never
replays it automatically. The same installation/image is required. Whole-host
restore, protocol compatibility,
enrollment renewal/revocation and unattended Windows startup remain open.

Fixed `backup-policy`, `backup-policy-review`, `backup-folder`, `backup-plan-run`
and owner-protected `backup-key` operations add nightly schedules, retention and
verified second-disk storage. The native host dialog approves destination paths;
browser requests carry destination IDs only. Schedule changes use the existing
single-use reviewed-apply channel. The worker claims a due job transactionally,
avoids concurrent installation/update/restore, and retains only bounded older
scheduled copies after successful verification. Missing/corrupt external snapshots
fail before restore downtime. Queued jobs missed at restart retry once; a backup
interrupted during execution disables its schedule pending an app-state check.

The fixed `updates` read and managed update/rollback/recovery reviews now expose a
dated immutable candidate catalog. Browser inputs contain app/update IDs only,
never images or Compose. The encrypted update journal checkpoints old/new receipts,
image identities, configuration snapshots and private health/settings checkpoints.
Updates recreate one selected service with no dependencies, building or volume
deletion. Receipt file replacement and database commit are journaled separately;
reviewed recovery accepts only recorded variants and a matching owned container or
an exclusive owned configuration volume if creation was interrupted. Unfinished
operations are marked needs-recovery at startup and block other app mutations.

Authenticated health and protected configuration checks precede commit. Automatic
rollback restores the old image plus its compatible data, rather than reverting an
image against a migrated database. Manual rollback retains a safety copy and can
recover the newer image/data if the previous version fails. The packaged candidates
are same-major Linux x64 releases; major migrations and wider platform/version
coverage remain separate gates. Compatible Stackarr dashboard/controller updates
use the separate self-update supervisor described below.

## Implemented boundary

`stackarr.controller.InstallationController` wraps the existing host installer.
The Windows source launcher now creates a private enrollment, starts a loopback
host service and checks the connection from the dashboard container. The live
Docker wizard can review, install, show status and resume through this service.

The host owns its separate state directory, app image catalog and approved media
roots. A request contains selected app IDs, explicit ports and an optional folder
index with a relative child path. It cannot supply Compose, commands, images,
environment variables, credentials, arbitrary host paths or privilege settings.
The controller reserves the dashboard and private-controller ports and enforces the existing installer
checks against replacing already configured apps.

Review performs host checks and saves a planning draft only. It returns a public
plan and a private five-minute approval reference. Approval is single-use, is
invalid after controller restart or a replacement review, and checks revisions
before queuing work. Folder boundaries are checked again when approving. The
existing durable worker executes owned deployments, records failures and requires
explicit resume. Public status excludes stored credentials and raw Compose.

The approval reference is a machine-to-machine implementation detail. Users must
never be asked to find, copy or enter it. Neither the web dashboard nor its
container has Docker access.

## Private transport implemented

`controller_transport.py` adds an ASGI service factory and an asynchronous client
for folders, review, install, status and resume. Requests and responses are signed
with an independently provisioned random 32-byte key. Requests include timestamps
and unique identifiers; accepted identifiers persist across service restarts.
The service requires the configured Host header, rejects browser-origin requests,
bounds request sizes and reading time, and serializes active requests. Validation
errors do not reflect submitted input. The client checks response signatures,
disables environment proxies and redirects, bounds responses, and never silently
retries a write when a connection fails.

The Windows source launcher provisions a shared key and host-owned TLS private
key beneath `.controller/`. It mounts only the shared key and pinned certificate
read-only in the dashboard container. The host service binds `127.0.0.1:28010`;
the client reaches it through Docker Desktop's `host.docker.internal` route with
certificate validation. The private key never enters the container. HMAC remains
a separate request/response identity check. No firewall rule, Docker socket mount
or external bind is created. Docker-to-host requests require HTTPS.

Reopening Start Stackarr reuses the enrollment and starts a missing controller.
Dashboard status requests reconnect independently after a lost connection. This
source-checkout startup path requires the repository's `.venv`; the packaged
one-download launcher has not been updated. The Docker dashboard's saved wizard
now sends scoped port checks, review, install, status and resume requests through
the controller. The dashboard keeps the host review reference on the server and
binds the browser's single-use approval to the owner session and draft revision.
Folder browsing also runs on the host through the private transport. The saved
draft carries an approved root number and relative path; the host resolves that
reference again at review and install. A container dashboard does not create
host folders directly. Initial roots can be supplied by `STACKARR_CONTROLLER_ROOTS`.
The packaged wizard also offers an authenticated, empty-body `media-folder` request:
a fixed Windows folder dialog obtains the host user's selection, validates a direct
existing directory and appends a durable grant. Root numbers never shift, including
after restart. No browser-supplied path can grant host access. Cancel keeps the prior
choice. A single already approved folder is proposed in the wizard without another
selection; monitoring-only setup skips media storage entirely.
Connection loss is shown as unavailable. Completed operations provide local
browser links, while app account setup and Stackarr connection remain separate
manual steps. The saved isolated preview on port 28000 was not rebuilt; testing
used a separate disposable dashboard on port 28100.

The dashboard persists the last signed controller status in its local database.
When the controller is unavailable, it returns that snapshot with a stale flag
and last-checked time. A signed busy response is shown separately. The wizard
labels cached progress and addresses as last known, disables Resume until the
controller is available, and checks status again automatically. If an install
response is lost, the wizard discards its consumed approval token and checks
status; it does not offer an unsafe repeat approval.

On 6 October 2026, a Seerr-only wizard request through that disposable Docker
dashboard completed as `needs-setup`. The host controller created its own Compose
project and volume, the app responded HTTP 200 at `http://localhost:28007/`,
and the dashboard returned that Open link. This proves the one-app dashboard to
host path on this computer; it does not prove initial Seerr account setup, app
connection, media import or a fresh-machine installer. A separate Uptime Kuma
attempt reached container startup but failed with `exec format error` in its
pinned image; its failed operation and volume were preserved. Do not present
Kuma as runtime-verified yet.

A second isolated host-controller batch on 6 October added Prowlarr at port
28005 after Seerr was already recorded as installed. Both apps returned HTTP
200; Seerr's container ID and saved integration settings were unchanged. The
wizard now offers a fresh **Add another app** selection after a completed
operation and prevents choosing that installed app again. This live second
batch exercised the host controller directly; the new button has not yet been
run against a live Docker dashboard, although a synthetic browser check covered
the button and exclusion of the installed app. Both test-owned app containers were
stopped after verification, with their volumes retained.

On 7 October, a new isolated dashboard and host controller exercised recovery
through the authenticated Docker API. A deliberate failure before Seerr's
Docker pull was resumed after the client closed; Seerr reached `needs-setup`
and returned HTTP 200. A later Prowlarr operation was paused immediately before
pull, then its exact test controller process was stopped. The dashboard showed
the cached running state as stale. Restarting only the disposable dashboard
preserved that snapshot. Restarting the controller marked the operation
`interrupted`; an explicit Resume completed it to `needs-setup`, and Prowlarr
returned HTTP 200. Seerr's container ID and saved settings did not change.
Only test-owned containers were stopped afterward; volumes, controller state
and receipts were kept. The original preview and unrelated containers were
not altered. This injection tested interruption before pull. It did not test
recovery from a partial image-layer download.

## Remaining connection work, in order

1. Complete packaged launcher startup, enrollment renewal/revocation and
   automatic service recovery. Verify the connection inside a newly built
   dashboard container, including after both sides restart.
2. Add guided host folder sharing, storage checks and a native chooser for media
   apps. Verify approved folder mapping from a Docker dashboard to a fresh host.
3. Deliver supported credentials privately and idempotently. Distinguish host
   loopback URLs, browser URLs, container-reachable URLs and inter-app URLs. Existing
   apps stay outside the controller's ownership. Never replace dashboard edits
   made while an installation was running.
4. Verify recovery from a partial image-layer download, occupied ports and
   unwritable storage in the real Docker path. Diagnose the pinned Kuma image
   failure before claiming optional-app support. Only then expand to Arr wiring
   and all optional apps. Preserve unrelated containers and the synthetic-media
   sentinel throughout.

## Verification for this slice

23 controller tests cover hostile inputs, paths, reserved/duplicate ports,
read-only review, expiry, approval replay/replacement, revision conflicts,
pending-install exclusion, and delegation to the existing worker. Worker calls
are mocked: these tests are not evidence of a live container installation or a
live network binding. Fifteen additional transport tests cover authenticated
review/approval/status, tampering, key mismatch, expiry, request replay across
restart, response replay, direct browser requests, invalid destinations, size
limits, busy/error handling, and connection loss without automatic retry. These
use in-process HTTP transport and mocked Docker calls. Seven new enrollment tests
cover stable keys, partial state, required TLS, dashboard status and graceful
failure, a real TLS listener, and a plain-language probe error. The full local
suite passed: 276 tests, three Windows filesystem-link skips. A read-only socket
check from the verified
isolated preview reached a temporary host controller bound to `127.0.0.1` via
`host.docker.internal` (Docker Desktop's internal gateway). A separate bounded, disposable
container on that network completed pinned TLS and signed status against the
controller; it was removed. A newly built disposable dashboard with tmpfs-only
state reported `connected`, then `unavailable` when the host controller stopped,
then `connected` after it restarted through its authenticated API. That
dashboard was removed; the saved preview image was not rebuilt, and no app was
installed from its wizard. Existing installer integration tests remain
applicable.

## Stackarr self-update transport

The signed, pinned-TLS transport exposes fixed `stackarr-probe`,
`stackarr-updates`, `stackarr-package`, `stackarr-update-review` and
`stackarr-update-apply` operations. Package choice has an empty browser DTO and
opens the host's fixed native ZIP chooser. Browser review carries only an action
and optional saved job ID. Approval resolves an expiring, one-use host reference;
the dashboard also binds its review token to the authenticated session and CSRF.
No executable path, command, Docker image or Compose document is accepted from the
browser. The private probe returns only protocol, checking mode, PID and digests.
It never returns account hashes, session tokens, encryption keys or credentials.

An independent known-source supervisor coordinates a cooperative controller stop
bound to the pending job and probed process ID. Candidate controllers use sibling
copied state, disable background app jobs and admit only the maintenance/read
allowlist. All app mutation workers defer while Stackarr maintenance is pending.
Reopening the managed package recovers the previous release after interruption.
The real packaged Docker evidence and recipient steps are in
[SELF-UPDATE.md](SELF-UPDATE.md).
