# Stackarr 0.2 usability and first watch plan

> [!NOTE]
> Historical plan. The [current roadmap](ROADMAP.md) supersedes this document's release priorities and status claims as of 16 November 2026. Some unchecked items below shipped in 0.1.0; retain this document as design history, not a current feature checklist.

Planning date: 20 October 2026. Baseline: the private Alpha 0.1 package documented in [ALPHA-0.1-TEST.md](ALPHA-0.1-TEST.md).

The next release should let a beginner install Stackarr, add a movie or TV show, understand its progress and watch it on their chosen device. Everyday controls should describe those tasks. Plex remains responsible for playback, Seerr for requests, and the Arr apps for finding and importing media.

This plan sets the v0.2 usability scope and delivery order. [COMPLETION-PLAN.md](COMPLETION-PLAN.md) retains the technical release requirements. Current development remains Docker-only on this computer, using isolated fixtures and installations. Clean Windows, second-device and signed-out startup acceptance remain explicit resource-dependent gates.

## Current implementation

The latest separate engineering package is `dist/Stackarr-One-App-Preview-20261020-r8.zip`.
It implements the six-app request preset, persistent setup, compact storage/quality
choices, one Plex sign-in followed by reviewed library/Seerr preparation for owned
apps, private matching app connections, and one **Test & connect source** action.
Home supports discovery, movie requests, selected TV seasons, actual per-title
quality profiles, saved requested-quality labels, import progress and verified
Plex title handoff. Existing shows retain their native quality. Advanced/manual
setup remains available. Main installation and previously deleted test libraries
are preserved; test containers and design-preview processes are removed afterward.

Validation includes 940 passing Python tests (3 skipped), 75 passing Node tests,
desktop/mobile design checks, 29 frozen checks and the exact network-disabled
dashboard image. Native Seerr/Arr checks confirm selected quality without changing
defaults. The extracted package now has real Plex-account and native Seerr
onboarding evidence, seven generated-sample downloads/imports, and actual movie
and episode playback at the selected 1080p/720p qualities. The follow-up test now
passes automatic discovery, Seerr availability and playback without manual scans.
Reviewed discovery uses durable import checkpoints and matching Plex section scans;
Stackarr must remain running, though the browser window can close. Stackarr offers persistent library preparation from the
selected Windows folder, avoiding Plex's Docker folder picker. A six-app preview
update/rollback/update retained settings, media and identities; the older nine-app
alpha replacement rehearsal remains pending. Clean Windows, another device and
signed-out restart remain acceptance gates. Details are in [PROGRESS.md](PROGRESS.md).

## Success criteria

- A new user completes the supported fresh setup without a terminal, developer help or copying credentials between newly installed core apps. Personal source credentials remain a guided owner choice.
- The interface always distinguishes installed, connected, configured and ready for the selected workflow.
- A user can add a movie, choose TV seasons and follow future episodes without understanding the word "monitored."
- Each title explains whether it is waiting, downloading, being imported, available in the library or blocked, with a useful next action.
- A supported household device plays the imported sample and continues to work after the server restarts while Windows remains signed out.
- Three novice walkthroughs pass. Target at most ten minutes of active setup interaction, measuring download, reboot and upstream account-creation time separately. This is a target to validate.

An engineering preview can ship privately while external checks remain open, with those limits stated. Consumer readiness requires the complete acceptance matrix below.

## Preserve the working foundation

Reuse the existing integrated readiness flow, reviewed Docker prerequisite setup, automatic ports, folder picker, generated logins, private credential handoff, reviewed connections, saved operations and maintenance/recovery controls. Keep the current one-Movies/one-TV-library layout and independent 1080p/4K request preferences.

The alpha demonstrates nine connected apps and local generated-sample playback. Its manual run did not exercise acquisition/import because content sources were not configured. Earlier isolated movie/episode transfer and Seerr request tests are component evidence; the new packaged journey must repeat them together and play the imported files.

## The intended experience

1. **Welcome:** choose "Watch media I already have," "Find movies and follow TV shows," or "Connect apps I already use." Keep Custom available.
2. **Check this computer:** explain readiness, required downloads, elevation and any restart. Save progress across interruptions.
3. **Choose storage:** choose one suitable folder, show free space, and keep exact paths and container details under Advanced.
4. **Review and install:** summarize the selected features, applications, storage changes and downloads in one understandable review.
5. **Connect accounts and sources:** guide Plex and Seerr sign-in, verify the selected server/libraries, and explain the role and requirements of content sources.
6. **Try a movie and an episode:** confirm request/search, transfer, import, library appearance and local playback with permitted fixtures.
7. **Watch on another device:** guide the supported Plex client, confirm library access and actual playback, and explain server availability.
8. **Everyday use:** open Watch library, Find a movie or show, or My requests. Reach app administration through Manage server.

Show one recommended next action at each unfinished checkpoint. Optional apps must not create requirements for users who did not select them.

## Delivery sequence

| Order | Deliverable | Dependency | Completion evidence |
| --- | --- | --- | --- |
| 1 | Journey, readiness and title-state contracts | Alpha baseline | Supported paths and failure states agreed; API feasibility checked |
| 2 | One persistent setup journey | 1 | Packaged minimal, request and mixed setup/resume scenarios |
| 3 | Guided sources and complete local request/import/playback | 2 | Original movie and episode complete the exact packaged workflow |
| 4 | Viewer home and progress for each title | 1 and 3 | Correct cross-app state, supported actions and accessible refresh |
| 5 | Reliable home access and installed Windows product | Runtime feasibility; integrate 2–4 | Clean install, second-device playback and signed-out restart evidence |
| 6 | Novice testing and private release candidate | 2–5 | Three successful walkthroughs and release checks |

Investigate Windows runtime, storage and home-access feasibility alongside steps 1–2; these risks must inform the installer before packaging is finalized. Work that needs another machine/device stays pending while independent UI and isolated-Docker work continues.

## Step 1 Define the journey and readiness

- [ ] Define feature presets and their required apps. The recommended movie/TV request experience includes Plex, Seerr, Sonarr, Radarr, Prowlarr and qBittorrent. Keep Tautulli, Uptime Kuma and Cleanuparr optional.
- [ ] Specify the checkpoints, required evidence, next action and resumable state for each supported path. Separate unavailable/stale observations from confirmed failures.
- [ ] Verify supported Seerr search/request and Plex playback-link behavior against the pinned versions. Establish how household identity and permissions reach each upstream action; an owner connection must not grant everyone owner access.
- [ ] Define stable title matching using upstream media identifiers, with season/episode identity where needed. Preserve upstream IDs and handle duplicate editions, requests and partial seasons.
- [ ] Define readiness for watching existing media separately from readiness for requesting new media. A missing source must not prevent playing an existing library.

**Done when:** each screen and title state has an explicit meaning, evidence source and next action. No "Ready" label is based only on a healthy container or collector.

## Step 2 Simplify and connect setup

- [ ] Present feature choices before the app catalog. Show the selected apps and install/connect details in an expandable review.
- [ ] Replace scattered completion panels with one saved checklist: computer, storage, installation, accounts, sources, connections and verification.
- [ ] Detect completed Plex/Seerr steps, retain the correct server/library selection and provide a clear return from upstream sign-in. Preserve the existing blocked-popup fallback.
- [ ] Show a friendly folder label and available space. Keep full paths, port settings, UID/GID and endpoint addresses under Advanced. Verify access from the actual services using bounded test files.
- [ ] Verify that downloader-to-library imports use same-filesystem hardlinks where supported. When an extra copy is required, explain the additional space used while downloads are retained and include it in storage estimates.
- [ ] Consolidate routine setup reviews into the journey while retaining clear approval for installation, privileges, network changes and maintenance effects.
- [ ] Cover Plex-only, full request setup, monitoring-only and mixed existing/new apps. Adding an app later must preserve existing settings and avoid duplicate containers/connections.

**Done when:** users can leave and resume without reconstructing what happened, and every unfinished setup has one clear recommended action. No unselected companion produces a task or warning.

## Step 3 Make sources and requests understandable

- [x] Add a "Where will your media come from?" step covering existing files and supported content sources. Explain provider accounts and credentials before requesting them; do not imply catalog discovery guarantees a downloadable copy. The guided subset uses Prowlarr's advertised torrent-provider forms with qBittorrent; complex forms and custom feeds have explicit advanced setup.
- [x] Test source authentication, enabled categories, sharing into Sonarr/Radarr and usable search results. Distinguish "no working sources" from "no matching release." Separate movie/TV diagnostics require verified category/authentication evidence; empty results require a fresh successful search-history record. Bounded checks cover three enabled sources and do not download media.
- [ ] Offer "Find existing episodes and follow new ones," "New episodes only" and season selection. Verify the initial search action rather than relying on monitoring alone.
- [ ] Use the existing request-quality choices consistently in Seerr and the Arr connections. Explain rejection by quality, size or release availability in ordinary language.
- [ ] Make repeated submissions safe and visible: show an existing request or library item rather than creating duplicate work.
- [ ] Exercise an original movie and episode through Seerr, Arr, downloader, import and Plex scan, then play the imported files locally. Include an existing-media path that needs no downloader/source. The 20 October native-UI Docker test now proves real browser requests, automatic transfer/import with matching hashes and hardlinks, and movie/episode Plex Web playback after an explicit library scan. Exact packaged/cloud-account onboarding and automatic availability remain open.
- [x] Close the library-refresh gap: reviewed automatic scans after successful imports now pass the claimed-server movie/TV request-to-playback retest without manual scans. Durable checkpoints coalesce batches and retry failures; Seerr updates availability through its own schedule. See [AUTOMATIC-IMPORT-TEST.md](AUTOMATIC-IMPORT-TEST.md). Large-library scale testing remains separate.
- [x] Add reviewed native Plex import/upgrade notifications and Seerr recently-added checks every minute when its default schedule is unchanged. Preserve existing notifications/custom schedules, verify masked saved credentials through native tests and bind the selected server/libraries/import roots. Real native-app requests/imports, refresh callbacks and scheduled movie/season status transitions pass against a protocol simulator; the claimed-server gate above remains open because the owner kept the new disposable Plex unclaimed.
- [x] Handle a claimed Plex server with no libraries as an explicit setup step. The separate Seerr 3.5.0-stackarr.2 preview normalizes a verified empty response, retains errors for malformed/authentication failures, explains missing libraries and offers explicit continuation without them. Real Plex sign-in in the same embedded-browser tab returns to Seerr, and normal setup reaches Discover with the test libraries still deleted. The image is hash-pinned in the new ZIP; fresh-Windows/package onboarding and request availability remain separate gates.

**Done when:** the exact packaged flow completes both fixtures, with matching imported bytes and the correct libraries, without inter-app secret copying or manual upstream configuration repairs.

## Step 4 Make everyday use about titles

- [x] Build a home screen with Watch library, Find a movie or show, My requests and Ready to watch. Delivered as Home, Your requests and Your library, with available-title rows and operations under Manage server. See the 20 October title-home preview in PROGRESS.md for its owner-only and acceptance boundaries.
- [x] Use supported Seerr search/request capabilities and Plex playback links first. Retain their ownership of request and playback data; do not build a separate streaming player. Native browsing is checked; real claimed-server playback acceptance remains separate.
- [ ] Correlate per-title observations into Requested, Waiting for release, Looking for a copy, Downloading, Adding to library, Available in library and Needs attention. Show partial-season availability accurately.
- [x] Offer Play only for a known library item with an appropriate destination. Implemented as Open in Plex after live machine/key/type verification and TMDB matching when provided. Real local movie/episode handoff and playback now pass following automatic scans; second-device playback remains separate.
- [ ] Explain blockers such as sources offline, no suitable copy, download stalled, import access denied, disconnected drive and Plex unavailable. Offer the supported repair or exact relevant upstream page.
- [ ] Replace full-screen polling updates with targeted updates that preserve keyboard focus, expanded details, filters and scroll position. Honor the configured refresh interval.
- [ ] Validate keyboard use, error announcements, screen-reader labels, 200% zoom, touch targets, contrast and phone layouts for the complete journey.
- [ ] After the direct request path works, offer optional Plex Watchlist auto-request with explicit permissions, user activation and its standard-quality limitation. Show delayed synchronization honestly.

**Done when:** a user can find a title, understand the action offered, follow its progress and open the correct playable item. Stale upstream data cannot silently become a fresh success or missing-title claim.

## Step 5 Finish home access and Windows delivery

- [ ] Resolve the alpha's portable-state/AppData Docker visibility limitation. Choose stable application/state directories and verify access from the packaged controller and containers.
- [ ] Specify retained-alpha-state detection and reviewed migration, preserving accounts, server identity, settings, ownership receipts and media. Moving or deleting the downloaded installer must not break the installed product.
- [ ] Deliver an installed entry point, Start menu shortcut and quiet background startup using the runtime proven by the Windows lab. Resume prerequisite setup after an interruption/reboot.
- [ ] Add a guided Home network option with stable browser/app links, trusted HTTPS for Stackarr, narrowly scoped access changes and a private controller. Validate Plex client connectivity separately from dashboard access.
- [ ] Provide supported TV/phone pairing instructions, library selection and playback tests with audio/subtitles. Distinguish local access from remote viewing and any applicable upstream account requirements.
- [ ] Test real sleep and restart behavior. Offer reviewed availability settings; verify the selected services work with Windows signed out and automatic sign-in disabled.
- [ ] Prove any advertised hardware-transcoding capability on actual supported hardware. If Docker cannot meet an essential requirement, record the failure and revisit the deployment choice before advertising that capability.
- [ ] Provide guided owner password recovery and concise, redacted diagnostics for setup failures.

**Done when:** the same candidate installs on a clean supported PC, survives restart, and plays the imported sample on another supported home device. Signing and actual Windows/native-dialog tests remain required for consumer distribution.

## Acceptance matrix

| Scenario | Required result | Environment |
| --- | --- | --- |
| Fresh minimal and full request setup | Correct features, accounts, connections and preserved progress | Isolated packaged Docker now; clean Windows later |
| Original movie and episode | Request/search, download, import, Plex visibility and playback all pass | Isolated packaged Docker and local playback |
| No source, no match, future release, quality rejection | Distinct explanation and next action; request preserved | Controlled fixtures |
| Network loss, interrupted download and port conflict | Existing resume/recovery flows work within the new journey | Isolated packaged installation |
| Import denied, disk full and disconnected drive | Clear blocker, retained media/downloads and safe recovery | Disposable storage fixtures |
| Hardlink-capable and copy-only storage | Actual import behavior verified; retained-download space impact explained accurately | Controlled filesystem and import fixtures |
| Expired credentials, unavailable Plex and stale data | Working features remain usable; no false zero or success | Controlled faults |
| Add another app, retry, preview-state migration | No duplicates or overwritten user settings; identity retained | Isolated copies of retained state |
| Browser closure, keyboard, zoom and phone | Progress and interaction context preserved | Browser automation plus human checks |
| TV/phone playback and subtitle compatibility | Actual local playback; device-specific instructions work | A second supported device |
| Clean install, prerequisite reboot and signed-out boot | No terminal/developer help; authenticated services return | Disposable Windows environment |
| Household permissions and revocation | Correct request/library access; no owner privilege leakage | Real second test account; retain synthetic coverage |

Reuse the current preservation, maintenance and security regression checks. Add tests for new behavior and changed boundaries; repeat broader checks when failures or new changes justify them. Record candidate versions, outcomes and remaining gates in [PROGRESS.md](PROGRESS.md).

## Novice testing and release

- [ ] Recruit three people unfamiliar with Docker: one existing-library user, one full request user and one household viewer. Each performs the relevant install/request/watch tasks without coaching; installers also add an app later.
- [ ] Record every hesitation, request for help, wrong turn and failed task. Measure active interaction and total elapsed time separately, fix recurring blockers and repeat affected tasks.
- [ ] Build a private candidate from the tested revision. Include accurate setup instructions, component inventory, checksums, attribution, support scope and retained-data uninstall behavior.
- [ ] Sign the installer when a signing identity is available and verify the exact downloadable artifact. Do not equate signing with guaranteed absence of reputation prompts.
- [ ] Reconcile existing roadmap checkboxes with verified evidence before release. Publish publicly only through the existing audited-export/publication process.

Needed resources are a disposable supported Windows environment, a second playback device, permitted test media, selected source/test accounts, a second Plex test identity, three novice testers and a signing identity. Reestimate delivery after the packaged local workflow and Windows runtime/storage checks; these determine the remaining integration effort.

## Deferred scope

Keep remote-internet access, NAS/macOS/ARM rollout, a custom player, broad catalog personalization, cloud backup destinations, major-version migrations, automatic download rescue and destructive cleanup outside this usability release. Existing optional maintenance remains available within its documented support boundaries.

## First implementation package

1. Define the saved checklist and readiness contract using existing deployment/account/source evidence.
2. Add the six-app request preset, keeping every app independently optional.
3. Implement the single-next-action setup view and compact folder display.
4. Correct polling and preserve focus/expanded state on refresh.
5. Demonstrate resume and correct next actions for Plex-only, full requests, monitoring-only and mixed setups in an isolated packaged installation.

Primary implementation areas are `stackarr/static/setup.js`, `setup_choices.js`, `setup_accounts.js`, `app.js`, `help.js`, `app.css`, and the onboarding/deployment/connection APIs. Changes to readiness or lifecycle behavior need matching server-side evidence and the existing review/ownership protections.

## Research supporting the priorities

Forum reports are qualitative signals. The proposed behavior above is a Stackarr product decision.

- Monitoring/backlog-search confusion: [Sonarr discussion](https://www.reddit.com/r/sonarr/comments/1ajs9tj/) and [official Sonarr FAQ](https://github.com/Servarr/Wiki/blob/master/sonarr/faq.md#how-does-sonarr-find-episodes).
- Downloads that never reach the library: [Radarr discussion](https://www.reddit.com/r/radarr/comments/1k82nb8/) and [Servarr Docker paths guidance](https://github.com/Servarr/Wiki/blob/master/docker-guide.md#consistent-and-well-planned-paths).
- Unclear content-source requirements: [Sonarr discussion](https://www.reddit.com/r/sonarr/comments/1ptipv5/indexers/) and [Prowlarr quick start](https://wiki.servarr.com/en/prowlarr/quick-start-guide).
- Household difficulty finding Plex libraries: [Plex library-pinning discussion](https://www.reddit.com/r/PleX/comments/1iu061f/pinning_libraries_is_too_confusing_for_many/).
- At-home playback classified as remote: [Plex user report](https://www.reddit.com/r/PleX/comments/1tc9oma/plex_says_im_remote_watching_from_within_my_house/) and [official playback requirements](https://support.plex.tv/articles/requirements-for-remote-playback-of-personal-media/).
- Watchlist automation requirements and limitations: [official Seerr guide](https://docs.seerr.dev/using-seerr/plex/watchlist-auto-request/).
- Runtime/reboot constraints: [Docker Windows installation](https://docs.docker.com/desktop/setup/install/windows-install/) and [Docker startup settings](https://docs.docker.com/desktop/settings-and-maintenance/settings/).
