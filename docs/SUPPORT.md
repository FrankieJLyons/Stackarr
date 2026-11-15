# Support matrix

For the current 0.1.0 public beta, use the [beta acceptance checklist](BETA-0.1.0.md)
and root README. The detailed reports below are historical engineering evidence,
not clean-machine, unattended-startup or household-network certification.

The [Seerr security backport](SEERR-PERMISSIONS-FIX.md) closes the earlier Manage
Users finding in Seerr 3.5.0-stackarr.1. Both native and packaged Docker tests pass
40 permission checks, including protected profiles, delegation limits and atomic
batches. Real browser login/replacement and the normal 3.5.0 security update pass
with settings, users, requests and authorization retained. Existing main apps
are unchanged and need a separate reviewed update to receive the fix.
[Plex membership/revocation](SEERR-PERMISSIONS.md) remains simulated by the owner's
choice; sharing/token revocation alone leaves an existing Seerr session valid.
No real invitation or sharing was changed. All nine main connections,
settings/credentials/backup policy and 16 files are preserved.

Fresh [Seerr setup](SEERR-SETUP.md) verifies owned persistent settings storage
and durable writes before clearing the empty image marker responsible for its
misleading mount warning. Unexpected markers and denied/shared storage stop setup
with settings retained. The package shows selected-app account steps, exact Seerr
buttons and a copy/manual-copy usual-browser fallback. Real authorization-window
handoff and blocked-popup behavior pass in Docker. The owner also completed fresh
Plex sign-in in a usual browser and confirmed the session survived replacement of
the new Seerr container. Private handoff, selected test library, fresh authorization
and settings persistence pass. Broader browser/server-library-selection walkthroughs
remain separate; this case uses the already claimed isolated Plex test server.

Final app-start [port recovery](STARTUP-PORT-RECOVERY.md) uses reviewed new
addresses for unstarted apps while retaining the same project, configuration
volumes, images, media and healthy app containers. Original-address resume also
recreates failed-bind containers with their retained volumes, checking published
bindings before connection setup. Changed/shared resources block recovery.
Six native scenarios and three packaged runs pass using real Prowlarr/qBittorrent
images and the frozen controller/browser, including the final r4 artifact.
No existing app is an update or fault target; all nine main connections and
16 original media/data files are verified unchanged.

Docker [network diagnostics and download recovery](NETWORK-DOWNLOAD-RECOVERY.md)
have six real nested-engine cases plus packaged older-release promotion and a
real frozen-controller registry-failure/browser retry. Only the nested daemon's
two-range pool is exhausted. Original image fixtures exercise partial-body cuts,
registry access failure, actual worker/CLI exit, fresh-process resume and offline
cache reuse. This tests download/engine handling, not upstream Seerr accounts.
Main apps/settings/media are preserved; default pools are never changed or pruned.
Capacity is an estimate that excludes host routes and concurrent changes.

Stackarr [runtime repair and storage recovery](RUNTIME-REPAIR.md) passes ten
isolated Docker cases with the packaged dashboard and frozen Windows controller.
Coverage includes first-use browser review, offline/missing-dashboard repair,
damaged generated Compose, actual read-only and full candidate storage, Windows
file locks, actual worker exit, fresh-process recovery, release-admission retry and
a late dashboard-port conflict. Existing main apps, media and settings are verified
unchanged. Unavailable Docker is simulated only at the lab adapter boundary;
the shared engine and host disks are never stopped or filled. Repair needs intact
keys, account, enrollment, verified runtime metadata and the original private
network. Missing/shared/unknown storage requires inspection or whole-host recovery.
Native-window and replacement-Windows walkthroughs remain separate gates.

Whole-host configuration recovery has isolated nine-app Docker acceptance in
[HOST-RECOVERY.md](HOST-RECOVERY.md): complete encrypted account/controller/app
checkpoints, empty-resource reconstruction, a fresh-process retry after partial
extraction, preserved logins/settings and unchanged media. A separate five-app
follow-up also passes claimed Plex, real Seerr Plex-owner and Tautulli account
recovery with Sonarr/Radarr dependencies. Original lab volumes remain intact and
stopped; only fresh source volumes are removed. Native recovery-dialog walkthroughs,
replacement Windows and revoked/shared-user credentials remain separate gates.
Complete host files are manually
prepared; scheduled app snapshots do not automatically refresh them.

This table describes the private alpha. Most checks use synthetic API fixtures and
the disposable browser environment. The [Docker lab](DOCKER-LAB.md) records the
specific real upstream versions, connections and restart checks exercised on
Windows Docker Desktop. Neither proves every upstream release or host filesystem.

The [Docker media-app preview](DOCKER-PLEX-PREVIEW.md) now has local extracted-package
acceptance for startup without recipient Python, a fresh browser-reviewed Plex
installation, read-only media mapping, Plex account completion and local sample
playback. The four core apps have private credential handoff, media/download paths,
reviewed connections and credential persistence across container restart. Generated Arr web logins and a guided provider/Torznab setup have passed packaged
checks; a local source was shared and searched by both Arr apps. Personal provider
choices remain user steps. Original local movie/TV BitTorrent transfers and automatic
imports pass with matching hashes. Personal providers, imported-file Plex playback,
LAN and Windows startup certification remain open. Seerr 3.5.0 has also passed private
handoff, reviewed Arr connections, original movie/season requests, automatic imports,
Plex library visibility and completed-request readback.

The Docker dashboard also supports reviewed Start, Stop and Restart on unchanged
owned containers. Manual encrypted configuration snapshots cover the nine catalog
apps. A real disposable four-app restore recovered deliberately changed app
settings, normal logins and library records, with unchanged container IDs and media
hashes. Nightly schedules, scheduled-copy retention and verified storage on another
physical disk also pass in the packaged four-app lab, including a rejected corrupt
copy and restore with the local snapshot missing. Manual/safety/update snapshots
are preserved. Claimed Plex/Seerr/Tautulli whole-host reconstruction now passes in
isolated Docker; replacement-Windows certification remains a separate gate.
Owned Docker updates now have a dated same-major
candidate catalog, encrypted snapshots, authenticated health/protected-settings
checks and image/data rollback. Real failure and fresh-process interrupted-commit
recovery pass on the disposable Prowlarr stack. Compatible [Stackarr self-update
and rollback](SELF-UPDATE.md) now pass packaged Docker acceptance, including a
database-changing failed candidate and fresh-process interrupted-worker recovery.
The dashboard and Windows controller update together without changing media apps.
Owned-app [repair and removal](APP-MAINTENANCE.md) retain settings/media and use
verified safety snapshots. The packaged core lab covers container recreation,
removal, backup while absent and bringing the app back. Failed/interrupted repair
recovery uses a matching configuration checkpoint and explicit recovery review.
[Plex, Seerr and companion maintenance](OPTIONAL-APP-MAINTENANCE.md) adds 30 real
native cases across all five apps: repair, recovery after confirmed failed-repair
writes, distinct-image update/rollback, failed update recovery, actual worker exit
with fresh-process recovery and encrypted restore. A separately claimed Plex
server and authenticated Tautulli connection are preserved. Seerr uses a generated
local account in that earlier matrix.
The final extracted package also passes 15 owner-reviewed browser actions across
these five apps, using its actual frozen controller: repair, distinct-image update
and rollback with logins, connections, monitors, disabled cleanup and media preserved.
The follow-up [Seerr Plex-owner matrix](SEERR-PLEX-MAINTENANCE.md) passes six native
cases and five packaged browser app actions for 3.4.1 → 3.5.0. Fresh Plex sign-in,
owner permissions, library selection, Arr connections and a pending test request
survive repair, update/rollback, actual failed/interrupted recovery and encrypted
restore. The new package also rolls back the earlier package's update checkpoint.
Invited/shared-user permissions and revocation, major migrations and recipient-browser
popup behavior remain separate gates. The whole-host follow-up restores the same
claimed Plex identity/libraries, Seerr owner/permissions/pending request and Tautulli
login/library/user records. All three databases pass integrity checks, old Stackarr
sessions are revoked, controller enrollment is regenerated and the five recovered
dashboard integrations authenticate. Media and the main installation remain unchanged.
Stackarr [removal and reviewed reinstall](SELF-REMOVAL.md) retain the account,
settings, keys, app receipts and backups while media apps keep running. Removal
stops its private controller, so scheduled backups pause. The local package offers
reviewed reinstall using checked data copies; failed/interrupted attempts preserve
the original removed state. Missing/shared/changed retained data requires inspection
or whole-host recovery, rather than adoption or a settings reset.
Major migrations, signing, native file-dialog walkthroughs and broader account
migrations remain open. Media/download files are
preserved in place and excluded from app snapshots; see the preview guide for key
retention and same-installation restrictions.

| Host / deployment | x86-64 | ARM64 | Status | Notes |
| --- | --- | --- | --- | --- |
| Linux Docker Engine + Compose v2 | Core and five-app installer tested in hosted CI | Core tested; app image support varies | Tested core / experimental apps | Use official image architecture lists and pin digests for production. |
| Docker Desktop on Windows | Core, browser-to-Docker install, libraries, credentials, reviewed connections, local Plex sample and app restarts tested | Experimental | Tested limited lab scope | Docker Desktop 4.92.0 / Compose 5.5.1; Bounded original-sample transfer/import passed; no real-provider, LAN/full-length playback or before-login certification. |
| Native Windows runtime migration | Not exercised on a live host | Not applicable | Plan-only preview | Versioned runtime staging and rollback source are provided; existing scheduled tasks, services, Caddy, firewall, certificates, and startup behavior are not adopted or changed. Reboot-without-login verification is required before any task migration. |
| Docker Desktop on macOS | Experimental | Experimental | Experimental | Use Docker Desktop and a shared host folder. Plex hardware transcoding and filesystem performance need host testing. |
| Synology Container Manager | Experimental | Experimental | Experimental | Export the reviewed Compose plan and import it as a project; DSM permissions and image availability vary. |
| QNAP Container Station | Experimental | Experimental | Experimental | Import the reviewed Compose application; verify shared-folder permissions and storage paths. |
| Unraid Docker | Experimental | Experimental | Experimental | Use the generated Compose plan or translate it into an Unraid template. No Unraid host was available for testing. |
| TrueNAS SCALE Custom App | Experimental | Experimental | Experimental | Paste the reviewed YAML into the Custom App flow; validate paths and UID/GID in the UI. |

The supported application subset is any combination of Plex, Sonarr, Radarr, Prowlarr, qBittorrent, Cleanuparr, Tautulli, Uptime Kuma, and optional Seerr. Stackarr uses read-only status collection for all adapters in this preview. Cleanuparr's pinned 2.10.11 adapter reads authenticated configuration to report dry-run and automation safety; setup disables all five automatic job groups, including both Seeker search switches, before connecting Arr/qBittorrent. It mounts no media or downloads and triggers no cleanup. Tautulli connects to the owned Docker Plex server. Uptime Kuma 2.5.6 slim receives TCP service monitors and exposes authenticated Prometheus metrics; a responding port does not prove an application API is healthy. Generated companion logins are protected by the Stackarr owner password. Seerr completes private credential handoff and reviewed Arr connections after its Plex setup while leaving request permissions and catalog behavior to Seerr. Connection wiring is previewed and only creates an advertised connection when the target application schema and test endpoint agree; existing connections are preserved.

The portable browser client needs only a modern browser and can run on a different OS from the server. Native installers, router changes, privileged containers, automatic internet exposure, and universal ARM support are unsupported in this preview.

The local installer uses pinned x64 images for all nine catalog apps. NAS agents,
ARM images, Docker prerequisite installation and unattended Windows startup remain
outside the tested installer path. A successful Docker lab is not fresh-Windows
certification.


If sign-in reports that password verification is temporarily unavailable, the host
may be under memory pressure. Close unused applications, then retry. Stackarr does
not reset the account or weaken its password protection. A failed first-account
attempt keeps the setup authorization file available for another attempt; local
pairing approval still has its normal expiry. Existing sessions are not replaced
by a failed sign-in.

Use Apps → Start, stop & recover → Check installation in the native or packaged
Docker dashboard to inspect containers created by the wizard. A changed image,
media mount, port, network or ownership is reported without automatic repair.
Review Start, Stop or Restart only for unchanged apps; use Health separately to
check app API connectivity. Backups requires its own review before app downtime
or configuration replacement and retains a before-restore safety copy.
