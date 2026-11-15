# Architecture

`seerr_storage.py` runs during new-install configuration. Existing maintenance
ownership checks verify the exact running container, recipe and exclusive local
config volume. Fixed Node probes run as Seerr's normal user, create a unique file,
write/fsync/read it back, remove it and fsync the directory. After container and
resource reinspection, only an empty regular single-link `DOCKER` image marker
may be cleared. Unknown markers or changed/shared/unwritable storage fail with a
fixed redacted message. No image, schema, volume-layout or existing-installation
migration is introduced.

`static/setup_accounts.js` renders selected-app account steps and a clipboard/
manual-copy fallback using saved app addresses. It does not broker Plex OAuth,
collect Plex passwords or transfer saved account tokens. The upstream Seerr page
owns its Plex authorization window; Stackarr verifies completion through its
existing private owned-app connection handoff. See [SEERR-SETUP.md](SEERR-SETUP.md).

`docker_networks.py` bounds read-only local pool/network inventory, estimates free
IPv4 subnet slots and reports uncertainty without allocating probes or disclosing
raw inventory. Runtime checks and installation preflight use the same calculation.
`docker_failures.py` maps known engine/registry errors to fixed public messages;
network-capacity failures survive the startup error boundary.

Approved installs create `deployment_steps` metadata lazily. Its durable download
phase produces an explicit retry after controller restart without changing an idle
older installation during candidate verification. Only immutable pulls retry;
complete digest/platform checks precede app storage/startup and `up --pull never`
prevents an untracked second download. Receipts, selected images, paths and ports
stay unchanged across resume. See [NETWORK-DOWNLOAD-RECOVERY.md](NETWORK-DOWNLOAD-RECOVERY.md).

Stackarr is a small server application plus a browser client. The server owns validated versioned settings, encrypted credentials, sessions, audit events, redacted backups, and read-only collectors. Normal browser responses contain no credentials; an explicit owner-password-protected action can reveal the generated qBittorrent or Arr login briefly. The browser does not call third-party APIs directly.

The first deployment target is a least-privilege Docker Compose project. The Stackarr container has no Docker socket, drops Linux capabilities, is read-only, binds to loopback by default, and mounts only its own state volume. The generated application plan is separate and scoped to a named Compose project. It never prunes volumes or touches unrelated containers.

New Docker projects use `stackarr-controller` and `stackarr-apps`, with short
numbered suffixes for names reserved by other containers, networks, retained
volumes or saved deployment receipts. The dashboard container is named after its
controller project. App project names are saved in the approved deployment
receipt and used consistently by inspection, maintenance, backup, updates and
host recovery. Older receipts retain their original `stackarr-owned-<id>` names.

Collectors run independently with bounded timeouts and one retry. A failed collector has `unavailable` state and its last successful snapshot remains marked stale; a failed request is never serialized as an empty array. Configuration revisions prevent an old collection from being written after a settings change. Destructive recovery, download deletion, replacement search, and blocklist cleanup are disabled in this alpha.

The application is intentionally split into `config.py`, `store.py`, `integrations.py`, `wiring.py`, `installer.py`, and `server.py`. `wiring.py` is action-capable but is only reached through an explicit preview/apply endpoint and uses the target app's advertised schema and test endpoint. Seerr adds a private owned-app handoff and reviewed Arr request-service connections through its verified v3 API. Broader installation detection remains planned. The original PowerShell/Python snapshot remains outside the distributable package and is not called by Stackarr.

Future host operations are separated from the web service. NAS support will use an optional allowlisted host agent, and Docker discovery will use a scoped proxy rather than a raw Docker socket. Backup destinations are modeled as local, NAS, or S3-compatible targets with checksums and restore tests.

The Docker preview uses a separate local installation controller over pinned TLS
and signed requests/responses. The dashboard can request fixed installation and
readiness operations; only the controller has host Docker access. Plex and the four
core download/Arr apps use separate private credential operations with owned
container, port, deployment and settings-revision checks. The candidate is verified
from the dashboard and encrypted there. Configuration, credentials and completed
handoff state are saved in one transaction. App-to-app connections are reviewed and
tested separately; gateway addresses let later installation batches reach earlier apps.
The packaged helper provisions enrollment and an approved media root; its state is
outside the extracted bundle. See INSTALLATION-CONTROLLER.md for remaining scope.

The native Windows preview has its own plan-first runtime deployer under `platform/windows/`. It stages a versioned, machine-owned payload and switches a `Runtime` junction only after validating the stage. It preserves the previous target for rollback. It reports existing Stackarr-named tasks but does not adopt, edit, or delete them. This separation protects boot-before-login behavior and prevents a production task from depending on a development checkout.

Storage Guard is represented as a validated policy: a selected path, pause/resume watermarks, and the two explicitly managed Arr categories. It is not an active host operation in this preview. Any later adapter must record its own pause marker, resume only marked items, preserve manual torrents and partial downloads, and never delete media.

Generated Arr web logins have a separate encrypted host checkpoint and dashboard
handoff table. Initial setup changes only an unconfigured owned app; later owner
logins are preserved. Reveal performs a read-only ownership check and a fresh normal
forms sign-in before returning the selected credential after owner-password approval.
`indexers.py` uses Prowlarr's advertised Torznab schema and test endpoint, with
single-use session review, settings revision checks and duplicate preservation.
Provider keys stay out of ordinary browser responses, audit messages and screenshots.

`seerr_wiring.py` creates only missing Sonarr/Radarr services, showing the selected
existing profile and root folder in the review. It checks Seerr v3 compatibility,
uses its test endpoint, verifies returned profiles/folders, checks settings revisions,
preserves existing entries and verifies save readback. Lost responses never trigger
an automatic retry; re-preview preserves an existing entry. Collectors remain read-only
and keep Seerr's Available and Completed request counts distinct.

`lifecycle.py` and `app_backups.py` share a durable, exclusive action journal behind
fixed private controller operations. The dashboard never obtains a Docker socket
or a general command proxy. Lifecycle changes use receipt-verified immutable IDs.
Backups stop selected running apps, archive only their exclusive configuration
volumes, encrypt snapshots and restart the prior running set. Restore validates all
archives before downtime and saves a separate safety copy before replacing app
configuration. Extraction failure rolls back; failed rollback keeps apps stopped.
Media/download folders are never mounted by archive helpers. Active dashboard and
controller settings remain in place; whole-host migration is separate work.

`backup_policy.py` owns an encrypted schedule, host-approved destination references
and verified-copy records. The controller worker atomically claims due nightly
jobs in the same exclusive action journal. Retention applies only to scheduled
snapshots after verification; manual, safety and update recovery copies remain.
Windows physical-disk metadata verifies the separate destination, a native host
dialog grants its path, and a namespace ownership marker bounds exact-file cleanup.
Authenticated manifests allow a registered snapshot to restore from its external
copy when local archives are missing. Recovery-key export requires the dashboard
owner password and crosses only the enrolled private controller channel.

`updates.py` couples an allowlisted immutable image to an encrypted configuration
snapshot. Its durable journal records both receipt variants before replacement,
plus the snapshot and private settings/health checkpoint. Only one reviewed service
is recreated. Three authenticated health checks and protected library/settings
readback gate commit. Rollback restores a compatible image/data pair; manual rollback
first saves newer settings. Interrupted receipt-file/database commits require an
explicit recovery review and are never replayed at startup. Browser requests cannot
provide images, commands or Compose. Candidate metadata is packaged separately in
`updates.lock.json`; major migrations remain separate work.

The catalog covers all nine apps, and the dashboard update request contract is
checked against that full set. `companion_maintenance.py` reads actual companion
releases and protected configuration using authenticated APIs/Socket.IO. Seerr's
checkpoint includes actual Arr paths and bounded pagination of users/requests.
New Seerr checkpoints also protect Plex account identity, user permissions and
sign-in/admission settings. Encrypted update runs and repair records retain their
checkpoint version so older runs remain recoverable with their original field
shape. Only the advancing library `lastScan` cursor is omitted from new comparisons;
library selection and other settings remain protected. See
[SEERR-PLEX-MAINTENANCE.md](SEERR-PLEX-MAINTENANCE.md) for real-account acceptance.
Whole-host recovery also passes with a claimed Plex identity, Seerr's Plex owner,
Tautulli's login/server connection and their Arr dependencies. It reconstructs
fresh volumes from the complete encrypted checkpoint, retains original lab
resources, verifies partial-write recovery in a fresh packaged process and
regenerates Stackarr enrollment while revoking its old sessions. See
[HOST-RECOVERY.md](HOST-RECOVERY.md) for the same-computer Docker boundary.
Candidate companion login checks use the reviewed candidate recipe before receipt
commit. Only Cleanuparr's reviewed, exact inactive new-option default is normalized
across the tested versions. Plex updates reuse the same verified scratch-volume
identity as repair; unknown additional mounts still fail closed. See
[OPTIONAL-APP-MAINTENANCE.md](OPTIONAL-APP-MAINTENANCE.md) for acceptance boundaries.

`self_update.py` manages compatible packaged Stackarr dashboard/controller releases.
It validates an allowlisted ZIP, stages immutable payloads and launches a known
working native supervisor with its own PyInstaller runtime. A flat durable journal
survives database replacement. Only Stackarr pauses: encrypted SQLite checkpoints,
an entire dashboard-volume snapshot and retained source releases support recovery.
The candidate uses a new named dashboard volume and sibling controller state with
app jobs disabled. Pinned TLS, executable/image identities and logical settings/key
fingerprints gate promotion. Manual rollback authenticates its checkpoint before
downtime, rejects changed app topology/credentials and retains the current owner
and sessions. Managed startup follows the committed release or recovers pending
maintenance. It never updates or restores app volumes or media. See
[SELF-UPDATE.md](SELF-UPDATE.md) for compatible-schema and unsigned-package limits.

`self_repair.py` reuses that supervisor for the same saved release. An authenticated
first browser review can verify/adopt its working owned runtime; offline local
review requires the saved runtime record. Strict container, volume, network,
enrollment and idle-app checks precede an encrypted checkpoint. A new dashboard
volume and controller state copy must preserve accounts, keys, settings and
backup/configuration files before promotion. Missing keys or unknown storage
require explicit recovery rather than an automatic reset.

`runtime_storage.py` checks free space and durable create/write/replace access
before downtime. Release staging commits a complete verified temporary directory;
journal writes preserve their last committed version on failure. Checkpoints are
authenticated before startup. Storage or port failures that also prevent recovery
retain pending maintenance for a fresh packaged retry. See
[RUNTIME-REPAIR.md](RUNTIME-REPAIR.md) for exact failure tests and boundaries.

`app_maintenance.py` handles reviewed per-app container repair and removal. It
rebuilds the fixed receipt recipe, verifies immutable images, complete environments,
unshared local volumes, the owned network and direct existing media roots. Before
removal/recreation it stops only the selected app and verifies an encrypted
configuration snapshot. A temporary one-service Compose plan references existing
volumes/networks externally and uses `--no-build` and `--pull never`. Running or
missing apps use `up --no-deps`; an existing stopped app uses `create` and never
starts its background jobs. Container removal uses an immutable ID without force
or volume deletion. Plex's image-declared anonymous `/transcode` cache is retained
by its verified exclusive volume identity and reused externally; unknown, shared
or host-bound extra mounts are rejected.

The existing action journal stores operation phases, snapshot references and only
digests of protected settings. Startup marks interrupted maintenance as needing
reviewed recovery; it never replays a removal. Candidate labels bind recovery to
the exact operation. Failed repair retains a separate candidate-settings snapshot,
restores its earlier configuration and recreates only the reviewed app. Pending
recovery blocks other mutations and scheduled jobs. Backup review can include an
absent app only after verifying its retained volume has no consumers; restore
requires its container to be repaired first. No new database schema is required.

`self_removal.py` uses the same independent supervisor, flat journal and exclusive
worker lock as Stackarr updates. Removal verifies the exact dashboard identity,
immutable package/image, full environment and security settings, exclusive local
volume, network and enrollment. After pausing only Stackarr, it verifies an
encrypted full-configuration checkpoint before removing the immutable container
ID without force or volumes. A removed-state marker and deliberate non-Compose
receipt prevent both new and older launchers from silently reinstalling it.
Retained-data jobs use a separate active pointer and legacy-compatible terminal
status, so older update supervisors cannot replay removal/reinstall as an update.
The controller verifies its own executable locally during a review instead of
recursively acquiring its private RPC lane. Execution rechecks stopped/absent
container expectations and occupied ports immediately before downtime or creation.

`reinstall_wizard.py` provides a native review while the dashboard is absent.
Approvals are encrypted, expire in five minutes and are claimed once by atomic
rename. Reinstall uses copied controller state and a new dashboard volume; logical
account/settings/credential fingerprints, keys and backup/configuration-file
content hashes gate promotion. Failed/interrupted reinstall retains the candidate
volume and recovers the original removed state. Interrupted removal resumes the
original container if deletion never completed, or records completed removal
without repeating deletion. Neither path changes media apps or app volumes.

`install_ports.py` recovers a failed final-start bind inside the same deployment.
It rebuilds the fixed app recipe and verifies partial container identity,
environment/security options, exclusive config volumes, network and media mounts.
A never-started created container can have no network attachment only when its
exact saved `HostConfig.NetworkMode` still identifies the private project network.
Running apps receive no lifecycle command or address change. Unstarted apps get
an operation generation label, including original-address resume, so Docker
recreates failed-bind containers with the retained volumes and restores actual
network/port bindings. qBittorrent's published/target/environment web ports match.

The existing deployment payload holds a format-1 source/target transition and
resource fingerprints. Approval queues that exact transition atomically before
the worker replaces the recipe file. Resume accepts only recorded recipes and
verified generation replacements; unknown/renamed containers or changed/shared
volumes fail closed. The fixed `install-ports` controller operation uses the
existing owner/CSRF/session-bound expiring single-use approval protocol. Trusted
status updates only known unactivated dashboard handoff ports, repairing lost
approval responses without replacing saved active connections. No new database
schema, arbitrary Docker command or recipient fault switch is introduced.
