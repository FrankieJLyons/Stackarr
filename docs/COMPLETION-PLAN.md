# Stackarr completion plan

> [!NOTE]
> Historical plan. The [current roadmap](ROADMAP.md) supersedes this document's release priorities and status claims as of 16 November 2026. Some unchecked items below shipped in 0.1.0; retain this document as design history, not a current feature checklist.

Planning baseline: 16 October 2026, application revision `e169c71`.

The [Stackarr 0.2 usability and first watch plan](UX-0.2-PLAN.md), dated 20 October 2026, defines the next release's beginner setup, source/request, title-progress and household viewing work. Use its delivery sequence for that work while retaining the technical release gates and environment boundaries below.

Execution scope on 16 October: the owner requested Docker-only work on the existing computer because no second Windows machine is available. Clean-Windows, signed-out reboot and second-device gates remain deferred. The current slice is the packaged Docker Plex journey described in [DOCKER-PLEX-PREVIEW.md](DOCKER-PLEX-PREVIEW.md); this does not close the full runtime milestone below.

### Current Docker work package

- [x] Verify the local Docker engine, Linux x64 architecture, Compose and local context through the private controller.
- [x] Package a prebuilt dashboard and Windows controller; verify startup from the extracted ZIP without recipient Python or a source build.
- [x] Integrate readiness and reviewed Docker prerequisite setup into the main executable and package. Continue into the Docker setup wizard in the same tab, keep existing-app mode separate, recheck stale readiness and retain repair/reinstall reviews. Pass isolated packaged installation/reopening, 9 browser scenarios and 23 frozen checks with existing apps/settings/media unchanged. See [INTEGRATED-FIRST-RUN.md](INTEGRATED-FIRST-RUN.md). Actual clean-Windows installation/reboot remains deferred.
- [x] Install Plex through the real browser flow, verify its read-only media mount and Web link, and preserve progress and unrelated containers.
- [x] Implement the private Plex credential handoff with encrypted storage, ownership checks and protection for newer settings; test the unclaimed-account path live.
- [x] Complete the owner's Plex account setup, verify fresh authenticated monitoring, and play the original sample on this computer.
- [x] Add qBittorrent, Sonarr, Radarr and Prowlarr through the packaged Docker flow; verify private credentials, paths, four reviewed connections and persistence across app-container restart.
- [x] Generate and privately save unique Arr web logins; preserve existing logins and verify owner-protected access.
- [x] Add guided Prowlarr provider/Torznab setup and verify sharing/search with an original local test source.
- [x] Complete the separate-container original-media download and automatic import test for movie and TV samples; verify transferred bytes, library hashes and Arr import history.
- [x] Restore Docker and the existing private controller/dashboard connection; finish the disposable import-lab shutdown.
- [x] Add Seerr, verify private credentials and reviewed Plex/Arr setup, and complete original movie/season requests through automatic import, Plex visibility and Seerr completion.
- [x] Bridge installation checks and reviewed Start/Stop/Restart into the Docker dashboard; verify real browser controls and exact container preservation.
- [x] Add encrypted app-configuration snapshots and reviewed same-installation restore with a retained safety copy; restore deliberately changed settings in the disposable four-app Docker stack and verify logins, library records and media hashes.
- [x] Add reviewed owned-app updates, authenticated health/settings checks, image/data rollback and interrupted-update recovery. Pass packaged browser update/rollback for all four core apps, failed health after real candidate writes and fresh-process recovery across the receipt file/database commit gap. Deploy the controls to the main six-app preview with its app containers, settings and 16 media/data file hashes preserved.
- [x] Add nightly schedules, scheduled-copy retention and verified storage on another physical disk. Test the packaged wall-clock schedule, preserve manual/safety/update snapshots, reject a corrupt external copy before downtime and recover changed app settings from the second disk with the local snapshot missing. Enable the main six-app plan at 03:00 with 7 scheduled copies per installation on D:; verify the first backups and all 16 original media/data hashes without restoring main data.
- [x] Default to automatic available app ports, avoid occupied dashboard/controller ports on fresh startup, and offer reviewed recovery for ports taken after review or during image download. Reuse approved media storage, defer new folder selection until needed, preserve grants across restarts and skip media storage for monitoring-only setup. Pass the packaged three-app and standalone Kuma workflows, long/Unicode folder paths, cancellation contracts, saved-address reopening and preservation checks.
- [ ] Check the native Windows folder dialog with a person and complete novice recipient walkthroughs.
- [x] Add Tautulli, Uptime Kuma and Cleanuparr through packaged Docker setup, with generated protected logins, private credentials, owned Docker Plex monitoring, nine TCP service monitors and tested Arr/qBittorrent connections. Verify dry-run, all automatic jobs off, no media/socket mounts, idempotence, encrypted backups/restarts and all 16 existing media/data hashes. Extend the main nightly backup plan and verify a separate-disk copy for the new companions.
- [x] Add complete encrypted host recovery files containing app configurations, controller receipts and the dashboard account/credentials. Reconstruct a separate nine-app Docker lab after losing its generated volumes and host state; verify fresh-process retry after a real partial extraction, saved logins/settings and unchanged sample/main media. See [HOST-RECOVERY.md](HOST-RECOVERY.md) for the exact boundary.
- [x] Add compatible Stackarr dashboard/controller updates and reviewed rollback. Verify actual packaged updates, restored preferences/current sessions, failed candidate database checks and recovery after killing the independent worker in the isolated Docker lab. See [SELF-UPDATE.md](SELF-UPDATE.md).
- [x] Add reviewed owned-app repair and removal with settings retained. Verify single-container recreation/removal, restoration from retained data, absent-app backups, occupied-port rejection, stopped-state preservation and failed/interrupted repair recovery in the isolated Docker lab. See [APP-MAINTENANCE.md](APP-MAINTENANCE.md).
- [x] Add Stackarr removal with account/settings/keys/backups retained and reviewed native reinstall. Verify packaged browser removal, frozen local approval, port conflicts, older-launcher refusal, actual failed-candidate database writes and fresh-process recovery after removal/reinstall interruption while media apps remain unchanged. See [SELF-REMOVAL.md](SELF-REMOVAL.md).
- [x] Pass the isolated five-app maintenance matrix for Plex, Seerr, Tautulli, Uptime Kuma and Cleanuparr: 30 native cases covering repair, confirmed-write failed repair recovery, distinct-image update/rollback, failed update recovery, actual worker exit/fresh-process recovery and encrypted restore, plus 15 final packaged browser actions. Preserve the freshly claimed lab Plex identity/library, generated logins, connections, monitors, disabled cleanup and all existing main apps/media. See [OPTIONAL-APP-MAINTENANCE.md](OPTIONAL-APP-MAINTENANCE.md).
- [x] Extend Seerr maintenance to a real Plex owner: pass six isolated native cases and five packaged browser app actions, fresh Plex sign-in after each case, API-healthy authentication failure recovery, actual interrupted-worker recovery and rollback of an older package's update checkpoint. Preserve owner permissions, library, Arr connections, a pending test request and all main apps/settings/media; stop the lab with recovery data retained. See [SEERR-PLEX-MAINTENANCE.md](SEERR-PLEX-MAINTENANCE.md).
- [x] Complete claimed Plex/Seerr/Tautulli whole-host recovery in a fresh five-app Docker lab with Sonarr/Radarr dependencies. Remove only its new source volumes/state, prove partial claimed-account extraction and fresh packaged retry, then verify real logins, identity/library/request/database preservation, revoked Stackarr sessions and unchanged original labs/main installation. See [HOST-RECOVERY.md](HOST-RECOVERY.md).
- [x] Add reviewed same-release Stackarr runtime repair with account/settings retained. Pass first-use packaged browser repair, frozen offline approval, missing-dashboard/damaged-Compose repair, actual read-only/full candidate storage, Windows write denial, interrupted-worker recovery, release-staging retry, unavailable-runtime refusal and late dashboard-port recovery in isolated Docker. See [RUNTIME-REPAIR.md](RUNTIME-REPAIR.md).
- [x] Add bounded read-only Docker network-capacity diagnostics and clear exhaustion recovery without pruning/changing pools. Add durable image-download progress, bounded download-only retries, digest/platform verification and explicit retry after worker interruption. Pass six real nested-engine faults and packaged older-release promotion/registry-failure browser retry with existing apps/settings/media preserved. See [NETWORK-DOWNLOAD-RECOVERY.md](NETWORK-DOWNLOAD-RECOVERY.md).
- [x] Recover port conflicts during final Docker app startup inside the same owned installation. Review new addresses, retain configuration volumes and healthy app IDs/logins, recreate failed-bind containers safely, preserve original-address resume and recover after worker interruption or repeated conflicts. Pass real Prowlarr/qBittorrent native and frozen-controller/browser acceptance with existing apps/settings/media preserved. See [STARTUP-PORT-RECOVERY.md](STARTUP-PORT-RECOVERY.md).
- [x] Clear Seerr's misleading image config-mount warning only after verifying owned persistent storage and durable writes. Add selected-app Plex/Seerr account steps, exact upstream button names and a usual-browser copy/manual-copy fallback. Verify real Plex authorization-window handoff, blocked-window behavior and the extracted package in isolated Docker. See [SEERR-SETUP.md](SEERR-SETUP.md).
- [x] Complete fresh Plex sign-in and return to Seerr in the owner's usual browser, verify private packaged handoff and preserve the new authorization/owner/settings across container replacement. Confirm the same browser session survives; use only the separate claimed test Plex server and existing sample library.
- [x] Test invited/shared-user restrictions and revoked access with the real pinned Seerr app and owner-approved synthetic Plex identities. Verify admission/import, request/profile privacy, live role downgrades, open-session revocation boundaries and the packaged browser/container-replacement/deletion journey. Preserve all existing apps/settings/media. Record the observed delegated-role flaw separately. See [SEERR-PERMISSIONS.md](SEERR-PERMISSIONS.md).
- [x] Fix Seerr's Manage Users protection with the packaged 3.5.0-stackarr.1 backport. Verify all three role-mutation routes, protected account profiles, delegation limits and atomic batches with 40 real HTTP checks in both native and packaged Docker labs. Pass browser sign-in/replacement and the normal 3.5.0 update with users, requests, settings and authorization retained. Keep existing apps/media unchanged. See [SEERR-PERMISSIONS-FIX.md](SEERR-PERMISSIONS-FIX.md).
- [ ] Test Plex cloud sharing/revocation with a second disposable real account when available. The owner chose synthetic external membership for the current matrix.
- [ ] Complete broader recipient browser/server-claim/library-selection walkthroughs. The fresh sign-in case uses an already claimed test server and API-assisted library selection.

Next Docker sequence:

1. Finish recipient app-selection presets and broader small/companion combinations.
   Integrated readiness, reviewed Docker setup, same-tab handoff and saved-installation
   reopening now pass in the main package. The native existing-app walkthrough and
   actual prerequisite installation still need recipient Windows acceptance.
2. Extend wider/major-version maintenance and recipient coverage. The packaged
   Seerr delegated-admin backport now passes isolated acceptance, including the
   normal security update. Invited/shared-user and revoked-access tests run with
   real Seerr and synthetic external identities; a second real Plex account remains
   a separate gate. Compatible owner-account maintenance and
   claimed Plex/Seerr/Tautulli reconstruction now pass, including partial extraction,
   fresh packaged retry and older-checkpoint rollback. Network/cloud backup
   destinations remain separate work.
3. When recipient testing is available, complete native folder/recovery-dialog and
   broader Plex browser/server-library walkthroughs, novice tests and replacement-Windows certification.
   Include companion-only and smaller combinations. Automatic ports/shared folder
   reuse and standalone Kuma already pass packaged Docker acceptance.

Seerr's fresh-volume warning fix, scoped account guidance and official Plex popup
handoff now pass. Fresh human sign-in/return and the usual-browser session surviving
Seerr replacement also pass; broader recipient and server/library-selection gates remain.
The invited/shared-user matrix is complete for synthetic external identities.
The observed delegated-admin gate is closed for the tested security package.
Existing upstream installations need a reviewed update before using that fix.

Windows signed-out startup, LAN/second-device certification and signing remain
separate deferred release gates.


The package checks passed on 16 October with the extracted `20261016-rc2` package. On 17 October the same Docker Plex server completed account setup as **Stackarr Docker Test**, its private connection reached fresh monitoring, and the original five-second sample played in the browser on this computer. A repeated connection check preserved saved details and remained ready. The broader release gates below remain separate from this Docker work package.

Stackarr has the core of a useful product. Completion now means joining its installation, connection, storage, startup and maintenance features into one dependable experience that another person can finish without developer help. The first supported release should target Windows 11 x64, with any selected combination of the nine catalog apps. Other platforms follow their own acceptance tests.

This is the proposed execution order for the remaining work. [ONE-DOWNLOAD-PLAN.md](ONE-DOWNLOAD-PLAN.md) defines the intended experience, [PRODUCT-PLAN.md](PRODUCT-PLAN.md) retains the broader roadmap, and [PROGRESS.md](PROGRESS.md) records completed evidence. Release gates below are open unless explicitly recorded as passed.

## The finished experience

A recipient downloads one signed installer, chooses what they want to do, selects a folder, reviews the changes and installs. Stackarr handles supported addresses, ports, shared paths and credentials for apps it owns. The recipient completes necessary Plex/Seerr sign-in and personal source choices through guided steps. A final check proves the selected workflow works.

They can then add another app, change supported settings, open the dashboard from a trusted home device, restart the computer and recover from an interrupted operation. Backups, repair, updates and removal preserve their media and unrelated applications.

Normal setup requires no Git, Python, terminal commands, Compose editing, environment variables or copying API keys between newly installed core apps. Existing apps use a separate guided connection flow and keep their current settings until a reviewed change is accepted. Advanced controls remain available.

## Current position

| Area | Working foundation | Remaining release gap |
| --- | --- | --- |
| Dashboard and security | Local account, sessions, encrypted credentials, read-only collectors, stale data and partial-failure handling | Complete accessibility, password recovery, platform key protection and household usability |
| Distribution | Docker preview ZIP with prebuilt dashboard/controller, integrated readiness, reviewed verified Docker download, same-tab setup, saved-runtime reopening, frozen smoke checks and checksums | Installed background runtime, signed installer, actual prerequisite/reboot and clean-machine acceptance, durable release downloads |
| Installation | Reviewed Compose plans, owned projects, pinned images, durable jobs, network-capacity diagnostics, verified image downloads, final-start port recovery and explicit resume | Whole-connection internet loss and abandoned-install resolution |
| Docker dashboard | Packaged controller startup, folder selection, private enrollment/TLS, review/install/status/resume, cached progress, six-app credential handoff and reviewed Start/Stop/Restart | Folder-dialog usability and connection recovery for older/uncertain installs |
| App configuration | Docker core apps have credentials, generated web logins, roots, categories, reviewed core/Seerr connections and restart persistence; original movie/season requests reached Plex libraries and Seerr completion | Real-provider account setup, imported-file playback and broader recipient checks |
| Optional apps | Packaged install, protected logins, Tautulli Plex connection, Kuma metrics/monitors, disabled Cleanuparr automation; distinct-image updates, repair, failed/interrupted update recovery and encrypted restore; real Seerr Plex-owner maintenance, fresh-volume warning fix, sign-in guidance and packaged Manage Users security backport | Companion-only/subset recipient walkthroughs, major migrations, real Plex cloud sharing/revocation and broader browser/server-library selection |
| Everyday operation | Docker lifecycle and retained-data repair/removal, encrypted app restore, nightly retention/second-disk copies, nine-app update catalog, five-app maintenance matrix, isolated whole-host reconstruction including claimed Plex/Seerr/Tautulli accounts, Stackarr self-update/rollback, runtime repair/storage-failure recovery and retained-data removal/reinstall | Replacement-host/native-dialog acceptance, revoked/shared-user account changes, major migrations, unknown/lost runtime metadata, LAN HTTPS and unattended startup |

The original planning baseline was **288 passed, 3 skipped**. The integrated first-run package now has **687 passed, 3 skipped**, plus 9 Node permission-policy tests. Ruff and portable-source checks are recorded in [PROGRESS.md](PROGRESS.md). The skips are Windows filesystem-link cases. Fresh packaged core-app acceptance and bounded local Plex account/playback evidence are recorded there; the original local movie/TV BitTorrent transfer and automatic imports also pass. These do not certify a clean Windows install, personal providers, imported-file Plex playback or LAN/startup behavior.

The main implementation split is visible in [server.py](../stackarr/server.py): controller-backed installation, readiness, Plex/core-app connection completion and generated Arr/qBittorrent login access are implemented. Seerr handoff and reviewed Arr connections now pass. Reviewed start/stop/restart and manual encrypted app backup/restore now use the controller. Reviewed same-major app updates and image/data rollback also pass, including injected failure and interrupted-commit recovery. Isolated whole-host reconstruction, fresh-process retry and compatible Stackarr self-update/rollback now pass. Connection recovery for uncertain older installations, revoked/shared-user account changes and replacement-host certification remain open. Claimed Plex/Seerr/Tautulli whole-host reconstruction now passes in isolated Docker. [INSTALLATION-CONTROLLER.md](INSTALLATION-CONTROLLER.md) records the remaining work. The packaged Docker startup helper now uses the bundled executable and image; the source-development helper still requires a checkout and `.venv`.

## Scope for completion

Ship one recommended Windows deployment, one onboarding flow and one set of ownership and configuration rules. Keep Plex, Sonarr, Radarr, Prowlarr, qBittorrent, Seerr, Tautulli, Uptime Kuma and Cleanuparr independently optional. Show each adapter's actual install, connection, monitoring, configuration and backup capabilities.

Finish the six core apps first, then validate the three companions before describing the nine-app package as complete. If a companion cannot pass, remove its installation option from the supported release or label it clearly experimental; that reduced release must not be represented as completion of all nine apps.

Defer NAS agents, ARM certification, macOS packages, internet access, cloud accounts, S3 backup, Buildarr/Recyclarr translation, advanced quality policies, automatic download rescue and destructive cleanup. Storage Guard can follow the first release behind its own acceptance gate. Basic space checks and disk-full recovery belong in this release.

## Delivery milestones

### 0 Prove the Windows runtime

The runtime choice is the largest scheduling risk. Use [WINDOWS-RUNTIME-LAB.md](WINDOWS-RUNTIME-LAB.md) on a disposable Windows machine with a second LAN device.

- [ ] Test the preferred Compose route with Stackarr, Plex, qBittorrent, Sonarr and the proposed HTTPS gateway.
- [ ] Verify folder access, credentials after restart, import of an authorized sample, LAN playback, resource use and quiet recovery.
- [ ] Reboot and verify authenticated services and playback while Windows remains signed out, with automatic sign-in disabled.
- [ ] If the route fails the required startup behavior, record why and test the existing plan's native alternative. Evaluate a hybrid only when a demonstrated limitation warrants it.
- [ ] Record the chosen topology, exact supported Windows/runtime versions, startup identity, privilege requirements and recovery method. Reestimate the remaining work against that choice.

**Done when:** one topology passes the real startup, storage and playback checks. A documented sign-in startup option is insufficient: Docker describes its desktop startup setting as running when the user signs in. [Docker settings](https://docs.docker.com/desktop/settings-and-maintenance/settings/)

### 1 Deliver one installable product

Preview progress: [integrated first run](INTEGRATED-FIRST-RUN.md) now includes the
local readiness interface, reviewed prerequisite flow, dashboard image and scoped
controller in one ZIP. The real package reaches reviewed app installation and
reopens saved state. The installed/signed product, actual clean-machine prerequisite
and reboot checks, startup mechanism and OS key-protection requirements below stay open.

- [ ] Package the local setup interface, dashboard and scoped host controller as one installed, versioned product. Setup must open even when Docker is absent.
- [ ] Put state, keys, logs and ownership receipts in designated application directories; remove runtime dependencies on the source checkout, `.venv` and developer tools.
- [ ] Add readiness checks and guided fixes for the chosen runtime, virtualization, available disk/RAM, occupied ports, storage permissions and download failures.
- [ ] Download verified prerequisite installers/payloads, explain terms and privilege requests, and checkpoint across necessary reboots. Follow the selected vendor-supported installation path. [Docker Windows installation](https://docs.docker.com/desktop/setup/install/windows-install/)
- [ ] Ship verified prebuilt payloads/images so recipients never build Stackarr locally. Install Start menu entry points and a background startup mechanism consistent with milestone 0.
- [ ] Package enrollment, controller restart/reconnect, certificate/key renewal and revocation. Add protocol/version compatibility checks and OS-backed protection for secrets and private keys.
- [ ] Preserve or explicitly review migration of preview state. Reopening setup must find the same installation, account and operation history.
- [ ] Configure builds for the actual release branch/tag and preserve unit, browser and packaged-runtime gates. The preview workflow now also builds `main`; a signed release pipeline remains open.

**Done when:** the exact release candidate opens setup on a clean supported PC with no Python or terminal, resumes across a required reboot and reconnects after both dashboard and controller restart.

### 2 Make choices and folders effortless

- [ ] Present editable outcome presets: Watch my media, Add TV and movies, Add requests, Monitoring, and Custom. Explain upstream accounts and personal provider choices before installation.
- [ ] Use one journey: computer check, features, folders, access, review, installation, account completion and verification. Save every checkpoint and offer one clear next action.
- [ ] Replace `STACKARR_CONTROLLER_ROOTS` configuration with a host-approved folder picker and guided sharing. The host grants folder access; browser input cannot grant arbitrary host filesystem access.
- [ ] Verify host free space and write permissions, then verify the actual container/startup-account view with bounded test files. Offer creation of reviewed media/download subfolders while preserving existing contents.
- [ ] Keep addresses, ports and container details behind Advanced. Suggest free ports and recheck them at approval; handle conflicts with a corrective action.
- [ ] Distinguish not selected, choices saved, installing, account setup needed, connected, working and temporarily unavailable. Show cached progress as last known.
- [ ] Finish keyboard, focus, error-announcement, contrast, zoom and phone checks. Remove setup steps that ask a beginner to understand JSON or host/container path translation.

**Done when:** a new tester selects a folder and the desired app subset without editing paths or environment variables, can leave/resume, and understands what has actually been installed.

### 3 Complete installation and app configuration

- [ ] Extend the existing controller with fixed operations for connection completion, installation checks and reviewed lifecycle actions. Preserve its allowlist, bounded inputs and ownership checks.
- [ ] Deliver owned-app credentials privately to the dashboard's encrypted store. Bind results to deployment identity and settings revision; handle duplicate delivery and reconnect without replacing later user edits. Keep credentials out of browser responses and logs except a deliberate owner-protected login reveal.
- [ ] Model host-local addresses, dashboard-reachable addresses, browser links and inter-app addresses separately. Verify every route from the component that uses it.
- [ ] Apply/test supported qBittorrent credentials, categories and paths; Sonarr/Radarr root folders and download-client connections; and Prowlarr application connections. Reuse the existing reviewed wiring behavior.
- [ ] Complete Plex sign-in/library and Seerr media-server/Arr/profile guidance. Use supported APIs where verified; otherwise open the exact upstream setup page and validate completion. Expose supported high-value settings inside Stackarr with reviewed changes.
- [ ] Give existing apps authenticated identity/version checks, guided credential entry, a connection test and a settings diff. Preserve existing libraries, profiles, credentials and upstream connections.
- [ ] Exercise Add another app through the live browser, including later batches wired to earlier apps. Support mixed existing/new choices and retries without duplicate installation or connections.
- [ ] Add a safe resolution for failed or abandoned installations so one failed companion does not permanently block every later app. Resolution must inspect ownership and preserve existing volumes.

**Done when:** fresh, connect-only and mixed setups reach verified monitoring and a working selected app workflow. A six-app setup completes an authorized download/import fixture and Plex playback; Seerr can complete an authorized test request. Repeating connection setup produces no duplicate writes.

### 4 Validate all optional applications

| App | Required completion |
| --- | --- |
| Tautulli | Fresh install, guided Plex connection, protected credentials, useful status and restart persistence |
| Uptime Kuma | Diagnose the recorded `exec format error`, verify the replacement/current architecture digest, complete first-run setup and authenticated metrics monitoring |
| Cleanuparr | Fresh install, protected login, authenticated safety status, tested Arr/qBittorrent connections, dry-run and all automatic jobs disabled; enabling cleanup remains opt-in |

- [ ] Test each companion alone and added later to an existing core installation.
- [ ] Test the complete selected nine-app combination and representative smaller subsets using the exact release images.
- [ ] Record install, account, connection, monitoring, backup and lifecycle support per adapter. Derive UI capability labels from that record instead of equating an install definition with working support.

**Done when:** every advertised supported app passes its capability-specific runtime checks and restart persistence. Unselected apps produce no setup requirements or failure alarms.

### 5 Finish home access and reliable startup

- [ ] Offer This computer and Home network access with a stable server address and working app links from another device.
- [ ] Generate reviewed gateway, allowed-host/origin, secure-cookie and narrowly scoped firewall configuration. Keep the private controller inaccessible to LAN browsers.
- [ ] Provide certificate-trust instructions for each supported client type and verify normal browser validation. Caddy's local HTTPS requires clients to trust its CA; automatic trust installation is not guaranteed. [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https)
- [ ] Support the upstream access requirements for Plex clients without exposing unauthenticated app administration or opening router ports.
- [ ] Implement the startup/recovery mechanism proven in milestone 0, including dependency ordering, bounded retries, cooldowns, useful audit messages and quiet background operation.
- [ ] Repeat cold boot, signed-out LAN access, playback and credential checks using the packaged candidate. Cover missing folders, changed network address and runtime unavailability with clear next steps.

**Done when:** a second supported LAN device securely opens Stackarr and the required apps, plays the sample and still works after a reboot with the host signed out.

### 6 Make maintenance recoverable

- [ ] Add consistent app-configuration/database backups alongside Stackarr settings, secrets and ownership receipts. Use supported app snapshot methods or reviewed downtime where required; report exclusions accurately.
- [x] Provide nightly schedules, scheduled-copy retention, encrypted verified snapshots, a tested separate physical disk destination and reviewed same-installation restore, including a missing local snapshot.
- [x] Complete whole-host reconstruction into an empty isolated Docker installation with a separately retained key and complete host recovery file; media files need their own backup. The nine-app first-run matrix and claimed Plex/Seerr/Tautulli five-app follow-up pass, including partial-write recovery in a fresh packaged process. Replacement-host/native-dialog acceptance remains open.
- [x] Implement reviewed owned Docker app updates with compatibility checks, verified configuration snapshots, authenticated health/settings checks and image/data rollback; test failure and interruption on the disposable core stack.
- [x] Complete compatible Stackarr dashboard/controller self-update and reviewed rollback, including failed and interrupted packaged Docker recovery without changing media apps.
- [ ] Complete broader/major-version update acceptance and signed update distribution. Reverting an image alone remains insufficient for a migrated database.
- [x] Add reviewed repair/removal of owned Docker app containers, retaining data, logins and backups by default; test isolated failure/interruption recovery.
- [x] Add retained-data Stackarr removal and reviewed reinstall, with packaged failed/interrupted recovery and media-app preservation.
- [x] Complete isolated same-major maintenance for Plex, local-account Seerr, Tautulli, Kuma and Cleanuparr, including claimed lab Plex/Tautulli authentication and failed/interrupted update recovery.
- [x] Complete compatible Seerr Plex-owner maintenance with fresh sign-in, protected permissions/request/library settings, failed/interrupted recovery and older-package checkpoint rollback.
- [x] Complete same-release owned Stackarr runtime repair and storage-failure recovery, including real candidate writes, actual denied/full storage, Windows file locks, interrupted-worker/fresh-process recovery and a late dashboard-port conflict. Preserve media apps, account, settings, keys and backups. Unknown/shared storage, missing keys/enrollment/network and corrupted accounts require inspection or whole-host recovery.
- [x] Complete read-only network-capacity diagnostics and interrupted image-download recovery, including actual nested-engine exhaustion, after-review/final-start network failures, partial blob transfer, worker/CLI exit, fresh-process explicit retry, cached-image reuse and packaged frozen-controller/browser acceptance. Keep default pools and unrelated apps unchanged.
- [x] Complete the final app-install port-conflict window, including partial startup, reviewed address changes on retained volumes, original-address failed-bind recreation, repeated conflicts, shared-volume refusal and actual worker exit/fresh-process resume. Finish private connections using recovered ports through the packaged browser without changing existing apps or media.
- [ ] Complete Seerr invited/shared-user permissions and revocation, and major/account migrations. Preserve data by default and show exactly which owned components change.
- [ ] Provide local owner-authorized password recovery, an audit view and a redacted diagnostics export with explicit preview before sharing.
- [ ] Finish whole-connection internet-loss acceptance and changed-password recovery. Partial image transfer/worker interruption, network-capacity failures, final app-start port recovery and Stackarr runtime denied/full-storage now pass; existing owned-app failure/update coverage remains recorded separately. Recovery must preserve unrelated apps and test media.

**Done when:** backup/restore, update rollback, repair and uninstall preservation pass on disposable installations, and every supported failure has an actionable recovery path in the UI.

### 7 Pass recipient testing and release

- [ ] Run the exact candidate on clean Windows environments, including a standard user and a machine with unrelated containers. Repeat the critical install, account, import, request, playback, restart and recovery checks.
- [ ] Run three novice walkthroughs covering minimal, full and mixed setups. Observe silently; record every request for help and fix recurring blockers. Each tester must also add another app after initial setup.
- [ ] Target no terminal use, no developer intervention and no API-key copying for the supported fresh core flow. As a proposed usability target, require no more than ten minutes of active user interaction excluding downloads, reboots and upstream account creation; measure total elapsed time separately.
- [ ] Add automated runtime coverage for all supported adapters and representative subsets. Keep human account, playback, startup and accessibility checks as explicit release gates.
- [ ] Sign the installer; publish versioned checksums, component inventory/SBOM, upstream attribution, release notes, tested platform versions and an upgrade policy. Ensure image selection and prerequisite downloads are verifiable.
- [ ] Reconcile README, support matrix, architecture and setup guides with the final behavior. Provide one obvious download, a short setup guide and a redacted bug-report flow.
- [ ] Share a private release with invited testers first. For a public release, prepare an audited clean export into a new repository and obtain the owner's publication approval under [PUBLICATION.md](PUBLICATION.md). Keep this repository and its history private.

**Done when:** the recipient test matrix passes, release artifacts correspond to the tested revision, and the download/install/setup/support experience is available to the intended audience.

## Completion checklist

- [ ] One signed download starts on an empty supported Windows PC.
- [ ] A beginner finishes the chosen setup through UI and understands necessary upstream account/source steps.
- [ ] All advertised apps pass their individual support gates; unselected apps stay out of the way.
- [ ] Installed core apps connect without secret copying, and existing apps keep their settings until changes are accepted.
- [ ] Adding an app later preserves earlier containers, settings, credentials and media.
- [ ] Authorized import, playback and request flows pass for the relevant selected apps.
- [ ] Home access and reboot while signed out pass on the exact release package.
- [ ] Interrupted installation and common failures recover without a reinstall.
- [ ] Backup restore, update rollback, repair and data-preserving uninstall pass.
- [ ] Three novice walkthroughs and the release security/accessibility checks pass.
- [ ] The versioned release has a working recipient download and accurate support documentation.

## Execution and resources

Use one release owner to maintain the milestone checklist and prevent unsupported scope from entering the critical path. Each implementation slice should end with a small reviewable change, relevant automated checks, a working demo and evidence in PROGRESS.md. Close a milestone only when its acceptance behavior passes on the target environment.

An initial planning allowance is **8â€“14 engineering weeks for one experienced developer**, assuming the Compose topology passes milestone 0 and supported upstream configuration paths remain available. This is a budgeting estimate, not a delivery date. Reestimate after the runtime test; a native/hybrid adapter effort changes the critical path. Signing, access to clean machines, upstream accounts and tester availability can extend elapsed time.

Required resources are a disposable Windows 11 x64 environment with suitable virtualization or a spare PC, a second LAN device, authorized sample media and chosen Plex/Seerr test accounts, three novice testers and a signing/release identity. Use physical hardware for any advertised GPU capability. Keep the working media server outside the test scope.

## First work package

1. Run milestone 0 and record the runtime decision. This determines the installer and startup work.
2. Package a single vertical slice: the real installer opens setup, a user selects a host folder, Plex installs, the user signs in, Stackarr connects and a second device plays an authorized sample.
3. Extend that same path to qBittorrent plus Sonarr/Radarr/Prowlarr, then Seerr and the three companions. Keep Add another app working at each extension.
4. Complete maintenance and recipient testing before declaring the app ready to hand to a household.

The Docker Plex account, monitoring and local sample demonstration passed on 17 October, followed by installation, connection and restart checks for the four core download/Arr apps. Generated Arr logins and original download/import acceptance subsequently passed, followed by Seerr connection setup and movie/season requests through automatic import, Plex library visibility and completed requests. Packaged Docker lifecycle controls and encrypted configuration backup/restore now pass, including a real disposable-stack restore with settings, logins, library records and media preserved. Safe Docker updates/rollback and scheduled second-disk backups now pass as well. The optional companions, automatic folder/port choices, isolated whole-host reconstruction, compatible Stackarr self-update/rollback and owned-app repair/removal with failed/interrupted recovery now pass. Stackarr removal/reinstall now also passes isolated failed/interrupted recovery. The additional five-app matrix covers compatible repair, updates and recovery with a separately claimed Plex/Tautulli connection and local-account Seerr. A follow-up Seerr lab now passes real Plex-owner sign-in throughout compatible updates, failed/interrupted recovery, encrypted restore and older-checkpoint rollback. Claimed Plex/Seerr/Tautulli whole-host reconstruction also passes in a fresh five-app Docker lab, including partial extraction and a fresh packaged retry. Same-release owned Stackarr runtime repair now passes actual denied/full storage, Windows file locks, interrupted-worker recovery and a late dashboard-port conflict. Network-capacity diagnostics and interrupted image-download recovery now pass, including actual nested-engine exhaustion, partial blobs, worker/CLI exit and a packaged frozen-controller retry. Final app-start port recovery now also passes real partial-startup, retained-volume, original-address and interrupted/repeated-conflict checks with packaged browser connection completion. Seerr's fresh-volume warning fix, selected-app account guidance and official Plex authorization-window handoff now pass in the extracted package. Fresh sign-in/return and same-browser session persistence across Seerr replacement also pass. Invited/shared-user restrictions and revocation now have real-app synthetic-identity and packaged browser coverage. The packaged delegated-admin security backport now passes isolated install/update acceptance. Real Plex cloud sharing/revocation, broader browser/server-library selection, major/account migrations and recipient walkthroughs remain open. Replacement-host, clean-machine and signed-out startup certification remain deferred release gates.
