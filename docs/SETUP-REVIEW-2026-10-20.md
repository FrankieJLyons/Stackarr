# Fresh-install and product review — 20 October 2026

## Recommendation

Keep Stackarr, but narrow its purpose to beginner setup, connecting existing apps,
plain-language preferences and recovery. Stop adding integrations until an ordinary
user can get from download to a movie and episode playing on their watching device.
The infrastructure already has strong open-source alternatives. Stackarr is worth
continuing if it removes the knowledge needed to connect them.

For a personal Linux server, YAMS or DockSTARTer would have avoided substantial
installer work. For this Windows beginner experience and existing-stack connection,
neither is a demonstrated replacement. This is a documentation comparison, not a
hands-on benchmark of competitors or a claim of uniqueness across the whole market.

## Fresh release exercise

The private GitHub release `v0.1.0-alpha.r8` was downloaded again, rather than using
the local build. Its 342,555,645-byte ZIP matched the published SHA-256:
`fb0335fba892bb668c91a498a420e790339c2ba94a7804051433a32a6e63b31b`.

The extracted executable ran integrated readiness, opened password creation, saved
basic details, accepted Movies & TV and a separate empty media folder, selected
available ports, and installed six apps. Plex, Sonarr, Radarr, Prowlarr, qBittorrent
and Seerr started with fresh configuration volumes. Existing image layers were
cached; this was not a cold-cache network benchmark. Docker was already installed,
so this does not certify clean Windows, WSL setup, vendor prompts or reboot behavior.

The browser exercise at 1440×1000 and 390×844 produced no JavaScript errors or
horizontal phone overflow. Before/after checks confirmed that all pre-existing
containers retained their IDs, images, start times, restart counts, mounts and
ports. No household app settings, startup registrations, firewall rules, Plex
libraries or media were changed. The isolated media sentinel remained unchanged.
Private evidence is in the ignored `test-results/fresh-review-20261020/` directory.

The new Plex server was not claimed with the household account. No provider account
was added. The six-app connection group remains account-blocked; this run did **not**
demonstrate request → download → import → playback. Earlier repository reports
describe tests with generated samples; those are prior evidence, not results of
this review. This is an installed preview, not a newly certified household server.

A separate read-only inventory found **both native Windows and Docker installations**.
The native Sonarr and Radarr each have one root folder and one download client,
with four and seven quality profiles respectively. Native Prowlarr has **three
indexers and two linked apps**: these are settings worth preserving. The existing
Docker Sonarr/Radarr each have six profiles, while Docker Prowlarr has two linked
apps and zero indexers. The instances are not equivalent. Never choose the first
discovered app as the migration source. No credentials or private paths are included here.

## Findings

| Priority | Finding | Consequence / next action |
|---|---|---|
| P0 | Discovery was absent from the visible wizard, unavailable through the Docker controller, and limited to default ports. | Duplicate installs are too easy. Fixed in this branch with explicit connect-only choices and Docker port hints. |
| P0 | Detection does not import settings or transfer ownership. | Do not call it migration. Build verified inventory and connection in place next. |
| P0 | There is no year-based quality policy. | The requested SD/1080p/4K rules cannot currently be expressed. Add previewable assignments using actual native profiles. |
| P0 | Radarr's standard SD is not a good beginner preset. | The inspected Docker profile permits WORKPRINT, CAM, TELESYNC, TELECINE and DVDSCR. Review/create a curated SD profile, not just a matching name. |
| P0 | Cleanuparr starts with protection jobs off. | Installed does not mean protected. Show actual filter state and offer a reviewed media-download protection preset. |
| P1 | An unfinished Plex/Seerr account blocks saving all six apps' connections. | `controller_connections.finish_owned` waits for all account apps before activating core apps. Add durable per-app completion with revision checks. |
| P1 | Native and Docker instances differ in settings and source coverage. | Native Prowlarr has three sources; the Docker preview has none. Import from the verified intended instance and test movie/TV categories before claiming readiness. |
| P1 | Existing Plex paths are not automatically reconciled. | Read actual library roots, map them to Arr/downloader paths and verify access before proposing changes. |
| P1 | Local startup does not prove household playback or signed-out reboot. | Add an explicit home-network step and second-device/reboot acceptance. |
| P2 | Documentation mixed old launchers, current releases and lengthy historical test narratives. | The README now gives one current download path and links detailed evidence. |

These priorities are product judgments. An expert walkthrough cannot replace
observing first-time users.

## The easiest setup

Do not require users to configure Docker and Plex independently and then begin
Stackarr. For a fresh supported Windows machine, offer one Stackarr download,
guide Docker prerequisites once, and install selected media components through the
same wizard. Windows/WSL requirements and vendor prompts remain real work; explain
and resume them. [Docker's installation guide](https://docs.docker.com/desktop/setup/install/windows-install/)
documents current prerequisites and installation modes.

If Plex already exists, keep it. A mandatory reinstall risks libraries, paths,
accounts and playback. Native Plex plus Docker Arr apps is a reasonable existing
installation case once mapping is verified; it should not be a second mandatory
fresh-install path. Test hardware transcoding and startup before sign-in before
deciding whether native Plex should become the Windows default. Current evidence
does not settle that tradeoff.

The user-facing journey should ask:

1. **Watch files I already own** or **Find and follow movies and TV**.
2. **We found these apps — keep them?** Show a choice when multiple instances exist.
3. **Where is your media?** Reuse detected Plex roots or choose one fresh parent
   folder. Show capacity and a useful estimate for 4K.
4. **What quality?** Simple defaults, an older-title rule and individual exceptions.
5. **Where will downloads come from?** Reuse verified provider settings or guide
   their account details. Existing-files mode skips this.
6. **Review and set up**, followed by one saved checklist through actual playback.

Distinguish Installed, Connected, Sources ready and Ready to watch. Hide ports,
keys and container paths behind details unless needed to resolve a problem.

## App count

Six background services are defensible; six independent setup experiences are not.

| Role | Default |
|---|---|
| Watch existing files | Plex only, preferably the existing server. |
| Full movie/TV workflow | Plex, Sonarr, Radarr, Prowlarr, qBittorrent and Seerr. |
| Indexer manager | Prowlarr. Do not add Jackett too by default; support an existing Jackett feed. |
| Requests and permissions | Keep Seerr as the backend rather than rebuilding its account/permission system. |
| Download protection | Reviewed downloader exclusions; Cleanuparr optionally adds queue management. |
| Viewing statistics | Tautulli optional after first playback. |
| Additional uptime monitoring | Uptime Kuma optional; Stackarr already reports basic service state. |
| Subtitles, unpacking, VPN, transcoding tools | Only when the selected workflow requires them; no further default expansion now. |

## Connect existing apps before migrating them

The quickest useful conversion brings existing apps into Stackarr while leaving
them running where they are. Moving their databases can come later.

Detect addresses, verify app/server identity, authenticate, then read folders,
profiles, downloader categories, sources and Plex libraries. Show “keep these
settings; add only these missing connections.” Import secrets only from a clearly
identified installation or approved backup, encrypt them and never forward them
to an unverified discovery candidate. Container labels or a login page are hints.

Keep **connected** separate from **managed by Stackarr**. An API key must not grant
restart/update/remove ownership. Preserve title profiles, source configuration,
categories, schedules, Plex library/server identities and Seerr users/permissions.
Do not retarget in-flight downloads as an onboarding side effect.

Later managed migration needs application-consistent backups, cloned configuration
in separate volumes, path translation, duplicate scheduled searches disabled in
the clone, compatibility/restore validation and an explicit cutover with rollback.
Two active writers must never share an application database. Native custom ports,
NAS hosts and arbitrary Compose packages need specific support, not a generic
unsafe import button.

## Requested SD / 1080p / 4K rules

Use separate movie and TV policies. Define TV year as series premiere year by
default: a series starting in 1999 remains in the older group even when later
seasons air after 2000. Episode-year rules require a different design because
Sonarr quality is assigned to a series.

| Precedence | Condition | Assignment |
|---|---|---|
| 1 | Explicit title exception, using stable media ID | Chosen profile, e.g. 4K |
| 2 | Known year < 2000 | Curated SD |
| 3 | Known year >= 2000 | 1080p |
| 4 | Missing/invalid year | Needs review; retain existing assignment |

The year 2000 belongs in 1080p. Preview the title count and old/new profiles.
Default to new requests only. Applying to existing titles is a separate review,
with original assignments saved for undo and stale-data checks. Resolve live profile
IDs, allowed qualities and upgrade cutoffs; never assume numeric IDs or fuzzy names.
Manual exceptions must survive future synchronizations.

Changing a profile does not shrink or convert existing files. Searches and upgrades
are separate choices, not a side effect of saving rules. Missing SD/4K availability
must remain visible. The inspected Docker HD-1080p/Ultra-HD profiles are resolution-specific,
but custom profiles elsewhere can differ. Docker Radarr's inspected SD includes undesirable
camera/screener sources, so offer a curated profile and review changes explicitly.

Use Recyclarr or one alternative to manage profile/format definitions. Stackarr's
value is applying understandable rules to titles and explaining their effects.
A profile synchronizer alone is not the requested assignment engine.

## Protection and Plex import

“No viruses ever downloaded” cannot be guaranteed. Cleanuparr filters known patterns
and can skip/remove downloads on a schedule; it is not a general antivirus engine.
Its timing, ignored downloads and mixed-file settings affect coverage.
[Cleanuparr Malware Blocker](https://cleanuparr.github.io/docs/configuration/malware-blocker/)
documents those controls.

Offer reviewed native qBittorrent exclusions for executable/script/shortcut content,
preserving existing exclusions and explaining any effect on a shared download
client. Destructive cleanup and replacement searches are separate opt-ins. Verify
with harmless dummy filenames, not malware. Archives and legitimate non-media
downloads require explicit compatibility choices. Retain host antivirus and updates;
extensions are not proof of safe content.
[Cleanuparr's qBittorrent scenario](https://github.com/Cleanuparr/Cleanuparr/blob/main/docs/docs/setup-scenarios/1_qbit-built-in.mdx)
describes native exclusions combined with queue cleanup.

Downloads belong in staging; Sonarr/Radarr import finished media into the actual
Movies/TV library, then Plex indexes it. Verify mount visibility, permissions,
categories, completed-download handling and import → scan → availability. Consistent
mounts permit hardlinks where supported, but path text alone does not prove hardlinks
work. Keep existing Plex library identities and roots.
[TRaSH's folder guide](https://trash-guides.info/File-and-Folder-Structure/How-to-set-up/Docker/)
is a useful implementation reference.

## Existing projects and reuse

Official documentation/repositories reviewed on 20 October 2026; competitors were
not installed on this host. These are documented capabilities, not measured outcomes.

| Project | Useful overlap | Recommendation |
|---|---|---|
| [YAMS](https://yams.media/install/steps/) | Guided stack installation and Docker setup on supported Debian/Ubuntu. | Strong personal-server starting point if Linux is acceptable. Study the concise journey. |
| [DockSTARTer](https://dockstarter.com/) | App selection and Docker configuration across many integrations. | Reuse deployment knowledge; it does not by itself complete the Windows beginner migration goal. |
| [Saltbox](https://github.com/saltyorg/Saltbox) | Ansible-based Docker cloud media deployment. | Learn from operational roles; broader server administration is outside the first release. |
| [Buildarr](https://github.com/buildarr/buildarr) | Declarative Arr settings, relationships and configuration export. | Useful design reference. GitHub reported last push in May 2024; verify present API compatibility before adopting it. |
| [Recyclarr](https://recyclarr.dev/guide/features/) | Profiles, custom formats, sizes, naming and previewable sync. | First integration to evaluate for quality definitions; keep title assignment in Stackarr. |
| [Configarr](https://configarr.de/) | YAML-driven Arr settings and TRaSH-based profiles/formats. | Alternative to evaluate; avoid two managers overwriting the same settings. |
| [Profilarr](https://github.com/Dictionarry-Hub/profilarr) | Radarr/Sonarr configuration management. | Compare its quality-management UI before building an advanced editor. |
| [Notifiarr](https://notifiarr.com/) | Notifications, monitoring and integrations. | Optional integration, not a substitute for local installation/adoption. |

No third-party implementation was copied for these changes. Prefer documented APIs,
configuration export or separately versioned components over an untracked fork.
If code is vendored, pin its revision and preserve license/notices. Stackarr's license
does not replace upstream terms; see [LICENSE-NOTES.md](LICENSE-NOTES.md). GitHub
reports Recyclarr as MIT, Buildarr as GPL-3.0 and Profilarr as AGPL-3.0. Treat each
project's reuse and distribution requirements separately.

## Changes and next delivery order

This branch restores visible discovery, delegates it through the authenticated host
controller, adds bounded Docker port hints and explicit connect-only draft choices,
preserves API/browser address differences, exposes checks in a connection-only
launcher, clarifies Cleanuparr's disabled protection and simplifies the README.
Both packaged components must be rebuilt for the new RPC. R8 remains unchanged.

The full Python suite passed: 947 tests, 3 skipped. A subsequent focused run passed
63 discovery/onboarding/controller tests, including the final host-capability change.
The 77-test Node suite and synthetic multi-viewport browser smoke passed; all three
discovery UI tests then passed with the final presentation coverage.
An isolated source dashboard found the original custom-port Sonarr and saved a
connect-only draft, with no browser errors or phone overflow. The separate R8 review
installation is retained at `http://localhost:29480`; its local test password is in
the ignored `test-results/fresh-review-20261020/access-private.json`. It has no content
source or claimed Plex account. Temporary source-preview processes were stopped.

Next: (1) verified connection in place and settings inspection, (2) per-app account
completion, (3) previewable quality rules with curated profiles, (4) tested download
protection and detected Plex mapping, (5) three novice first-watch sessions plus
clean-Windows, signed-out reboot and second-device acceptance. Defer new apps and
advanced editors until those pass.

## Native import implementation — 21 October 2026

The first delivery priority is implemented: standard Windows Sonarr, Radarr and
Prowlarr settings can be detected, reviewed and imported into Stackarr. This keeps
the apps in place, stores credentials privately, imports a sanitized settings
snapshot and changes their setup choices to connect mode. Imports are read-only;
native services receive no installation or lifecycle ownership. See
[the import contract and limits](DISCOVERY.md#importing-native-windows-settings).

The real packaged test used the existing isolated dashboard at
`http://localhost:29480`. Its dashboard and Windows controller were updated together
using Stackarr's reviewed update mechanism, with encrypted checkpoints retained.
The published GitHub R8 release and the working dashboard on port 28000 were not
changed. The final local package is `Stackarr-Native-Import-Final-20261021.zip`
under the ignored review directory; it is an unsigned development build.

The browser detected and imported the intended native instances: Sonarr with one
library root, one downloader and four quality profiles; Radarr with one root, one
downloader and seven profiles; Prowlarr with three sources and two linked apps.
The source-sharing check recognized three Sonarr links and two Radarr links.
Windows HTTP Host restrictions required preserving the original loopback Host
header on Docker-to-host requests. Native localhost aliases are reconciled for
source-sharing checks without changing the original configurations.

Desktop and phone browser tests passed with no JavaScript errors or horizontal
overflow. Credential-free previews, reviewed saves, draft conversion, read-only
write rejection, source sharing and real status collection all passed. Native
configuration/settings fingerprints stayed identical. All 17 protected containers
(the original stack and six lab media apps) retained their IDs, start times,
restart counts, images, ports and mounts. Only the isolated Stackarr dashboard
and controller were updated.

Validation: the full Python suite passed with 966 tests and 3 skips; the final
native source-alias change then passed 24 focused tests, including its new case.
All 81 JavaScript tests, the existing browser smoke, Ruff and whitespace checks
passed. Private evidence and screenshots are in the ignored review directory.

This completes connection in place for those three native Arr apps. Per-app
account completion, quality rules/curated profiles, download protection and
existing Plex path reconciliation remain the next priorities. Native Plex token
import, qBittorrent login recovery, custom native data directories and database
migration are not implemented by this slice. No quality rules or protection
settings were applied to the working stack.

## Per-app completion and quality rules — 21 October 2026

The next two priorities are implemented. Ready apps now connect independently of
unfinished accounts; saved progress and encrypted ownership receipts survive
restarts. Existing native imports remain protected. TV and movie rules support
an exclusive year cutoff, separate older/newer quality choices and stable-ID title
exceptions. New Stackarr requests use the rules after verifying Seerr's target
and the actual profile definitions. Existing-library assignment has a separate
review, durable per-title results and guarded undo. See
[QUALITY-RULES.md](QUALITY-RULES.md) for scope and limits.

Live testing used the six-app isolated installation, with a separate temporary
dashboard on port 29490 so the original imported connections on 29480 could stay
read-only. Three unmonitored titles were added to each isolated Arr app as metadata
fixtures. Real profile creation, the 1999/2000 boundary, title exceptions, profile
assignment and undo passed through the browser and real APIs. Original profile
assignments were restored; monitoring, paths and tags stayed unchanged. No search
or download was started. Desktop and phone checks had no JavaScript errors or
horizontal overflow. Native settings fingerprints and all 17 protected container
identities, start times, restart counts, ports and mounts were unchanged.

The final full Python suite passed with 1,003 tests and 3 skips. All 84 JavaScript
tests, the browser smoke and Ruff passed. The isolated Plex server remains
unclaimed and Seerr account setup remains unfinished; future-request routing was
tested with authenticated API fixtures rather than claiming a user's Plex account
or starting a download. Download protection and detected Plex path reconciliation
remain the next delivery priorities.

The final packaged release, `Stackarr-Accounts-Quality-Final-20261021.zip`, was
installed into the isolated dashboard/controller on port 29480 through reviewed
self-update. A first candidate was rejected because empty feature tables changed
the startup fingerprint; automatic recovery restored the previous isolated
release. Feature tables now appear only on explicit saves, with a regression test
ensuring startup and read-only previews preserve the fingerprint. The replacement
package passed candidate checks and completed its update with an encrypted
checkpoint retained.

Packaged browser acceptance confirmed qBittorrent connected and its private login
became available while Plex and Seerr remained unfinished. All three native
imports stayed unchanged and read-only, persisted per-app progress survived a
reload, and attempted native quality writes were rejected. Desktop/phone checks
passed again, with unchanged native settings fingerprints and all 17 protected
container records.

A separate source preview is left running at `http://localhost:29490`, using the
same local test password as the isolated dashboard. Its HTTP integration transport
allows only the lab Sonarr and Radarr ports (18990 and 17879), including for writes.
It has sample year/title rules, unmonitored metadata fixtures and undo history.
The test assignments were undone. The packaged dashboard on 29480 retains the
native imports for read-only inspection; the working dashboard on 28000 and the
published R8 release were not updated. Private test evidence, process information
and local development packages remain under the ignored fresh-review directory.
## Download protection and library mapping follow-up — 2026-10-21

Implemented reviewed qBittorrent exclusions, automatic-program hardening,
preservation of existing patterns, stale-change checks and durable recovery.
Added native Plex account/library discovery in read-only mode and automatic
selection of a unique TV/movie library. Folder routing uses current host-owned
installation receipts and verified shared mounts, with explicit selection for
ambiguous libraries. It configures new-download category paths and the Arr import
root, and can prepare Plex notifications with path translation. Existing files,
titles, downloads, custom connections and native settings remain in place.

The isolated packaged update succeeded. Final tests: 1,032 Python passed (3
skipped), 87 JavaScript passed, browser smoke and desktop/phone acceptance passed.
The live stopped-torrent test verified actual file priorities and zero downloaded
bytes. Native Plex was detected and imported read-only; all 17 protected Docker
containers and native Arr/Plex fingerprints remained unchanged.

At that point the isolated Plex instance was unclaimed. Claimed-library success
was initially tested with an explicit Plex protocol fixture and real isolated
Arr/qBittorrent apps. The real playback follow-up below closes that test gap.
The working Plex media folders are
intentionally not mounted into the isolated apps. The UI detects this and blocks
mapping rather than changing mounts. See [scope and verification](DOWNLOADS-AND-LIBRARIES.md).

## Real download-to-playback follow-up — 2026-10-21

The owner claimed the isolated Plex server on port 42401. The real account
completion and library-mapping flows then succeeded, including Seerr setup,
import notifications and automatic library discovery. Stackarr requests for an
original movie fixture and an original episode fixture passed through Seerr,
Prowlarr, a separate private local seeder, qBittorrent, automatic Arr imports and
automatic Plex discovery. Imported file hashes matched the source files; no
manual imports or scans were needed.

Both 720p samples played in real Plex Web for 12 seconds, with 17 decoded frames,
zero dropped frames and no playback errors for each. Plex independently reported
both sessions as playing. Stackarr's availability and Plex links were also
verified. This tests colour-bar/silent fixtures, not the named films or episodes.

Temporary source and seeder infrastructure was stopped after testing; imported
samples remain in the test Plex. Temporary size limits were restored and test
titles were left unmonitored. All 17 protected container records and native
Arr/Plex fingerprints remained unchanged. No additional sign-in is required for
this isolated server. Details and evidence locations are recorded in
[download-to-playback verification](DOWNLOADS-AND-LIBRARIES.md#real-download-to-playback-follow-up).
