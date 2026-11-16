# Stackarr: one download to a working home media server

> [!NOTE]
> Historical plan. The [current roadmap](ROADMAP.md) supersedes this document's release priorities and status claims as of 16 November 2026. Some unchecked items below shipped in 0.1.0; retain this document as design history, not a current feature checklist.

Planning revision: 25 September 2026. This is the delivery plan, not a claim that the current alpha already provides this experience. It narrows PRODUCT-PLAN.md and takes priority where the older sequencing differs.

The proposed remaining execution order and release gates, based on the 16 October 2026 source baseline, are maintained in [COMPLETION-PLAN.md](COMPLETION-PLAN.md).

## The outcome

Give another person a GitHub release link. They download `StackarrSetup.exe`, run it, choose their media folders and desired features, sign into Plex, and finish with a private local-network dashboard and functioning selected services. No Git, Python, terminal, YAML, API-key copying between newly installed apps, or knowledge of container networking should be required for the normal path.

Start with supported Windows 11 x64 machines. Use the same configuration and adapters for Linux Compose next, then macOS and named NAS platforms with separate acceptance tests. One download means one entry-point installer that downloads verified dependencies when needed; it does not initially mean an offline bundle. Show estimated download size, disk use, license terms, privilege requests, and any necessary reboot before proceeding.

The existing working media server is reference material only. Build and verify this on disposable machines. No migration is required.

## Usability rule for every revision

The normal fresh-install journey is for someone with no computer experience. Ask
for the outcome they want, explain account steps in plain language, and let
Stackarr handle addresses, ports and app credentials wherever safe. Advanced
settings remain available without becoming required reading. Disabled apps stay
out of the way. A completed download or running container is not a completed setup.

The local launcher uses a one-time approval in its own window instead of asking
users to find or copy a setup token. The Stackarr password protects this local
control panel; it does not create a cloud account. Plex and Seerr retain their own
account setup. After that, **Finish connecting** retrieves and verifies connection
details privately for those apps only when Stackarr installed them. Existing
credentials are preserved, and existing installations keep their guided manual
connection path.

Implementation references: [Plex container first-run settings](https://github.com/plexinc/pms-docker/blob/master/root/etc/cont-init.d/40-plex-first-run)
and [Seerr settings schema](https://github.com/seerr-team/seerr/blob/develop/server/lib/settings/index.ts).
These establish file/schema behavior, not permission to redistribute either app.
No upstream code or assets were copied for this feature.

## What exists and what does not

The private alpha now has a bundled Windows launcher, saved setup drafts, local
checks and discovery hints, Seerr request monitoring, reviewed connection wiring,
configuration backup previews, durable checks and webhook deliveries. Hosted CI
builds and smoke-tests the executable. The October 6 implementation adds reviewed
Docker installation for six apps, encrypted credential handoff, new library folders,
port suggestions, connection wiring, read-only container drift checks and reviewed
start/stop of owned apps. It is
still not the promised complete media installer: Docker prerequisite installation,
third-party application backups, LAN setup, upgrades/rollback and
boot-before-sign-in certification remain work. See PROGRESS.md for current evidence.

## Important research findings

Facts checked against official documentation:

- Docker's Windows installation has platform/virtualization prerequisites and first-start terms acceptance. The installer must model these as resumable setup steps. [Docker Windows installation](https://docs.docker.com/desktop/setup/install/windows-install/)
- Docker Desktop documents a start-on-sign-in setting. That alone is insufficient evidence of operation before Windows sign-in; Stackarr must prove the latter separately. [Docker Desktop settings](https://docs.docker.com/desktop/settings-and-maintenance/settings/)
- Plex hardware acceleration depends on the platform, hardware, configuration, and applicable Plex requirements. Detect and test capabilities; do not promise universal GPU support. [Plex hardware acceleration](https://support.plex.tv/articles/115002178853-using-hardware-accelerated-streaming/), [Plex server requirements](https://support.plex.tv/articles/200375666-plex-media-server-requirements/)
- Caddy supports internal HTTPS, but trusting its local CA is not guaranteed automatically, particularly in containers. Other devices require their own trust setup. [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https)

Recommendations below are Stackarr product decisions, not claims made by these sources.

## Architecture decision: prove the runtime before polishing the installer

Keep Docker Compose as the preferred portable deployment format. Bundle the Stackarr setup UI/runtime so it can open and explain prerequisites even when Docker does not exist. Use a local, narrowly scoped host broker for installation work; the web server must not accept arbitrary shell commands or gain a raw Docker socket.

The first technical spike compares a Windows Compose route with a native/hybrid route against boot-before-sign-in, Plex playback, resource usage, update behavior, and folder access. Native Plex may be appropriate on Windows if it passes these tests more reliably. Do not assume that a SYSTEM task or S4U principal solves application account, encrypted credential, or network-share access. Test those specifically.

Select one recommended Windows topology after the spike. If the Compose route cannot meet the always-on requirements, retain it as the portable option and use tested native/service adapters for the Windows default. Do not build a custom Linux VM distribution as an unplanned shortcut. Document any unavoidable prerequisite instead of promising unsupported behavior.

Privileged broker rules: authenticated local IPC, fixed operation types, validated path/port arguments, request identity and revision, bounded execution, operation journal, and least-privilege accounts. Adding remote NAS enrollment comes later. An existing app remains external unless the user explicitly adopts it through a separate supported flow.

## The setup wizard

| Step | What the person sees | What Stackarr does |
| --- | --- | --- |
| 1. Welcome | “Set up a new media server” | Starts bundled local setup; offers resume if an earlier attempt exists |
| 2. Computer check | Ready / needs attention with “Fix” or instructions | Tests OS, disk, RAM, virtualization/runtime if needed, ports, network profile, and download connectivity |
| 3. Choose features | Watch my media; TV/movies automation; requests; monitoring | Explains each capability, maps to editable app choices; Plex remains optional |
| 4. Choose folders | Media, downloads, and small configuration backups | Uses folder picker, can create explicitly approved empty folders, verifies permissions/mount views and space |
| 5. Private access | This computer / home network, server name, owner account | Prepares scoped firewall and gateway changes; never forwards router ports or disables authentication |
| 6. Review | Apps, required downloads, disk space, permissions, restart needs | Produces an immutable settings revision and installation plan |
| 7. Install | Named steps, useful progress, retry/resume | Verifies downloads, installs only selected apps, records ownership, starts and probes services |
| 8. Connect | Plex sign-in and any necessary personal provider choices | Exchanges credentials only server-side for newly owned apps; tests supported cross-app settings before writing |
| 9. Verify | “Your media server is ready” plus unfinished optional tasks | Tests app graph, library paths, LAN access, backup and restart readiness; does not declare skipped steps complete |

Use a short recommended path and an expandable advanced view. Setup persists across browser closure, interrupted downloads, installer restart, and required machine reboot. No auto-sign-in is enabled. A locally authenticated bootstrap handoff replaces asking the user to retrieve a token in a terminal; bind it to a single-use, short-lived setup session and keep credentials out of URLs and logs.

Prerequisites may be downloaded and launched by the future installer only after the user selects the action, reviews terms and elevation, and the supported upstream installation method is verified. Today’s source bootstrap does not implement this.

## Reproduce the useful parts of the current setup

| Reference feature | Fresh-install implementation | Release placement |
| --- | --- | --- |
| Plex plus optional Arr/qBittorrent | Curated adapters install, configure folders/categories and test connections | Core release |
| Seerr requests | Optional install and supported Plex/Arr setup handoff; Seerr owns requests and permissions | Core release |
| Tautulli, Kuma, Cleanuparr | Optional install, monitoring connections, clear per-adapter capabilities; cleanup stays opt-in | Core release, limited Cleanuparr controls |
| Caddy LAN HTTPS and app links | Generated host-specific routes, gateway health, guided public-root certificate trust | Core release |
| Boot with Windows signed out | Verified application-specific tasks/services, startup ordering and bounded recovery | Core release gate |
| Hidden watchdog | Server-side health and bounded owned-service recovery with audit/cooldown; no focus-stealing windows | Core release |
| Space protection | Per-volume hysteresis; default suggestion 50/100 GiB, editable; categories not assumed tags; durable torrent IDs track guard-owned pauses | Full-stack beta gate |
| Small daily backups | Suggested 04:30 local schedule and seven-day retention; consistent supported app snapshots; precise inclusion report | Core release |
| Off-device safety | Optional mounted NAS target, then S3; encryption, destination test, restore test | After first core release |
| Overview, Activity, Health | Freshness on every source, queues/imports, streams, indexers, blocklists, filters, sorting, paging | Core release |
| Archived safety events | Preserve provenance and source IDs without clearing upstream blocks; private retention controls | Full-stack beta |
| Gaming PC operation | Resource limits/presets, optional scheduled work, quiet background operation; no automatic power-plan changes | Core defaults, tuning later |
| 1080p HEVC preference, preserve 4K | Optional reviewed quality-policy preset/translator; existing libraries not mass-replaced | Later |
| Stalled-download rescue | Diagnose and propose next steps; no automatic deletion/blocklist/replacement search | Later, explicit action policies |

Backup warning is practical: same-disk backups recover configuration mistakes, not disk failure. Mark unsupported/inconsistent app snapshots as incomplete. Plex database backup must use an upstream-supported consistency mechanism or reviewed downtime; copying a live database is not enough.

## Day-to-day UI

Use five main destinations: **Home**, **Activity**, **Apps**, **Health**, **Settings**. Home gives the next helpful action, fresh playback/download summaries, storage, and backup status. Activity has Downloads, Imports, Streams and Sources only where supported. Apps shows setup progress, Open, Test, and allowed owned-app actions. Seerr gets a Requests shortcut only when present. Settings groups Storage, Network, Backups, Notifications, Updates and Advanced; Audit is reachable from Health and Settings.

Teach outcomes before implementation: “Downloads can reach your TV library” is more useful than “mount validated.” Keep exact path/API diagnostics available in details. Separate “not selected,” “setup unfinished,” “authentication failed,” “temporarily offline,” and “stale.” Counts should depend on relevant collectors, not become blank because an unrelated optional app is unavailable.

High-value settings should be controllable in Stackarr: chosen apps, folders, ports, app links, schedules, storage thresholds, category mapping, connection targets, backup destinations, notifications, startup behavior, and safe updates. For upstream settings without a stable supported API, explain the limitation and open the exact upstream page. Never label a link-only integration as fully managed.

## Short delivery sequence: demonstrate progress every step

Existing issue numbers remain useful workstreams, but are not a strict dependency chain. Do not wait for public-history decisions to prototype an installer privately.

| Slice | Deliverable shown to the human | Existing issue mapping | Completion evidence |
| --- | --- | --- | --- |
| A | Runtime feasibility report and a fresh Windows reboot demo | #6, #10 | Second LAN device reaches chosen services while host stays signed out; playback and folder tests recorded |
| B | One downloadable installer opening a real wizard without Docker/Python | #5, #7 | Clean supported Windows VM; signed RC when signing is available; unsupported host has clear next step |
| C | “Plex only” installation from that wizard | #2–#4, #8, #10–#11 | Select folders, sign into Plex, play a user-supplied test file from another device |
| D | Add TV/movies and qBittorrent with working settings integration | #12–#14 | Correct categories/root paths/client connections; controlled lawful fixture imports; failed credentials recover without reinstall |
| E | Add optional Seerr and monitoring apps | #15–#16 | Each app installs independently; absent apps hidden; permission/setup handoffs verified |
| F | LAN HTTPS, backups, storage protection and useful health | #18–#20, #25–#26 | Certificate trust guide, restore rehearsal, disk-threshold simulation, gateway outage and partial failure demos |
| G | Friend test and release candidate | #17, #21–#22, #1, #5 | Nontechnical tester succeeds from GitHub download without commands or developer intervention |
| H | Broaden platforms and advanced controls | #23–#24, remaining #26 | Separate platform evidence, NAS agent security review, S3 restore test and supported update paths |

The broad #26 combines updates, HTTPS and Docker-proxy research; split these before implementation. HTTPS belongs before the first LAN release. Docker proxy is later and not required by a local broker. Buildarr/Recyclarr translation, recovery policy editor, hardware tuning, and native non-Windows packages remain follow-on slices.

## Definition of ready to give to another person

- A release asset, not GitHub's source ZIP, is the prominent download. No source build occurs on the recipient machine.
- Fresh supported Windows install completes through UI; dependencies and reboots are explained and resumable.
- The recipient completes a Plex-only path and then optionally adds a second application without reinstalling Stackarr.
- A second LAN device plays a supplied test file, opens the dashboard securely, and sees accurate health.
- Machine reboot while signed out passes the always-on test; Windows automatic sign-in remains disabled.
- App connections, imports, queues and indexers are verified with controlled fixtures; no real indexer subscription is required to run CI.
- Disk-full, internet loss, changed password, app outage and reboot mid-install each have a tested recovery flow.
- Backup restore, ownership-preserving uninstall, and Stackarr update rollback pass in disposable environments. App database downgrade compatibility is checked separately; image rollback alone is not sufficient.
- Keyboard/phone access and novice usability are tested; no user must know an API key, Compose command, UID/GID or port to follow defaults.
- GitHub private tester access is arranged until publication is explicitly authorized. Do not switch repository visibility as part of installer work.

## Next concrete task

Execution kit: [WINDOWS-RUNTIME-LAB.md](WINDOWS-RUNTIME-LAB.md) provides the comparison protocol, read-only readiness inventory, and evidence-ledger commands. Physical/VM execution is pending an explicitly selected disposable Windows environment and LAN observer; unit tests of the toolkit do not certify a runtime.

Build slice A: a bounded Windows runtime feasibility test with the smallest useful stack (Stackarr, Plex, qBittorrent, one Arr app, Caddy). Produce a topology decision with evidence for unattended startup, account/credential access, storage sharing, LAN playback, resource use, and restart recovery. This removes the largest risk before committing to a polished installer that cannot reproduce the current server's behavior.
