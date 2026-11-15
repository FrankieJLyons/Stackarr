# Current delivery checkpoint — 20 October 2026

R8 publication review: portable source/history and the exact package were checked
for personal credentials, including decoded image layers and compiled project
constants. Machine-specific test harnesses and private evidence remain local.
Pinned CI secret scanning and stricter export/artifact exclusions are included.
See [RELEASE-R8-SECURITY.md](RELEASE-R8-SECURITY.md).

## Automatic discovery fixed; request-to-playback retest passed

Latest separate engineering package: **Stackarr-One-App-Preview-20261020-r8.zip**,
image **stackarr:auto-import-20261020-r2**, matching
`automatic-import-runtime-r2/StackarrPreview.exe`.

The real Plex-account movie/TV retest now passes **without manual scans**. Through
Stackarr Home, one movie was requested at **1080p** and TV season one at **720p**.
The real source/downloader/Arr pipeline imported all seven generated originals
(13,241,396 matching bytes, hardlinked). Reviewed Stackarr discovery automatically
scanned the matching sections; Seerr's scheduled job fulfilled both requests.
Stackarr's verified Plex handoffs played the movie and S1E1 with advancing video,
correct 1080p/720p dimensions, no video errors and matching native Plex sessions.
Browser Back returned to Stackarr. The existing claimed disposable server was
reused; new account association and signed-out credential entry were not repeated.

Discovery checks successful import history every 15 seconds, combines batches and
limits root scans to once per matching section per minute. Durable checkpoints
survive restart and advance only after scan acceptance. Changed servers, addresses,
credentials or roots block writes until reviewed; unrelated library folders are
excluded. Existing native notifications/custom schedules stay intact. Fresh
watching setup includes this connection. Stackarr must remain running; the browser
window can close. Availability still requires actual Plex matching. Full matching
section scans trade extra work for reliability; large-library scale remains a test.

Unconfigured startup/review does not alter update fingerprints. Configured scan
bindings are protected during updates while routine progress may advance. Full
regression runs exposed transient native Windows access/sharing locks in journal
replacement; a bounded 0.75-second retry fixes those without bypassing persistent
write failures or altering the previous journal on failure.

Final checks: **940 Python passed, 3 skipped; 75 Node passed; 29 frozen checks
passed**; changed files pass Ruff. The exact final image passes its network-disabled
API/assets/quality/Plex-link smoke. Package verification confirms eight payload
hashes, nine ZIP entries, 35 embedded image blob hashes and the matched executable.
ZIP: **342,555,645 bytes**; SHA-256
`fb0335fba892bb668c91a498a420e790339c2ba94a7804051433a32a6e63b31b`.

Restarting the final image retained availability/checkpoints without replayed
scans. Private evidence is in `test-results/automatic-import-20261020/` and the
walkthrough is [AUTOMATIC-IMPORT-TEST.md](AUTOMATIC-IMPORT-TEST.md). The older
nine-app alpha's exact replacement rehearsal remains pending; this test does not
approve main cutover, clean Windows, second-device playback or signed-out startup.

All **nine** retest containers and their two unused networks were removed.
Configuration/recovery volumes and generated samples are retained. No native test
controller remains running. Final main container/configuration/credential/media
preservation checks pass; the earlier deleted libraries remain deleted and their
old server was never restarted. Only the original ten main Stackarr containers
and unrelated `open-easyx` remain.

## Previous real-account first-watch test and replacement rehearsal

Latest separate engineering package: **Stackarr-One-App-Preview-20261020-r6.zip**,
dashboard **stackarr:accounts-source-20261020-r4**, matching
`accounts-source-runtime-r4/StackarrPreview.exe`. **It is not ready for the main
installation's cutover: automatic Plex discovery fails.**

The real extracted-package walkthrough found and fixed a Windows PowerShell
quoting failure in separate-project allocation and Seerr's actual fresh-state
enum (`NOT_CONFIGURED=4`, rather than the fixture's assumed zero). The user
created the test Stackarr password and associated the new Plex server with the
existing real browser account. Stackarr then privately signed that same owner
into Seerr, created/enabled matching Movies and TV libraries, and configured
native download/source/import connections. No second Seerr browser sign-in or
copied account key was required. Plex's container-folder dialog was skipped.
Instructions now explicitly say **Next without Add Library → Done → return to
Stackarr**. A persistent **Check Plex libraries** control can prepare missing
libraries from the selected Windows folder after reopening setup. New library
preparation also starts a resumable initial root scan; existing libraries are not
repeatedly scanned by that step. **This initial scan did not fix post-import discovery.**

Real UI requests selected **1080p** for one movie and **720p** for TV season one.
Native Seerr and Arr profile assignments agree. qBittorrent downloaded seven
original generated animation/tone files, using catalog titles only as metadata
stand-ins. All **13,241,396 bytes** match the generated sources; all imports are
hardlinked to their downloads. Actual dimensions are 1920×1080 and 1280×720.
The local Torznab source is real Prowlarr configuration, not a personal provider
account or a mock of Plex/Seerr/Arr/qBittorrent. Test-only size allowances permit
these small generated files; public peer discovery is disabled.

**Failed automatic gate:** native Arr debug logs and Plex's own logs prove that
partial refreshes reached the correct server, section and imported path and
returned HTTP 200. Both Plex libraries nevertheless remained empty. Initializing
fresh empty libraries and repeating real requests did not correct this. A
separate, explicitly recorded full scan found the files immediately. Seerr's
scheduled checks then fulfilled the movie and requested TV season; Stackarr
offered verified Plex links. Actual browser movie and episode playback passed,
including advancing video time, 1080p/720p decoded dimensions, live Plex playing
sessions and browser Back returning to Stackarr. **Those playback results require
the recorded full scan and do not certify the automatic first-watch journey.**

The separate preview also passed an actual **update → rollback → update** through
the UI, preserving the six app container identities, native settings, credential
inventory, media and browser session. A further update delivered the library
controls. This is a preview-to-preview rehearsal, not certification of the owner's
older nine-app alpha or adoption of external apps. The next replacement matrix is
in [STACK-REPLACEMENT-TEST.md](STACK-REPLACEMENT-TEST.md): fix automatic discovery
first, then rehearse the older alpha's forward/rollback path while retaining apps,
Plex identity, accounts, watched state, sources, profiles, requests and schedules.

Regression checks: **926 Python passed, 3 skipped; 75 Node passed; 29 frozen checks
passed**. A Windows test-client split-write race on rejected readiness requests was
corrected while retaining strict 403/no-probe assertions. The exact final image
passes the network-disabled API/assets/quality/Plex-link smoke. Eight payload
hashes, nine ZIP entries, 35 embedded image blob hashes and the matched executable
verify. ZIP: **342,529,961 bytes**; SHA-256
`2fa3768b7fbe11567dd3f1cc2d8caab4d370e738ffbb372d4fd0d0f396d786d8`.

All **nine** containers from this run and their two unused networks were removed;
its native preview controller was stopped. Configuration/recovery volumes and
generated samples are retained. Main container/configuration/credential/media
preservation checks pass; the earlier deleted libraries were never recreated or
their old server started. Only the original ten main Stackarr containers and
unrelated `open-easyx` remain. Private evidence, failed-run diagnostics, explicitly
recorded manual scans, browser playback measurements and cleanup receipts are in
`test-results/one-app-real-20261020/`.

## Previous one-app Plex, sources and request-quality preview

The earlier separate package was **Stackarr-One-App-Preview-20261020-r3.zip**,
using **stackarr:accounts-source-20261020-r2** and its matched
`accounts-source-runtime-r2/StackarrPreview.exe`. Extract into a new folder and
open **Start Stackarr.cmd**. The main installation was not upgraded or configured.
This checkpoint supersedes the older package recommendations below.

The recommended setup now leads with Plex sign-in. After signing in and finishing
Plex's server setup, return to Stackarr and choose **Check Plex sign-in & continue**.
Stackarr presents a concrete review to prepare Movies/TV libraries and requests.
For the exact apps owned by this installation, it reads the saved credentials
privately, prepares matching libraries, signs the same owner into Seerr and
completes matching core-app connections. It does not claim a server automatically.
Repeated setup preserves matching libraries/settings; changed accounts, servers,
endpoints or configuration require a fresh check. Manual connections remain
available for existing apps. The earlier test libraries were not recreated.

Source setup offers **Test & connect source**, followed by sharing confirmation
and a Home shortcut. The separate review remains available under Advanced.
Private input changes invalidate an in-flight review. Setup shows one current
task, remembers saved quality/storage and returns unfinished new installations
to Setup after login/reload. Plex-only Home provides a direct Plex action.

Home requests now offer the actual connected quality profiles for each new title.
Selections are bound to that title and the current upstream settings, verified
again before submitting, and checked in the saved request response. Existing
shows retain their quality for additional seasons. Requests show the saved
requested quality and distinguish imported files waiting for Plex from finding
a release. Available titles retain the verified token-free Plex handoff.

Validation: **924 Python tests passed, 3 skipped; 73 Node tests passed; 29 frozen
executable checks passed**. The exact final image passes a network-disabled
authenticated API/assets/quality/Plex-link smoke. Package verification covers
eight payload hashes, nine ZIP entries, 35 embedded image blob hashes and the
matched executable. ZIP: **342,525,203 bytes**, SHA-256
`5da946af802b0f1f3125b3f7be036b2a50ac83535c49dc930c392aacb72faa54`.

Native Seerr/Arr tests confirm a movie's Ultra-HD and a show's HD-720p request
profiles without changing defaults. Retained generated samples are correctly
shown as imported and waiting for Plex. Native Seerr's library sync, enabled
libraries, initialization and repeated setup pass against a synthetic existing
owner/Plex protocol fixture; that component test does not certify real Plex
authentication or playback. Browser account/source interactions also use an
explicitly labelled design fixture. **Real-account automatic availability and
player decoding of the final packaged journey remain unverified**, alongside
clean Windows, second-device and signed-out restart acceptance. No account claim
was made to bypass that limitation.

All test Docker containers and their unused test networks were removed after
checks, including the final self-removing smoke container. The latest temporary
protocol-test volume was removed; retained earlier media/configuration volumes
were preserved. Only the ten original main Stackarr containers and the unrelated
`open-easyx` service remain. Main container identities, configuration, credential
fingerprints and media preservation checks pass. Design-preview processes were
also stopped. Private receipts are in `test-results/accounts-source-20261020/`
and `test-results/one-app-20261020/`.

## Historical checkpoints

The following records describe earlier packages and their state at the time.

## Native home-flow acceptance and Docker cleanup

The latest separate preview is **Stackarr-Home-Preview-20261020-r3.zip**, using
**stackarr:home-20261020-r2** and the matched `home-runtime-r2` executable.
It contains two fixes found while using real services: a cached search no longer
disables request/library polling after navigation, and a new search clears the
previous query's cards while awaiting its response. Loading and search failure
are distinct from an empty result. Home/refresh regression checks pass **14 tests**;
the exact Docker image passes its network-disabled smoke and the EXE passes
**28 frozen checks**. All eight payload hashes, nine ZIP entries and 35 embedded
image blobs are verified. ZIP SHA-256:
`34a7cda1d264eb4292272ab3d7486b95d37c4871c52750c79ec2b98e820612cc`
(342,438,351 bytes).

The native acceptance lab is separate from both the main installation and the
earlier test servers: project `stackarr-apps-7`, ports 43700–43705, home on 29340.
Two requests were submitted through the actual home-screen UI and real Seerr:
movie TMDB 10331 and TV TMDB 2316, season one only. Native Radarr/Sonarr searched
the private original-sample source, qBittorrent downloaded, and the Arr apps
automatically imported one movie and six episodes. All **34,380,189 bytes** match
the retained original samples; all seven files are hardlinked to their downloads.
These are generated animation/tone samples with catalog metadata stand-ins, not
copies of the named works. No mocked Seerr/Arr/downloader or Plex-protocol service
was used. Updated request timestamps advance after search-to-Requests navigation
with the polling fix; the UI correctly retains requested status until Seerr
actually confirms availability.

**Incomplete account gate:** new Plex server **Stackarr home end-to-end disposable**
remains unclaimed. A choice to associate this new server with the signed-in account
was requested and has not arrived. Its two new libraries remain empty; the real
Plex refresh/Seerr Available check and actual player decoding have therefore not
passed. No manual scan, account claim, authentication exception or simulated
availability was used to turn this into a success. Resume this retained, reviewed
lab only after the account choice; do not recreate the earlier deleted libraries.

Docker cleanup now removes obsolete containers rather than leaving stopped groups
in Docker Desktop. The 26 previous test containers and five unused test networks
were removed after ownership/mount checks. An offline copy of the stopped original
Plex database confirmed zero library sections before its container was removed.
Configuration volumes, samples and media are retained. The current eight native
test containers are stopped/removed after the partial acceptance run, their unused
network is removed, and the dedicated home acceptance process stops. Main resource
identities, saved settings/credentials and media remain protected by the existing
preservation checks; unrelated services are untouched.

Private evidence and cleanup/package receipts are in the ignored
`test-results/home-e2e-20261020/`. `tools/home_e2e_check.py` includes a scoped resume
operation for the same approved volumes and Plex identity; that resume path still
needs execution when the owner supplies the pending account choice. The earlier
design demo on 29330 remains explicitly simulated and is not native-playback proof.

## Title home preview

The earlier design-preview bundle is **Stackarr-Home-Preview-20261020-r2.zip**, using
dashboard image **stackarr:home-20261020-r1** and its matched Windows executable.
The second package revision corrects the portable walkthrough; the executable and
dashboard are unchanged. Extract into a new folder and open **Start Stackarr.cmd**.
No running installation is upgraded. The earlier import-refresh package remains
available below as historical evidence.
Final ZIP: **342,437,084 bytes**; SHA-256
`6828fadeb5ba0f7c4ddeb3fc7b8dfc33a97c6bf5c1ac2eff2aff02011897e03b`.

**Home**, **Your requests** and **Your library** now provide poster rows, movie/TV
filters, paged search, title descriptions and explicit movie/season requests.
**Manage server** opens the existing operations/setup screens. Requests use the
connected Seerr owner and native default quality/approval settings; this is an
owner workspace, not a new household permission system. Seasons already available
or requested cannot be selected again. Specials, 4K requests, future-season
automation and request repair remain available in Seerr's advanced controls.

Status distinguishes requested, approval, downloading, queued/paused, import,
partial availability and attention states when Seerr supplies those observations.
Unknown source/release waits are described as requested, without inventing progress
or an ETA. Recent library rows are limited to twelve titles; Plex owns the full
library. The page polls every thirty seconds while visible and idle, preserving
search/filter/focus/scroll context and pausing for title dialogs. Snapshot times
remain separate for requests and library; failures keep stale snapshots labelled.

Title details offer **Open in Plex** only after a live server-machine and metadata
key/type check, also checking TMDB identity when Plex provides it. Links are built
from the configured browser address, carry no token, and open in the same tab to
avoid embedded-browser popup failures. Plex still owns playback and may require
sign-in. Library presence does not certify device compatibility.

The owner-authenticated API keeps Seerr/Plex credentials server-side. It bounds
upstream time/bytes/concurrency, rejects redirects, normalizes public title fields,
limits the artwork proxy to known TMDB sizes/filenames and validated raster bytes,
and bounds its in-memory artwork cache. Requests require CSRF and an explicit
submit, recheck title/seasons before creation, and rely on native Seerr duplicate
protection. An uncertain POST is not automatically retried. Saved native failures
stay visible as requests needing attention.

Native Seerr 3.5.0-stackarr.2 checks pass for discover/search (including multi-word
titles), movie/TV details, request/library lists and artwork. Native checks exposed
and resolved Seerr's reserved-plus query validation and `image/jpg` response type.
They used a scrubbed disposable copy with its own volume; no real Plex token was
used. All test containers are stopped, including failed startup attempts, with
volumes/media retained. The eight older disposable containers were also stopped
after receipt verification and confirming the earlier Plex libraries remained
deleted. The main installation and unrelated containers are preserved.

The separate loopback **design demonstration** uses public title/art captures with
explicitly simulated progress, local fixture requests and a fake Plex handoff page.
No demo data or credentials are in the downloadable bundle. Browser checks cover
movie/selected-season submission, immediate saved status, duplicate suppression,
partial libraries, title-specific same-tab handoff/Back, keyboard focus and a
390-pixel phone layout without horizontal page overflow. This does not certify a
real claimed-server import-to-availability/playback flow; that earlier gate remains
pending. Native browser zoom, physical phone playback and full assistive-technology
testing remain future acceptance checks.

Verification: full Python suite **889 passed, 3 skipped** before final browser
refinements; final focused API/adapter/authentication checks **44 passed**; frontend
home/refresh checks **12 passed**. The exact final Docker image passes a
network-disabled fixture smoke; the frozen EXE passes **28 checks** from an empty
directory. Package hashes, embedded image blobs and final preservation/cleanup
receipts are recorded under the ignored `test-results/home-screen-20261020/`.

Disposable-test convention: stop receipt-verified test containers in cleanup,
including failed attempts. Retain data unless deletion is explicitly requested;
never stop an installation merely because its name begins with `stackarr`.

## Automatic import refresh preview

The latest separate bundle is **Stackarr-Import-Refresh-Preview-20261020-r1.zip**.
Extract into a new folder and open **Start Stackarr.cmd**. This does not upgrade
the running main installation. It retains Seerr 3.5.0-stackarr.2 from the previous
sign-in/empty-library preview.

Connection review now offers native Sonarr/Radarr **Plex Media Server** import and
upgrade notifications after verifying the claimed server, authenticated library
access and matching import/library paths. It tests before creation, verifies saved
nonsecret fields, then tests the saved record ID so the Arr app resolves its own
masked token. Existing Plex notifications are preserved. No deletion notifications,
trash-emptying preference, library creation or anonymous-access fallback is added.

For Seerr connected to that same server with matching enabled libraries, review
can change its default five-minute recently-added job to every minute. It uses
Seerr's native schedule API, verifies readback and preserves custom schedules.
Unrelated, unselected Plex libraries do not block the selected import folders.
Server/library selection, import roots, credentials and configuration revision are
checked again before changes. Both mechanisms run in the apps, independently of
Stackarr's UI or controller. Availability still depends on Plex matching and a
successful Seerr scan; it does not certify device playback.

The saved checklist now requires these Plex refresh/availability reviews when
Plex and Arr apps are selected. Earlier six-link evidence alone cannot satisfy
the expanded connection checkpoint. Public reviews and saved readiness evidence
exclude credentials and raw API payloads.

**Verification boundary:** the owner chose to keep the new separate server
**Stackarr automatic import refresh** unclaimed. Other containers receive HTTP 401
from it. No claim, network-access exception or authentication bypass was applied.
Real Plex import scanning and real-account Seerr availability remain unverified.

Other acceptance checks pass against a clearly labeled Plex protocol simulator
that never proxies or contacts the real Plex server. Real Seerr requests drive
native private BitTorrent downloads and automatic imports of one generated original
movie and six episodes. All **34,380,189 imported bytes** match and all seven files
are hardlinked to their downloads. The movie uses its cumulative transfer counter;
episode counters are from fresh torrent sessions. A single fresh transfer session
for every retained attempt is not claimed.

Native Arr apps then send four observed library refresh callbacks to the simulator.
Seerr's scheduled scan, without a manual job run, completes both requests: movie
media status **5**, requested season status **5**, whole-series status **4** (partial),
with the simulator's Plex rating keys. This proves the native notification and
scheduled-scanner contracts, not real Plex discovery, matching or playback. Initial
fixture attempts are retained separately: its first version string lacked the
build suffix required by the Arr client, and repeated TV hashes reused completed
download history. Corrected fixtures use identical media and distinct TV torrent
identities; no direct Arr add/grab or manual import is used.

Validation: **56 targeted Python tests**, **60 Node tests**, **28 frozen executable
checks**, four network-disabled image checks and the native-app protocol flow pass.
The full Python run passed 850 cases with three skips and one Windows loopback
connection abort in an unchanged first-run test; all 24 first-run server tests pass
on rerun. Later claimed-server/selected-library changes pass the targeted suite.
Ruff, JavaScript syntax and whitespace checks pass. Exact packaged fresh-Windows
and claimed-server request-to-watch acceptance remain open.

All nine containers created for this phase are stopped; every volume, generated
file, retained attempt and report remains. The earlier test libraries stay deleted.
Main preservation checks pass with the existing documented background Seerr
`lastScan` exclusion. No main installation upgrade or settings change was applied.

The final ZIP is **342,350,843 bytes**, SHA256
`b8be62b538280a13ebca800e2ff6a8a19099191fb5652beb822590044746e639`.
All eight payload hashes, nine ZIP entries and 35 OCI blobs verify. Dashboard image:
`stackarr:import-refresh-20261020-r1`. Private evidence is in
`test-results/import-refresh-20261020/flow-report.json`, `package-report.json`,
`cleanup-report.json`, `.runtime/import-refresh-targeted.xml`,
`.runtime/import-refresh-suite.xml`, `.runtime/import-refresh-first-run-rerun.xml`
and `.runtime/import-refresh-frozen-r1/report.json`.

## Plex sign-in and empty-library setup preview

The latest separate bundle is **Stackarr-Plex-Setup-Preview-20261020.zip**.
Extract it into a new folder and open **Start Stackarr.cmd**. It includes
**Seerr 3.5.0-stackarr.2**, retaining the Manage Users protection and adding
reviewed, hash-locked setup fixes. The running main installation is not upgraded.

Plex sign-in now uses the same tab, including in the embedded browser, and
returns automatically to Seerr. Only a bounded PIN receipt is stored in that
tab; account tokens stay out of browser storage and return URLs. Interrupted
setup returns signed-out users to sign-in, and failed PIN creation shows a retry
message. Plex still owns account authorization and Seerr validates the account.

An authenticated Plex response with zero libraries now becomes an empty list,
instead of Seerr's missing-list HTTP 502. Malformed lists and authentication
failures still fail. After a successful empty sync, setup explains the missing
libraries and offers **Continue without libraries**. This explicit choice permits
setup completion without claiming availability or creating any libraries.

**Real account/browser acceptance passes:** same-tab Plex authorization, automatic
return to Seerr, connection to the exact claimed test server, empty-library
guidance, explicit continuation, Finish Setup and arrival at Discover. Stackarr's
normal private credential handoff also passes. Authenticated Seerr sync now returns
**HTTP 200 with `[]`**. The two test libraries remain deleted and all 15 retained
media files match. Main container identities, settings/credentials and media pass
the existing preservation check, with the earlier documented Seerr `lastScan`
timestamp exclusion. No requests, downloads, scans or library creation are part
of this follow-up. The completed test Seerr is on localhost:43409; the superseded
candidate is stopped with its volume retained.

Validation: **60 Node checks**, eight cases against the actual patched library
method, **27 frozen executable checks**, four network-disabled dashboard image
checks and the real embedded-browser flow pass. The Python suite initially passed
831 cases with three skips and five stale image-label fixture failures; the
fixtures now include the required setup label and all 26 affected catalog/deployment
checks pass on rerun, including missing/changed setup labels. Source syntax,
Ruff and whitespace checks pass. Exact packaged fresh-Windows onboarding and
request-to-availability automation remain separate gates.

All eight package payload hashes, nine ZIP entries and 35 OCI blob hashes verify.
The tested Seerr digest is
`stackarr-seerr@sha256:3d0ddfab2de853a31d289316297bf6760e59d5fda4cd3046fd93b6c5dd8da531`;
the matching dashboard is `stackarr:plex-setup-20261020`. ZIP size is 342,320,176
bytes and SHA256 is
`1acf5926aade0972d7798c974e72b8fb68736b4533519418b15196d1f2f5012e`.
Evidence: `test-results/source-flow-20261020/plex-setup-fix/report.json`,
`package-report.json`, `real-empty-library-setup.png`, `real-setup-complete.png`,
`.runtime/plex-setup-frozen/report.json` and the two `plex-setup-fix-*.xml` reports.

## Source setup and first-watch preview

The new separate private bundle is **Stackarr-Source-Flow-Preview-20261020-r1.zip**.
Extract it into a new folder and open **Start Stackarr.cmd**. It preserves the
portable `alpha-data` layout and unsigned status; the existing alpha is not
upgraded. The included walkthrough now starts with **Find movies & follow TV**
and follows the saved setup checklist.

**Where will your media come from?** distinguishes existing files from finding
new copies. It loads provider-specific forms from the connected Prowlarr version,
keeps private fields blank, and uses a session-owned five-minute review before
testing and saving one source. Existing sources are preserved. The live pinned
Prowlarr advertises 657 forms; 568 fit the guided subset. Custom Torznab feeds and
complex forms use explicit Advanced setup. Guided sources use qBittorrent;
Usenet requires a separately configured compatible downloader.

Source sharing remains separate from provider authentication, movie/TV categories
and search results. Each explicit diagnostic tests up to three enabled sources
with a bounded deadline and never grabs media. A successful empty response needs
a new matching successful Prowlarr history event; failed, skipped or unverifiable
queries cannot become “no matching copy.” One unavailable Arr app preserves
other source evidence. Only counts, source IDs and configuration bindings are
retained in the checklist; provider credentials, queries and release URLs are
excluded. Movie and TV checks advance independently and expire rather than
certifying future availability. Playback and imports remain explicitly unverified
in the product checklist.

Delayed responses cannot overwrite source/app edits or display a search result
under a changed title/category. Source sharing explains Prowlarr's asynchronous
propagation and offers an explicit recheck before connection review. Desktop and
390-pixel layouts pass, with the advanced form collapsed and touch-sized summary
controls.

Validation: **836 Python tests passed, 3 skipped; 51 Node tests passed**. The
seven startup-journey scenarios now include provider selection and independent
movie/TV probes. Standard and Docker-mode browser smoke, quality, refresh and
source UI/race checks pass. Ruff, JavaScript syntax, whitespace and portable-source
audit checks pass. The standalone executable passes **27 frozen checks** from a
source-free directory; the built dashboard passes four authenticated checks in a
disposable network-disabled container with synthetic upstream responses. These
package smoke checks do not certify real provider accounts or cloud sign-in.

Private regression evidence: `.runtime/source-phase-final-suite.xml`,
`test-results/setup-source-journey-20261020a/report.json`,
`test-results/source-setup-race-20261020/report.json`,
`test-results/source-phase-quality-20261020/report.json`,
`test-results/source-phase-refresh-20261020/report.json`,
`.runtime/source-phase-frozen/report.json`,
`.runtime/source-phase-image-report.json`.

All eight package payload hashes and nine ZIP entries verify, including equality
with the fresh executable. Image records, OCI blob hashes and 23 image layers
verify; no runtime state or media is bundled. Seerr's intentional empty
`app/config/DOCKER` marker is recorded separately. The image tag is
`stackarr:source-flow-20261020`. Package proof is
`.runtime/source-phase-package-r1-report.json`; the 332,501,462-byte ZIP has SHA256
`7d47d9ce02c8c81282e3057fd8e1b2bcd260be92d06f58e19a825309973bd3af`.
The r1 walkthrough documents the observed manual Plex scan requirement; its
executable and full image archive are byte-for-byte equal to the tested base.

The controlled live test uses the current native Stackarr UI/API with six real
pinned Docker apps, a separate private source/seeder and generated original media.
It exercises the advanced local-feed path; the 568 guided provider forms were
projected from the live schema, not individually tested against external accounts.
Real Seerr browser login and movie/season request buttons pass without API-key
browser authentication. The movie and six episodes download and import
automatically: **34,380,189 bytes**, every SHA256 matches the generated original,
each new torrent has import history, and each library file is a hardlink to its
retained download. No direct Arr add/grab or manual import is used.

The initial 25-second originals were correctly blocked as samples. Their rejection
evidence is retained; replacement originals have normal movie/episode durations.
Only the disposable lab's WEBDL-720p minimum-size floor is relaxed for the small
generated files. Sample detection remains enabled. Old fixture requests/download
records were reset explicitly before new browser requests; these steps are test
scaffolding, not a consumer setup requirement.

**Remaining seamless-flow gap:** both Plex libraries remained empty throughout a
60-second observation after successful imports. The local fixture needs an
explicit library refresh before playback testing. Automatic Plex discovery and
Seerr availability propagation must be verified and improved before advertising
an uninterrupted request-to-watch experience. The lab uses unclaimed local Plex
and a seeded local Seerr owner, so cloud sign-in, claim/library-selection onboarding
and the exact packaged full journey remain separate acceptance gates.

The local Plex defaults had automatic, partial and scheduled library updates off.
Those preferences were observed, not changed. Seerr still reported Approved /
Processing after import; its library-sync endpoint returned an authentication
error without a real Plex owner token. Request completion is therefore unverified
in this fixture. No main token or cloud identity was copied to bypass the check.

After the explicit scan, **actual Plex Web playback passes for both imported
originals** using the native Play button. The movie advances 0–3.727 seconds and
4–94 decoded frames; the episode advances 0.081–4.092 seconds and 7–103 frames.
Both decode audio, remain unmuted and report no media errors. Screenshots show the
generated animation in the full and mini players. This verifies local browser
decoding, not physical speaker output, subtitles, a TV/phone or home-network access.
Proof: `test-results/source-flow-20261020/playback-web-report.json` and the two
`playback-*-playing.png` images. The frozen/package smoke and real native-UI lab
evidence are separate; an exact packaged fresh-account walkthrough remains open.

Live evidence: `test-results/source-flow-20261020/source-browser-report.json`,
`requests-browser-report.json`, `imports-report.json`,
`short-sample-rejection.json` and `automatic-plex-visibility.json` in that directory.
The aggregate `flow-report.json` records local playback success and explicitly
leaves seamless automation and Seerr completion false. The main installation is
not upgraded. Its ten container identities/mounts, dashboard/controller settings
and credentials, six other app configuration files and existing media hashes
match the baseline. Main Seerr's raw settings file changed during background
library scanning before a refined semantic checkpoint; original raw-file equality
is not claimed retroactively. Subsequent protected Seerr settings match that
checkpoint, excluding library `lastScan` timestamps.
The exact six lab apps, two source/seeder fixtures and native test server were
stopped after the local test. All test state, Docker volumes, media and reports are retained; nothing
was pruned or deleted. The ten original containers remain running and the main
dashboard health check passes. See `cleanup-report.json` and `flow-report.json`.

The owner subsequently chose real Plex sign-in. The same six receipt-verified lab
app containers were restarted with their retained Plex identity and libraries;
the source/seeder fixtures remain stopped. The visible Plex Web sign-in page is
prepared for owner authorization. This restart checkpoint predates the claim and
authentication results below. See `real-account-restart-report.json`.

On return, Plex Web was signed in to the real account, but the exact retained test
server still reported unclaimed and had no saved server credential. Its General
settings explicitly displayed **Claim Server**. This reproduces the onboarding
distinction between account sign-in and claiming the selected new server.
The owner requested deletion of the two test libraries and chose to keep them
deleted, limiting this follow-up to authentication. **Original flow movies** and
**Original flow TV** were removed only from the verified test server; all generated
media hashes and main preservation checks still pass. No libraries will be
recreated without a new request. See `real-account-library-removal-report.json`
and `real-account-authentication-report.json` in the source-flow evidence folder.

The owner then explicitly authorized **Claim Server** on that exact test server.
Claim succeeded, and Stackarr collected the test server's own credential through
its normal private handoff. Authenticated Plex access now passes and returns zero
libraries. No main account token was copied. See `real-account-plex-claim-report.json`.

Real Plex authentication also passes in a separate receipt-owned clean Seerr on
port 43408 using its supported `/api/v1/auth/plex` endpoint: cloud identity login,
owner session, connection to the exact claimed test server and logout all pass.
The earlier seeded local-owner Seerr is preserved. The embedded-browser Plex
popup did not open, so browser OAuth onboarding remains unverified.

**New empty-library blocker:** authenticated Plex returns HTTP 200 with zero
libraries and omits `MediaContainer.Directory`. Pinned Seerr returns HTTP 502 on
library sync; its implementation filters that missing list without a fallback,
and its log records `Cannot read properties of undefined (reading 'filter')`.
This is separate from successful account authentication. No upstream patch was
applied. The owner requested authentication only, so availability was not tested
and the libraries remain deleted. All 15 retained lab media files and main
preservation checks pass. The six original lab apps and the separate clean Seerr
remain running; source/seeder fixtures and the native test server remain stopped.
See `real-account-seerr-authentication-report.json` for the sanitized results.

## Earlier setup usability preview

The separate private bundle is **Stackarr-Setup-UX-Preview-20261020.zip**. It builds
on Alpha 0.1 and implements the first setup slice of the
[v0.2 usability plan](UX-0.2-PLAN.md). Extract it into a new folder and open
**Start Stackarr.cmd**. Choose **Find movies & follow TV** for the six-app request
preset, or choose a smaller/custom setup. The existing alpha is not upgraded.
The package retains Alpha 0.1's portable `alpha-data` storage and unsigned status.
Its generic alpha README still describes the optional all-nine-app walkthrough.

The setup checklist reconstructs selected-only tasks from the saved draft,
installation receipts, authenticated API observations and redacted source/wiring
checks. It recommends one action, directs missing hosts to explicit reconnect
instructions, and advances completed connection reviews to functional verification.
Preserved existing settings count as reviewed configuration; they do not certify
the connection's correctness. Playback, imports and source search remain separate
unverified checks. Plex-only and Seerr-only guidance exclude unselected apps.

Folder selection shows a friendly name with the exact path available in collapsed
details. Movie/TV request-quality choices and saved paths are preserved. No free-space
figure is shown without host evidence. Background refresh honors its interval,
preserves focus, selection, details, filters and scroll, and leaves dirty forms and
newly entered secrets mounted. Checklist controls cannot invoke disabled actions.

Validation: **784 Python tests passed, 3 skipped; 31 Node tests passed**. The seven
new isolated browser scenarios cover request presets, saved quality/resume,
minimal/monitoring/mixed setups, source and connection review progression,
verification navigation, unselected apps and reconnect guidance. Existing launcher
and Docker-mode browser smoke checks, eight quality scenarios and desktop/mobile
refresh checks pass. Ruff, JavaScript syntax, whitespace and portable-source audit
checks pass. Existing mount-normalization fixtures now use synthetic media paths.

The frozen executable passes **26 checks**, including authenticated journey routes
and bundled assets without Docker calls. The new dashboard image passes an
authenticated saved-journey check in a disposable, network-disabled container with
no media mounts or published ports. All eight package payload hashes and nine ZIP
entries verify. The image tag is `stackarr:ux02-setup-20261020`.

Private evidence: `.runtime/ux02-suite-final.xml`,
`.runtime/ux02-journey-final/report.json`, `.runtime/ux02-quality-browser/report.json`,
`outputs/refresh-dirty-form-regression-check/report.json`,
`.runtime/ux02-frozen-isolated/report.json`, `.runtime/ux02-image-report.json` and
`.runtime/ux02-package-report.json`. Browser boundaries are synthetic; these checks
do not certify actual app installation, acquisition/import/playback through the new
UI, clean Windows, home-device access or signed-out startup. No existing app,
account, media or host startup/network setting was changed. Full packaged workflow
acceptance and the next guided-source work remain open.

## Integrated first run — packaged Docker acceptance complete

The newest private bundle is **Stackarr-Docker-First-Run-Preview-20261019-r1.zip**.
Its main executable now includes readiness and reviewed Docker prerequisite setup.
**Start Stackarr.cmd → Continue to Stackarr** checks current readiness and opens
password creation and app setup in the same browser tab. Existing-app mode opens
the separate local launcher without Docker. Saved Docker installations retain
managed-release startup and local repair/reinstall review instead of being reset.

**687 Python tests pass, 3 skip; 9 browser scenarios and 23 frozen checks pass.**
Eight payload hashes and all nine ZIP entries verify. Ruff and PowerShell/JavaScript
syntax checks pass. The actual extracted package starts with fresh lab state,
performs real Windows/Docker checks, installs a separate Seerr after review, and
verifies its patched persistent storage and initial setup. A second frozen launch
retains the account, browser session, container IDs, settings and credentials.
Desktop/narrow readiness layouts pass. A harness-only URL predicate error on the
first attempt was corrected before repeating the entire journey in fresh state.

All nine existing apps authenticate in fresh checks. Their original IDs, settings,
credentials and all 16 media/data hashes are unchanged. Only isolated lab containers
and networks are removed; all volumes, lab state, keys and media remain. The main
Stackarr/app installation is not upgraded. No Docker installer or reboot runs on
this working computer. Missing-Docker, vendor calls and restart behavior are fixture
checks; actual clean-Windows installation and native recipient walkthroughs remain
separate gates.

Private proof: `test-results/docker-integrated-readiness-20261019-r1/`, including
`suite.xml`, `source-browser/browser-report.json`, package/frozen verification,
`packaged-browser.json`, `acceptance.json` and fresh authenticated monitoring.
See [integrated first run](INTEGRATED-FIRST-RUN.md) and the
[updated completion plan](COMPLETION-PLAN.md).

## Seerr Manage Users fix — packaged acceptance complete

The earlier security bundle is **Stackarr-Docker-Seerr-Permissions-Preview-20261019-r4.zip**.
It includes the immutable **Seerr 3.5.0-stackarr.1** security backport, its license
and reproducible patch receipt. All three permission-mutation routes share a
transactional policy, protect owner/self and higher-privilege accounts, limit
delegation to held capabilities and reject mixed batches before writes. Profile
mutations are guarded too. The delegated-admin gate is closed for this package.

The final native image passes **40 real HTTP checks** across **9 recorded cases**
including login, privacy and revocation regressions. The extracted package repeats
all 40 checks, loads the absent image from its archive, verifies fresh storage,
and passes real browser login/container replacement with its cookie and protection
retained. The normal packaged update from 3.5.0 succeeds with users, requests,
owner authorization and settings unchanged; all 40 checks pass afterward.
Only owner-approved synthetic identities are seeded into the fresh package lab.
No real authorization is transferred and no real sharing/invitation is changed.

**589 Python tests pass, 3 skip; 9 Node policy tests and 22 frozen checks pass.**
All eight ZIP payload hashes pass. The empty-cache test caught and corrected a
Docker export issue: save the verified repository tag so digest addressing is
restored on load. Changed upstream patch inputs fail before partial writes.

Fresh checks authenticate all nine existing apps. Main app/dashboard IDs,
settings, credentials, backup policy and all 16 media/data hashes are unchanged.
Only lab containers/networks are removed; volumes, state and keys remain.
The main Stackarr/app installation is not upgraded. Real second-account Plex
cloud and broader recipient acceptance remain separate gates.

Private proof: `test-results/docker-seerr-permissions-fix-20261019-r1/`, including
`native-final/matrix-result.json`, packaged install/browser/update results,
`acceptance.json`, `main-authenticated-monitoring.json`, `suite-r2.xml`, frozen
checks, package verification and source audit. See
[the backport record](SEERR-PERMISSIONS-FIX.md) and [completion plan](COMPLETION-PLAN.md).


## Earlier upstream permission audit

The isolated matrix is complete for the owner's chosen **test identities**:
**10 native real-app cases**, the retained r3 packaged invited-user browser journey
and **30 focused maintenance tests** pass execution checks. Four new contracts
cover unexpected guest elevation, removal, revival and identity changes in update
checkpoints. Ruff passes. This checkpoint changes maintainer tests and guidance;
the product image and **Seerr Setup r3 ZIP remain unchanged**.

The real pinned Seerr 3.5.0 handler admits shared identities with request-only
permissions, denies unshared users, respects import-only admission, limits request
and profile visibility and applies permission downgrades to open sessions. Plex
membership/token revocation is simulated on an internal Docker network, with
private TLS trusted only inside the new app container. Real HTTP requests preserve
Seerr cookies and headers; neither auth nor permission responses are mocked.
No real invitation, sharing, account credential or media is used in that fixture.

Revocation has two verified limits: an existing Seerr session survives simulated
Plex sharing/token revocation, and deleting only the Seerr account permits
readmission if sharing and new sign-ins still allow it. Setting permissions to
none also permits sign-in. Removing the Seerr test user denies its live cookie
and password; the packaged browser returns to sign-in. The real browser sequence
also preserves least privilege and its session across container replacement, and
keeps the pre-existing lab owner's authorization/settings digests and volume.

**The earlier unpatched upstream audit found:** Manage Users can change a
non-owner administrator through both single-user and batch permission APIs, even
though admin deletion is denied. Request-only users cannot reach these actions,
and the owner stays protected. Grant Manage Users only to trusted administrators
on unpatched installations. That historical report marks
`delegated_admin_release_gate_passed: false`; completed testing is not a passed
security gate. Real second-account Plex cloud certification is also separate.

Finalization freshly authenticates **all nine existing integrations** and preserves
main app/dashboard IDs, settings, credentials, backup policy and **16 media/data
files**. Both labs' containers/networks are removed with all volumes, state, keys
and original samples retained. No existing Plex test server is started for this
matrix. Private proof is under `test-results/docker-seerr-permissions-20261019-r1/`:
`acceptance.json`, `native-report.json`, `findings.json`, `isolation.json`,
`fixture-events.json`, `checkpoint-tests.xml`, `main-authenticated-monitoring.json`,
`source-audit.json` and `packaged/browser-report.json` with its revoked-access
screenshot. See [SEERR-PERMISSIONS.md](SEERR-PERMISSIONS.md) and the
[completion plan](COMPLETION-PLAN.md). The security follow-up below supersedes that open fix gate; real-cloud and broader recipient coverage remain separate.

## Seerr warning fix and Plex sign-in guidance

This earlier setup slice used
**Stackarr-Docker-Seerr-Setup-Preview-20261018-r3.zip**.
Dashboard image: `sha256:296b42b6512c18b6f396772abb0dae6c17f53508d04294e8febcdfef361d2f34`.
ZIP SHA-256: `c30cc96a5560325dc2c602cefc49a231daa8c1ec15e77f81b1cfbc2c638f7b64`.
Nine allowlisted entries and eight payload hashes verify. The frozen executable
passes **21 smoke checks outside the checkout**. Full Python regression reports
**579 passed, 3 skipped**; Ruff and JavaScript syntax checks pass. The final
portable-source audit reports **264 files, 0 findings**. The final r3 package
also corrects garbled punctuation found during screenshot review. The existing
main installation stays on Self-Removal r4.

Fresh Seerr setup now verifies its exact owned running container and exclusive
persistent settings volume, writes/fsyncs/reads a unique probe as Seerr's normal
user, removes only that probe and flushes its directory. After resource
reinspection, only an empty regular single-link image `DOCKER` marker can be
cleared. Its inherited presence caused the misleading upstream mount warning.
The official pinned image and named-volume layout remain unchanged. Unexpected
markers, denied writes and changed/shared storage stop with settings retained.
Existing installations are not adopted or changed by this new-install step.

The setup screen shows only the selected Plex/Seerr account steps. It names the
actual **Configure Plex → Login with Plex** buttons and explains choosing the
correct server. A collapsed missing-window guide offers Seerr's address for the
usual browser, popup permission and retry. Clipboard denial selects the address
for manual copying. Clipboard tests use browser fixtures; no personal clipboard
is touched. Empty/duplicate account panels are removed, and incomplete accounts
stay pending after **Finish connecting**.

Six real pinned Seerr storage/persistence cases pass, plus actual official Plex
authorization-window handoff and a browser fixture blocking popup creation.
Two packaged journeys (Seerr-only and Plex-plus-Seerr) pass in both r2 and final
r3: **12 recorded passing results across 10 distinct scenarios**. Final r3
checks cover the frozen controller, warning absence, scoped instructions,
copy/manual-copy fallback, readable punctuation and desktop/phone layouts.
The combined server is new, distinct and unclaimed, with read-only copied samples.
No real media is requested or downloaded.

The automatic popup tests alone do not certify a completed account callback.
On the morning of 19 October the owner chose **fresh Plex sign-in**, completed it
through the usual-browser fallback and returned to Seerr's media-server step.
The new Plex owner and permissions are verified. API-assisted setup selects only
the already claimed, separate maintenance Plex server and its existing sample
library. Private packaged handoff, repeat handoff, fresh authenticated monitoring
and disappearance of the completed account guide pass.

Replacing only the new Seerr container preserves its exclusive settings volume,
owner/new-authorization fingerprint, settings-file hash and selected library.
Authenticated APIs work and the warning stays cleared. The owner refreshed the
same browser and confirmed the sign-in session survives. This adds a thirteenth
passing result; no earlier sign-in authorization was reused. The earlier blocked
reuse proposal never executed. A novice recipient's server claim/library selection
and other browsers remain separate gates.

Finalization freshly authenticates **all nine existing integrations** and checks
unchanged original app/dashboard IDs, settings, credentials, nightly backup policy
and **16 tracked media/data files**. Three copied sample files also match. Only
this task's new lab containers/networks are removed. All settings volumes, state,
keys and media remain, and the main Stackarr package is not upgraded.
The fresh-account follow-up uses a new morning main-state/media baseline after
normal overnight activity, again freshly authenticates all nine integrations and
preserves the same 16 files. Its retained Seerr lab is stopped/removed, and the
separate maintenance Plex server returns to its original stopped state.

See [SEERR-SETUP.md](SEERR-SETUP.md) and the updated
[completion plan](COMPLETION-PLAN.md). Private proof is under
`test-results/docker-seerr-guidance-20261018-r1/`: `acceptance.json`, `cases.json`,
`package-verification.json`, `frozen-smoke.json`, `source-audit.json`,
`main-authenticated-monitoring.json` and the setup screenshots. Earlier r2 proof
is retained separately under `r2-proof/`. Python regression is
`test-results/seerr-guidance-suite-r2.xml`; final UI changes are covered by the
r3 packaged browser reruns and syntax checks.
Fresh-account follow-up evidence is under `fresh-plex-signin/`:
`account-acceptance.json`, `packaged-browser.json`, `final-preservation.json`,
`main-authenticated-monitoring.json` and `packaged-seerr-connected.png`.

Next Docker work is invited/shared-user permissions and revocation, followed by
wider account/major migrations. Broader browser/server-library selection, native
folder/recovery dialogs, novice walkthroughs, replacement Windows, signing, signed-out startup
and LAN/second-device certification remain explicit release gates.

# Current delivery checkpoint — 18 October 2026

## Final Docker app-start port recovery

The bundle tested for that checkpoint is
**Stackarr-Docker-Startup-Ports-Preview-20261018-r4.zip**.
Dashboard image: `sha256:fdb0437ffd70db2e453abd45a53c25528f5daf50397180ff3ad36d1d4f2f86f3`.
ZIP SHA-256: `f296447be325ee4552212a66a2472a60ef659c168c98dfb0af211f5ba6b79042`.
Its nine allowlisted entries/eight payload hashes verify; the frozen executable
passes **20 smoke checks outside the checkout**. Final regression reports
**572 passed, 3 skipped**. Ruff passes and the portable-source audit reports
**258 files, 0 findings**. The main installation remains on Self-Removal r4.

A real port conflict during final Compose startup now offers **Review available
ports → Apply new ports & resume**. Recovery keeps the same deployment/project,
configuration volumes, pinned images, media folder and generated-login checkpoints.
Only blocked unstarted apps change ports. Healthy running apps keep their
containers and addresses; existing services owning the old ports keep running.
qBittorrent's published port, matching target and web-port environment change
together. Trusted status repairs a lost approval response's unactivated connection
handoff so **Finish connecting** uses the recovered addresses privately.

The live test found Docker can report a previously failed-bind container running
without restoring its network/published port. Original-address resume now also
recreates unstarted containers from the exact saved recipe using their retained
volumes and checks real published bindings before credential handoff. An app
stopped externally after approval is preserved for inspection. A port taken
before missing-container recreation keeps this same recovery receipt instead
of falling back to fresh installation and abandoning retained configuration.

Approval is owner/CSRF/session protected, expires after five minutes and is
single-use. It durably records source/target recipes, verified resource identities
and generation labels before the worker atomically replaces the recipe file.
Fresh-process resume reconciles only that transition and accepts only verified
generation replacements. Changed/shared settings, missing retained resources,
unexpected containers, altered recipes or changed privileges stop recovery.
No foreign service is stopped, app volume removed, media moved or login reset.

**Six native scenarios** use real pinned Prowlarr/qBittorrent images and new
settings volumes with three copied original sample files. They pass new-address
recovery, original-address resume, a proposed port taken before approval, actual
worker exit after receipt/file commit and explicit fresh-process resume, a second
real startup conflict, and shared-volume refusal followed by recovery. Each
checks Prowlarr's unchanged ID/setting/generated login, retained config-volume
fingerprints and marker, authenticated downloader access, media bytes and one
installation/activation.

**Three packaged runs**, including the exact final r4 ZIP, pass the real browser
review/approval/connection journey through the frozen controller. A separate
maintainer-only CLI relay injects a real port-owner container immediately before
the new lab's Compose startup; Docker supplies the real bind failure. Only that
controller inherits its relay PATH; release artifacts contain no relay or fault
switch. Desktop/phone layouts and the final visible connected state pass.
Earlier packaged runs and their state/evidence are retained separately.

Final acceptance freshly authenticates **all nine main integrations** and confirms
unchanged existing app/dashboard IDs, settings, credentials, nightly backup policy
and **16 tracked media/data files**. The separate three-file sample copies match.
Only this task's new containers/networks are removed; all named volumes, state,
keys, generated settings and media remain. Existing Docker pools and the main
Stackarr package are unchanged. Capacity-limited labs run sequentially.

See [STARTUP-PORT-RECOVERY.md](STARTUP-PORT-RECOVERY.md) and the updated
[completion plan](COMPLETION-PLAN.md). Private evidence is under
`test-results/docker-startup-ports-20261018-r1/`: `acceptance.json`, `cases.json`,
`package-verification.json`, `frozen-smoke.json`, `source-audit.json`,
`main-authenticated-monitoring.json` and `packaged-*.png`. Final regression is
`test-results/startup-ports-suite-r4.xml`.

Next Docker work: remove the legacy Seerr config-mount warning and finish Plex
popup guidance, then invited/shared-user permissions and revocation and broader
account/major migrations. Whole-connection internet loss, changed-password
recovery, native/recipient walkthroughs, signing and signed-out/LAN certification
remain open.

## Docker network diagnostics and interrupted-download recovery

The bundle tested for that checkpoint is
**Stackarr-Docker-Network-Download-Preview-20261018-r2.zip**.
Dashboard image: `sha256:9c759d0a9a0b7175cc1fd0efeced39a8963173aba643f38b9551fcc79a4df30f`.
ZIP SHA-256: `d9f62b9f4d16fc41ac7f4a9d2f6e3f89c8aa908425deaf3a7da6830d02eaf52e`.
Nine allowlisted entries/eight payload hashes verify. The executable passes
**19 frozen smoke checks outside the checkout**. Full regression reports
**550 passed, 3 skipped**; Ruff passes and the portable-source audit reports
**252 files, 0 findings**. The main installation remains on
Self-Removal r4 and is excluded from all update/install targets.

**Check Docker** now estimates IPv4 network ranges using bounded, read-only pool
and subnet inventory. It explains low/exhausted capacity and uncertainty without
allocating probes, exposing raw inventory, pruning networks or changing Docker
configuration. Exhaustion blocks new app batches; an owned existing network can
still support resume. Actual Docker creation failures retain the specific diagnosis.

Image pulls now have durable progress, bounded download-only retries and fixed
messages for transient interruption, timeouts, registry access and full image
storage. Failed/interrupted downloads offer **Retry download**. Resume keeps the
same receipt, pinned images, paths and ports. Every image's complete identifier,
repository digest and Linux x64 platform is checked before app storage/startup;
startup uses `--pull never`. Completed cached images need no registry access.
Progress metadata is created lazily, preserving older idle controller fingerprints
during compatible Stackarr promotion. Interrupted workers wait for explicit resume.

The final six-case matrix passes in a new nested Docker daemon with a private
two-range pool, no host Docker socket and no existing media/configuration mounts.
It reproduces actual engine exhaustion, after-review/final-start capacity races,
offline cached-image resume, a connection cut after 262,144 original layer bytes,
registry access refusal and actual worker/download-CLI exit during a partial body.
Fresh-process resume keeps one installation and one activation. An unrelated
nested sentinel retains its ID and original settings. The final-start race retains
Compose's newly created empty settings volume instead of discarding it.

The packaged follow-up promotes an older Runtime-Repair r2 lab through the real
browser with account/session/preferences and its idle controller fingerprint
retained. It then exercises real registry-failure/browser retry through the actual
frozen controller. The maintainer's original image occupies the Seerr catalog slot
only for engine/download testing; it does not certify upstream Seerr accounts.
Both packaged browser cases pass, completing **eight live cases**. The actual
frozen controller's hash matches the package, the failed download creates no app
resources, and the browser retry completes the same deployment with one activation.
Production packages retain normal image restrictions and have no fault flags.

Final acceptance freshly authenticates all **nine main integrations** and confirms
unchanged main app/dashboard IDs, settings, credentials, nightly backup policy and
**16 tracked media/data files**. The packaged lab's separate **three-file** media
copy matches. Only this task's temporary containers/networks are removed; every
configuration volume, state folder, key and encrypted checkpoint remains. All nine
real cached catalog images pass the new digest/platform check read-only as well.

See [NETWORK-DOWNLOAD-RECOVERY.md](NETWORK-DOWNLOAD-RECOVERY.md) for preservation,
cleanup, exact acceptance scope and private evidence under
`test-results/docker-network-download-20261018-r2/`. The source audit narrowly
recognizes one quoted public Docker default subnet in its defining source file;
other addresses, paths and credentials still fail the same audit/package gates.
The exact exception and remaining address/token checks have regression coverage.
Proof includes `acceptance.json`, `cases.json`, `package-verification.json`,
`frozen-smoke.json`, `catalog-image-verification.json`, `main-authenticated-monitoring.json`,
`source-audit.json` and the three `packaged-*.png` screenshots. Full regression is
`test-results/network-download-regression-r2.xml`.

At that checkpoint the next Docker gate was the final app-install port-binding
conflict, now completed above. Whole-connection internet-loss acceptance, native/recipient
walkthroughs, shared/revoked users, major migrations, signing and signed-out/LAN
certification remain open.

## Stackarr runtime repair and storage-failure recovery

The bundle tested for that checkpoint is
**Stackarr-Docker-Runtime-Repair-Preview-20261018-r2.zip**.
Dashboard image: `sha256:1f42e159fdb9c33f935deb3d56517f4cb2c9dd21f598d88c1bb098296b63a4d2`.
ZIP SHA-256: `5dab88989317c0dafd1f6192aea7067c179852882a02bd7e3267dedb355d0a31`.
Its nine allowlisted entries/eight payload hashes verify. The extracted executable
passes **18 frozen smoke checks outside the checkout**. Full regression reports
**530 passed, 3 skipped**; Ruff passes and the portable-source audit reports
**245 files, 0 findings**. The skips remain the existing Windows filesystem-link cases.
The main installation stays on Self-Removal r4; it is not upgraded for these tests.

Settings now offers **Review Stackarr repair**. The first browser review can
prepare a verified runtime record through the authenticated controller without
requiring a status click first. Offline local approval requires that saved record.
The packaged startup helper opens a local repair review when managed startup fails.
Reviews bind the action and installation, expire after five minutes and are single-use.

Repair verifies the saved release, ownership, exclusive storage, private network,
enrollment, account, keys, settings and idle app jobs before pausing Stackarr.
Storage checks exercise available space and durable create/write/replace operations.
The independent supervisor tests checked configuration copies and an authenticated
encrypted checkpoint. Same-release promotion preserves account/password/sessions,
connections, app logins and backup files. Media-app containers and original storage
are excluded from candidate writes. Atomic release staging and journal replacement
keep the last committed version when writes fail.

All **ten final packaged Docker cases pass**: first-use browser repair, stopped
dashboard/controller, missing dashboard/damaged Compose, actual read-only/full
candidate storage, Windows file lock after actual database writes, worker exit and
fresh-process recovery, release-admission write denial/retry, unavailable runtime
and a late dashboard-port conflict. The full-filesystem case proves 61,487 partial
candidate bytes before ENOSPC. Unavailable Docker is simulated at the lab adapter
boundary; the shared engine is not stopped, and only the tiny disposable target fills.

The lab's fresh Sonarr/Radarr containers, settings, generated logins, Stackarr
account, backup/configuration bytes and three copied original media files are
preserved throughout. Final acceptance freshly authenticates all **nine main
integrations** and confirms unchanged main container IDs, settings, credentials,
nightly policy and **16 tracked media/data files**. Only this task's temporary lab
containers/networks and one abandoned plaintext work directory are removed. All
configuration volumes, keys, encrypted checkpoints and media are retained.

The matrix is documented in [RUNTIME-REPAIR.md](RUNTIME-REPAIR.md). Private proof:
`test-results/docker-runtime-repair-20261018-r2/acceptance.json`, `cases.json`,
`main-authenticated-monitoring.json`, `package-verification-r2.json`,
`source-audit.json` and the two `runtime-repair-browser-*.png` screenshots.
Full regression/smoke records are `test-results/runtime-repair-regression-r2.xml`
and `test-results/runtime-repair-frozen-smoke-r2.json`.

Guided Docker address-pool exhaustion diagnostics, interrupted registry pulls and
the final app-install port window remain next Docker gates. Native repair-window
walkthroughs, replacement Windows, lost keys/enrollment/network, unknown/shared
storage and corrupted accounts remain separate support/recovery boundaries.

## Claimed Plex, Seerr and Tautulli whole-host recovery

The claimed-account follow-up passes with the existing extracted
**Stackarr-Docker-Seerr-Plex-Maintenance-Preview-20261018-r2** package. No product
change, new package build or main-installation upgrade was needed.

The new five-app source lab restores encrypted configuration snapshots from only
the earlier stopped disposable account labs into fresh volumes. It contains the
claimed **Stackarr Maintenance Lab** Plex identity, Seerr's real Plex owner and
pending synthetic request, Tautulli's generated login/authenticated Plex connection,
and separate Sonarr/Radarr dependencies. The original containers remain stopped
and their volumes/media remain intact; only one copy of the claimed server runs.

The packaged browser creates and verifies a complete host recovery file. Its
independently retained copy and key survive removal of only this task's five source
configuration volumes and dashboard volume. The original source state is renamed
and unavailable at its original path; a different three-file media copy is mapped
for recovery. Wrong keys and occupied original ports are rejected.

An injected extraction failure occurs after real claimed-Plex configuration writes.
The stopped candidate's original machine identifier proves that write. All five
new recovery containers remain stopped. An attempt to recover into another empty
destination rejects those existing stopped resources without adoption. A fresh
packaged executable resumes the original review and reconstructs all five apps.

Recovered checks pass for the same claimed Plex identity, library IDs/UUIDs and
original video bytes; fresh Seerr Plex-owner sign-in, owner permissions, library,
Arr connections and pending request; Tautulli's saved web login/API key, Plex
monitoring and library/user records. All three account-app databases pass integrity
and record-preservation checks. Saved Stackarr credentials/password work, old
Stackarr sessions are rejected, private controller enrollment is regenerated,
all five dashboard integrations authenticate and backup schedules stay paused.

Final acceptance freshly authenticates all **nine main integrations**. Main
dashboard/app IDs, settings, credential fingerprints, nightly backup policy and
**16 tracked media/data files** match the baseline. Both new **three-file** media
copies and the original lab media match. The recovered apps, dashboard and
controller are stopped; original/recovered volumes, media, keys and encrypted
recovery files remain.

Validation: the packaged live backup/reconstruction/retry/account/browser matrix
passes; Ruff passes and the portable-source audit reports **240 files, 0 findings**.
The unchanged product/package retains its previous full regression result of
**511 passed, 3 skipped**, and 17 frozen smoke checks. Private evidence is under
`test-results/docker-claimed-host-recovery-20261018/`, including `acceptance.json`,
`verification.json`, `recovery-acceptance.json`, `backup-acceptance.json`, blocked
review reports and `claimed-recovered-dashboard.png`.

The same-computer Docker claimed-account gate is closed. Replacement Windows,
native dialogs, revoked/shared-user account changes and populated playback-history/
client-playback checks remain separate. See [HOST-RECOVERY.md](HOST-RECOVERY.md).

## Seerr Plex-owner sign-in, updates and recovery

The bundle tested for that checkpoint is
**Stackarr-Docker-Seerr-Plex-Maintenance-Preview-20261018-r2.zip**.
Dashboard image: `sha256:737f186343a43505b697cf3052e7a6253dd8994bd0d836c0907e916be9d52889`.
ZIP SHA-256: `293c99a0f347c1eeebdb01c0fc4ecfdc1d93a0ea4e66189e3c4bf4474bf97cee`.
Its nine allowlisted entries/eight payload hashes verify. The extracted executable
passes **17 frozen smoke checks outside the checkout**. The main dashboard and
controller remain on the earlier Self-Removal r4 package.

A new Seerr-only Docker installation signs in with a real Plex owner through
normal Plex authorization. Local sign-in and admission of new Plex users are off.
It connects only to the retained isolated Plex/Sonarr/Radarr lab. A separate movie
library references the same original test video; one synthetic pending request
provides a nonempty preservation check without submitting a download.

All **six native cases** pass: repair, failed-repair recovery, Seerr 3.4.1 → 3.5.0
update/manual rollback, rejection/recovery of an API-healthy candidate that disabled
Plex sign-in, fresh-process recovery after an actual worker exit during receipt
commit, and encrypted restore. Faults make real authentication-setting and request
database writes. Independent encrypted-snapshot inspection proves those writes.
Fresh cookie jars sign in through Plex after every case and verify the same owner,
permissions, library, connections and pending request.

All **five packaged browser app actions** also pass. An earlier Optional-Maintenance
r4 package creates a real update checkpoint. After promotion to the new package,
that older checkpoint rolls back correctly; new-package repair, update and rollback
then pass. The actual frozen controller performs the operations. Docker events
confirm **zero Seerr lifecycle events during Stackarr promotion**.

New Seerr maintenance checkpoints protect Plex account identity and sign-in/admission
settings. Their recorded version preserves compatibility with older encrypted runs.
Only the advancing library `lastScan` cursor is excluded; library selection and all
other protected settings remain checked. The first candidate exposed that volatile
cursor, and the final r2 package passes the complete acceptance matrix.

Final checks verify all **nine main integrations** with fresh authenticated requests
from the actual dashboard. Main dashboard/app identities, settings, credential
fingerprints, nightly backup policy and **16 tracked media/data files** match the
baseline. All **three lab media files** match. The new lab and its three borrowed
dependencies are stopped; configuration volumes, keys and encrypted backups remain.

Validation: **511 passed, 3 skipped**, Ruff passed, portable-source audit **239 files,
0 findings**, plus **17 frozen checks**. Private evidence is under
`test-results/docker-seerr-plex-maintenance-20261018/`; regression and executable
reports are `test-results/seerr-plex-maintenance-regression-r2.xml` and
`test-results/seerr-plex-maintenance-frozen-smoke-r2.json`.

Plex-owner compatible maintenance now passes. Invited/shared-user permissions and
revocation, major migrations, recipient-browser Plex popup behavior and broader
Windows/LAN certification remain open. Claimed-account whole-host Docker recovery
subsequently passed in the follow-up above. A misleading
legacy-image first-run config-mount warning also needs setup-usability work; actual
volume ownership and persistence pass. See
[SEERR-PLEX-MAINTENANCE.md](SEERR-PLEX-MAINTENANCE.md) for the precise boundary.

## Plex, Seerr and companion maintenance

The preceding private bundle is **Stackarr-Docker-Optional-Maintenance-Preview-20261018-r4.zip**.
Dashboard image: `sha256:702211ee1c3a18962b89cea6b21f5a143c336b81a0b55348c3bfe5fb34e6c1b6`.
ZIP SHA-256: `4b22f30bf7233327d9bb9668ef58c4804753d79f9a1cf1eae2a23529480827e4`.
Its nine allowlisted entries and eight payload hashes verify; the extracted
executable passes **17 frozen smoke checks outside the checkout**. The package
contains no runtime state, credentials, account tokens, media or backups.
The existing main dashboard/controller remains on the Self-Removal r4 package.

The same-major update catalog now covers all nine apps. Tautulli and Kuma release
checks use their authenticated running APIs rather than assuming image branch
labels are versions. Protected checks cover Tautulli's Plex identity and login,
Kuma's monitors/API-key records, Cleanuparr's complete configuration and Seerr's
actual Arr paths, profiles, Plex settings, users and paginated request identities.
Plex repair/update/rollback reuses its verified original anonymous transcode volume.
Unknown extra mounts still block maintenance. Candidate login checks use the
reviewed candidate recipe before committing the new receipt.

The fresh isolated lab uses five target apps plus three separate Arr/download
services. The owner separately claimed **Stackarr Maintenance Lab**; no existing
Plex identity, configuration or token was copied. Tautulli uses that server's real
authentication over the private network. Invalid peer tokens are rejected and
remote access/network-authentication exceptions are disabled. Seerr has a generated
local administrator and real Sonarr/Radarr connections. Kuma has eight service
monitors. Cleanuparr has three tested connections, dry-run and all five jobs off,
with no media, downloads or Docker-socket mounts.

The native matrix passes **30 cases across five apps**: repair, recovery after
confirmed failed-repair configuration writes, distinct-image update and manual
rollback, failed-update recovery after actual writes, fresh-process recovery
after an actual worker exit in the receipt file/database commit gap, and encrypted
configuration backup/restore. Independent inspection of all five pairs of encrypted
repair snapshots proves the failed candidates overwrote the configuration sentinel
and created a new marker before recovery. Each case verifies protected settings,
logins, connections, other app IDs, sample hashes and the unchanged main installation.

The final extracted r4 package also passes **15 authenticated browser actions**:
repair, distinct-image update and reviewed rollback for each of the five apps.
Settings, generated logins, connections, monitors, disabled cleanup and media
survive each action. The actual frozen controller and bundled dashboard perform
these operations. The browser matrix uses the same eight isolated apps and
retained volumes after importing only their controller state with that controller stopped.
Earlier incomplete r3 browser evidence is retained separately and is not the
delivered acceptance result.

Final acceptance verifies each original image/version and its saved protected
checkpoint after rollback, original claimed Plex identity/video/transcode volume,
local Seerr password login and all companion connections/safety settings. The
running frozen controller hash matches the package. All **nine main integrations**
authenticate freshly from the actual dashboard using its encrypted credential store.
Main dashboard/app container IDs, logical settings, credential hashes and **16
tracked media/data files** match the baseline; the nightly backup policy is retained.
The isolated eight apps, dashboard and controller are stopped. All lab volumes,
three original media files, keys and encrypted snapshots remain. Generated plaintext
work archives left by the deliberate worker crashes were removed within the lab.

Acceptance found and fixed real compatibility gaps: candidate login checks used
the old receipt, Plex update recipes did not retain its reviewed scratch volume,
Seerr checkpoints used an incorrect library-path field, and the browser update
request schema still accepted only the original six apps. Cleanuparr 2.10.11 adds
an errored-torrent option; only its exact inactive zero/false default is normalized
against 2.10.10. Changed thresholds/deletion flags still reject the candidate.
The browser update authorization contract now covers all nine catalog apps.

Validation: **503 passed, 3 skipped** (existing Windows filesystem-link cases),
Ruff passed, portable-source audit **236 files, 0 findings** and **17 frozen checks**.
Private evidence is under `test-results/docker-optional-maintenance-20261018/`,
including `native-report.json`, `native-evidence.json`, immutable previous-image
records, `packaged-browser-report.json`, `acceptance.json`,
`main-dashboard-monitoring.json`, screenshots and package verification.
Regression and executable reports are
`test-results/optional-maintenance-regression-r4.xml` and
`test-results/optional-maintenance-frozen-smoke-r4.json`.

At this earlier checkpoint, Seerr Plex/SSO maintenance remained open; the follow-up
above covers compatible Plex-owner maintenance. Major migrations, claimed-account
whole-host recovery, native dialog/novice walkthroughs and clean-Windows/LAN
certification remain open.
See [OPTIONAL-APP-MAINTENANCE.md](OPTIONAL-APP-MAINTENANCE.md) for versions and
account boundaries, and [COMPLETION-PLAN.md](COMPLETION-PLAN.md) for the next work.

## Safe Stackarr removal and reinstall

The previous private bundle is **Stackarr-Docker-Self-Removal-Preview-20261018-r4.zip**,
with dashboard image `sha256:277cdc16190659b792ed376f6732c1ccda5984d0abdf9f6085c323b192211def`.
Its ZIP checksum, nine allowlisted entries and eight payload hashes verify. The
extracted executable passes **17 frozen smoke checks outside the checkout**. The
unsigned package contains no runtime state, enrollment, credentials or media.

**Settings → Stackarr updates & rollback → Review Stackarr removal → Remove
Stackarr, keep settings** pauses only Stackarr, verifies an encrypted complete
configuration checkpoint, then removes its exact owned dashboard container and
stops its authenticated private controller. The account, settings, keys, app
credentials/logins, receipts, backups, images, network and staged releases remain.
Media apps keep running. Scheduled Stackarr backups pause until reinstall.

Reopen **Start Stackarr.cmd** with the same state folder to open the local
**Review reinstall** window. Approval expires after five minutes and is claimed
only once. Reinstall uses the same retained release, copied controller state and
a new dashboard volume. Logical account/settings/credential fingerprints, keys
and backup/configuration-file content hashes gate promotion. Existing stopped or
foreign containers, shared/missing/changed retained storage and occupied saved
ports are checked again before execution; no other service is stopped or adopted.

Completed removal stays offline until reviewed reinstall. A deliberate non-Compose
receipt and separate retained-maintenance pointer protect against older launchers
replaying new operations as updates. Interrupted removal resumes the original
container if deletion did not happen, or records completed removal without repeating
deletion. Failed/interrupted reinstall returns to the removed state with the original
data; candidate volumes and encrypted checkpoints remain available for inspection.

Packaged Docker acceptance used the retained four-app original-sample lab.
Authenticated browser removal and frozen two-step local reinstall passed with
the existing owner password. Reused approvals and both saved-port conflicts were
rejected. An older package refused to start completed removal and left both
interrupted removal and interrupted reinstall untouched. The current PowerShell
launcher also kept removed Stackarr offline in its no-browser mode.

The failed-candidate test observed an actual preference write in the copied
dashboard database, then let normal protected-data checks reject it. Original
account, settings, keys and backups were recovered to the removed state. Separate
actual supervisor exits followed confirmed dashboard deletion and confirmed
candidate database writes. Fresh packaged startup recovered both cases; a final
reviewed reinstall succeeded. The four original media-app IDs, protected settings,
generated logins/library records and **6 original lab files** were compared
throughout, along with all nine main app IDs, complete logical Stackarr fingerprints
and **16 main media/data files**. Cleanup removed only isolated containers/networks,
retaining all settings volumes, samples, staged releases and checkpoints.

Acceptance exposed two compatibility problems: a controller review recursively
acquired its own single-request RPC lane, and an older supervisor interpreted a new
terminal status as an unfinished update. Reviews now verify the current controller
locally; retained-data jobs use their own pointer and a legacy-compatible terminal
status. The initial compatibility test restarted only the isolated dashboard.
Its exact runtime and complete protected data were verified before clearing the
stale marker. Final older-launcher refusal tests pass at all three boundaries.

Validation: **485 passed, 3 skipped** (existing Windows link cases), Ruff passed,
both browser smoke modes passed, source audit **231 files, 0 findings**, and all
17 final frozen checks passed. Evidence is under
`test-results/docker-self-removal-20261018/`, including `final-acceptance.json`,
`report.json`, native review/reuse results, confirmed-write/deletion proofs,
legacy-launcher refusals and browser screenshots. Final regression and frozen
reports are `test-results/self-removal-regression-r4.xml` and
`test-results/self-removal-frozen-smoke-r4.json`. Baselines, encrypted approvals,
state and keys are private and must not be shared with the package.

The main dashboard and controller now use this package. Removal was reviewed
without approval; main Stackarr was never removed or reinstalled. All **nine
original media-app container IDs** remain running with fresh monitoring. Complete
logical controller/dashboard fingerprints, integration settings/credential hashes
and all **16 main media/data file hashes** match the baseline. The existing nightly
backup plan remains **03:00 host-local / 7 scheduled copies per installation**, with
all nine apps selected. Only Stackarr was updated. See `main-verification.json`.

Lost/corrupt state still requires verified whole-host/media recovery. Broader
optional-app/claimed-account runtime acceptance, native dialog/novice walkthroughs,
signing and clean-Windows/LAN certification remain open. See
[SELF-REMOVAL.md](SELF-REMOVAL.md) and [COMPLETION-PLAN.md](COMPLETION-PLAN.md).

## Earlier 18 October checkpoint — Safe Docker app repair and removal

The preceding private bundle was **Stackarr-Docker-App-Maintenance-Preview-20261018-r4.zip**,
with dashboard image `sha256:a9d067fab09badc83a0b6347229ce7b5e2339f93bdd777cd335180711dae6efe`.
Its ZIP checksum, nine allowlisted entries and eight payload hashes verify. The
extracted executable passes **16 frozen smoke checks outside the checkout**. The
unsigned bundle contains no runtime state, enrollment, credentials or media.

**Apps → Start, stop & recover → Check installation** offers **Review repair** and
**Review remove** for one verified owned app. Repair recreates its container from
the same saved image, folders and ports. Removal deletes only the container and
keeps settings, generated logins, connection details, media, downloads and backups;
Repair brings it back. Both verify an encrypted configuration snapshot first and
copy it to an already configured separate backup disk before container deletion.
Retained settings can still be backed up while the app is absent without starting it.

Existing stopped apps are recreated without being started. Docker event history
confirms the disposable replacement did not start until the later explicit Start
action. A missing app starts from retained settings. Shared/missing volumes,
unavailable or linked media roots, changed container identities, environment,
mounts or privileges and occupied saved ports block unsafe replacement. Plex's
image-declared anonymous scratch cache is retained by its verified exclusive
identity; unknown, shared or host-bound extra mounts are rejected.

Failed repair saves candidate settings separately and restores its verified
before-repair checkpoint and previous running state. An interrupted operation
requires **Review maintenance recovery → Recover maintenance** after reopening
Stackarr; startup never replays removal. Pending recovery blocks other mutations
and scheduled backups. Contract tests cover interruption immediately before and
after container removal, preserving the original container or completed removal
respectively without repeating deletion.

Final packaged acceptance used qBittorrent in the retained four-app original-sample
Docker lab. Browser repair, removal, backup while absent, occupied-port rejection,
bringing the app back and stopped-app repair passed. A maintainer-only readiness
failure followed a confirmed candidate configuration write; automatic recovery
removed that write and preserved protected API settings, generated logins, library
records and all **6 lab media/data files**. A separate actual worker exit followed
another confirmed write. Reopening the final frozen controller marked the operation
for explicit browser recovery, which restored the original settings and login.
The three peer app containers kept their original IDs throughout.

The main dashboard and controller now use this package. All **nine original app
container IDs** remain running with fresh authenticated monitoring. Complete logical
controller/dashboard fingerprints, integration settings/credential digests and all
**16 main media/data file hashes** match the baseline. No main app repair, removal
or restore was approved; only Stackarr was updated. All nine apps passed read-only
repair reviews. The existing **03:00 host-local / 7 scheduled copies per installation**
backup plan still covers all nine apps on its separate disk. Isolated containers
and networks were removed, retaining four app settings volumes, sample media,
encrypted snapshots and staged releases.

Validation: **463 passed, 3 skipped** (existing Windows link cases), Ruff passed,
both browser smoke modes passed, source audit **226 files, 0 findings**, and all
16 final frozen smoke checks passed. Evidence is under
`test-results/docker-app-maintenance-20261018/`: `final-acceptance.json`,
`stopped-repair-events.json`, `report.json`, `main-verification.json`,
`final-backup-and-retention.json`, sanitized action results and browser screenshots.
The final regression and frozen reports are
`test-results/app-maintenance-regression-r4.xml` and
`test-results/app-maintenance-frozen-smoke-r4.json`. Baseline files and retained
runtime state are private and must not be shared with the bundle.

These controls repair containers around intact settings, rather than reconstructing
lost volumes or repairing corrupt app databases. Claimed-account/optional-app runtime
repair acceptance, major migrations,
recipient walkthroughs, signing and clean-Windows/LAN certification remain open.
See [APP-MAINTENANCE.md](APP-MAINTENANCE.md) and [COMPLETION-PLAN.md](COMPLETION-PLAN.md).

## Earlier 18 October checkpoint — Stackarr self-update and rollback

The preceding private bundle was **Stackarr-Docker-Self-Update-Preview-20261018-rc11.zip**,
with dashboard image `sha256:ccdf776dcb4b0c8426a71b269b2b67763fd613a9e387179d78a733c8a92189e9`.
Its ZIP checksum, nine allowlisted entries and eight payload hashes verify. The
extracted executable passes **15 frozen smoke checks outside the checkout**. No
runtime state, media, account credentials or enrollment is included. This is an
unsigned private preview, built from the working source rather than a new commit.

**Settings → Stackarr updates & rollback** selects a trusted complete compatible
ZIP through a fixed native Windows chooser, then uses an expiring session-bound
review and one-use approval. An independent known-working native supervisor
updates both the Docker dashboard and Windows controller. Only Stackarr pauses;
media apps stay running. The candidate receives copied controller state and a new
dashboard volume with app jobs disabled. Image/executable identity, pinned TLS,
account, saved settings, decrypted-credential digests and key digests gate commit.
The entire dashboard configuration volume is retained, including local backup files.
Encrypted checkpoints and earlier complete releases support recovery after a crash.

Manual rollback first authenticates its saved checkpoint and takes a current safety
copy. It restores earlier Stackarr preferences while retaining the current owner
password and browser sessions. Changed app connections, credentials or ownership
block replay of an older checkpoint. The final browser test deliberately changed
a lab-only preference, verified it was locked during maintenance, then verified
the earlier value reloaded into the editable Settings form with no stale restart
error. Reopening an older recovery-capable package follows the saved active release
or recovers pending maintenance; it does not silently downgrade a completed update.

Real packaged acceptance uses the retained four-app core lab with **6 original
media/data files**. Successful updates and reviewed rollback preserved its app
container identities, generated logins, library records, protected settings and an
extra Stackarr configuration-file marker. A guarded broken candidate writes to
its copied database while reporting healthy; data verification rejects it and
returns to the previous release and original volume. The interruption test observes
those actual candidate writes, pauses only that candidate, kills only the recorded
maintenance worker and reopens the older packaged launcher in a fresh process.
The main nine-app installation, its settings/credential hashes, **16 media/data
file hashes** and unrelated running containers are compared throughout.

Acceptance exposed and fixed an independent-process PyInstaller lifetime issue,
overly broad copied-key permissions, stale Settings values after rollback and a
controller status/probe timing race. Independent processes use PyInstaller's
documented fresh-runtime environment; keys retain restrictive file modes. Read-only
signed probes now retry transient busy/unavailable responses within a fixed bound;
write approvals are never retried. The intermediate timing failure recovered from
its retained checkpoint by reopening the packaged launcher. The older disposable
baseline was upgraded through authenticated review/approval without browser polling
until the correction was active. The final worker then passed browser rollback
with status polling and authoritative Settings reload.

Validation: **443 passed, 3 skipped** (existing Windows link cases), Ruff passed,
both browser smoke modes passed, source audit **222 files, 0 findings**, and the
final extracted executable passed all 15 smoke checks. Evidence is retained under
`test-results/docker-self-update-20261018/`, including sanitized operation results,
browser screenshots, `report.json`, `cleanup.json` and `package-verification.json`;
the frozen report is `test-results/self-update-frozen-smoke-rc11.json`.

The main dashboard and controller now use this package, with self-update controls
verified through Settings and no update/rollback approval on the main installation.
All **nine original media-app container IDs** remain running with fresh monitoring.
Original integration settings/credential hashes and all **16 media/data hashes**
match the pre-test baseline. Only Stackarr's dashboard container was replaced;
no main app was restored, updated or recreated. See `main-verification.json` in
the evidence folder. The isolated test containers/networks were removed, retaining
their configuration volumes, media, staged releases and encrypted checkpoints.

Compatible preview packages only: major state migrations, signed update
distribution, native ZIP-dialog and novice walkthroughs remain open. Checkpoints
and staged releases have no automatic retention yet and require free local disk
space. Keep the complete private state directory and a recovery-capable package;
use whole-host and media backups for host-disk loss. See [SELF-UPDATE.md](SELF-UPDATE.md).
Reviewed owned-app repair/removal subsequently passed the checkpoint above.
Broader update and recipient acceptance remain open.

## Earlier Docker checkpoints — 17 October 2026

## Whole-host configuration recovery

The current private bundle is **Stackarr-Docker-Host-Recovery-Preview-20261017-rc5.zip**,
with dashboard image `sha256:3b3f24cf61a1b78ad44e15f42a41145148c23990d545513dd990dec489b1aa64`.
The extracted executable passes 14 frozen smoke checks outside the checkout. No
runtime state, media, enrollment or credentials are included in the package.

**Backups → Prepare whole-host recovery** reviews every owned installation,
including installations older than the dashboard's recent-operation list. Its
approved job creates consistent encrypted app snapshots and fresh controller and
dashboard SQLite checkpoints. One authenticated `.stackarr-recovery` file includes
the owner account, app credentials/logins and fixed-recipe installation receipts.
A configured separate backup disk receives a verified copy. The recovery key is
exported separately behind owner-password verification; media is excluded.

**Recover Stackarr.cmd** provides a local file/folder review and recovery entry
point without recipient Python or browser uploads. It refuses existing app
containers, volumes or matching networks, verifies all archives before Docker
writes, retains original app ports and remaps approved media roots. It creates
new controller enrollment, revokes sessions and pauses backup schedules for review.
Extraction failure stops only the new recovery containers. A saved review can
resume against the exact same owned containers and unshared volumes.

The isolated acceptance lab created **nine apps in three deployment groups** with
copied original samples. It verified a complete host file, removed only its ten
generated app/dashboard volumes, and made the original controller/account state
unavailable. A real extraction wrote one new volume before an injected failure;
all nine new containers remained stopped. A fresh **final packaged executable**
then restored all nine volumes and the dashboard account. The saved Stackarr
password, all controller credentials, three generated Arr web logins, protected
core settings, authenticated core/Kuma monitoring and nine configuration fixtures
verified. Both sample folders retained all **6 file hashes**. The main installation
retained its nine app IDs, settings/credentials and **16 media/data hashes**.
Existing resources, a wrong key and an occupied original app port were rejected
before recovery writes. Synthetic checks also reject truncated/corrupt/incomplete
files, arbitrary Compose options, extra mounts and unlabelled conflicting volumes.

The lab exposed a Docker Desktop Windows/Linux bind-path spelling mismatch, now
handled with an additional enrollment-file fingerprint check. Cleanuparr's first
run needed its safe account setup before clean shutdown; the forced-shutdown backup
guard was retained. Acceptance-harness assertions/client lifetime and bootloader
process cleanup were corrected without changing existing main applications.

The main dashboard/controller now use this package; all **nine apps remain fresh**,
with the original app containers, settings and 16 media/data hashes preserved.
No main application was restored or recreated.
The main nine-app recovery review passed without approval or app downtime. The
isolated recovered containers and networks were removed afterwards, retaining all
ten configuration volumes, both sample folders and the private recovery copies.
The final ZIP checksum, nine allowlisted entries and eight payload hashes passed.

Validation: **426 passed, 3 skipped** (existing Windows link cases), Ruff passed,
both browser smoke modes passed and source audit **216 files, 0 findings**.
Evidence: `test-results/docker-host-recovery-20261017/report.json`, the backup review
and recovered-dashboard screenshots, frozen recovery reviews/results and
`test-results/host-recovery-frozen-smoke-rc5.json`.

This is same-computer isolated Docker reconstruction, not replacement-Windows
certification. Plex/Seerr/Tautulli use first-run recovery fixtures; claimed-account
and full request/playback recovery need further acceptance. Cleanuparr uses a
generated account with dry-run and automation disabled. Native recovery-dialog
and novice walkthroughs remain open. Complete host recovery files are explicitly
prepared; nightly app snapshots do not automatically refresh them. See
[HOST-RECOVERY.md](HOST-RECOVERY.md).

## Simple folder selection and occupied-port recovery

The current private bundle is **Stackarr-Docker-Setup-Preview-20261017-rc3.zip**,
with image `sha256:5eb887042a7e9c711090a6092447f1540a4d03e4e5523d76c1455cb3da1c371a`.
Its extracted executable passed the frozen smoke check outside the checkout,
including actual occupied-wildcard-port rejection. The ZIP checksum, seven payload
hashes and eight allowlisted entries passed verification. No runtime data is bundled.

New setup defaults to **Choose available ports for me**. Manual defaults, sequential
ports and custom numbers are under Advanced port settings. The host checks actual
availability, excludes dashboard/controller ports and resolves duplicate choices.
Windows probes use exclusive wildcard binds to avoid shadowing an existing service.
A fresh bootstrap also selects available dashboard/controller ports and persists
them; reopening uses the saved addresses instead of moving existing installations.

Approval rechecks ports after review. A port taken while images download stops the
empty attempt before media folders, app volumes or containers are created. **Use
available ports** preserves the folder and unaffected port choices, then requires a
fresh installation review. The empty earlier attempt is retained as replaced.
Availability checks do not reserve ports; a conflict in the final Docker-start
window remains a separate recovery case.

Folder choice now happens in the wizard only when a selected app needs media.
A single approved folder is proposed automatically. A fixed host Windows folder
dialog can grant another direct existing directory; browser-supplied paths cannot
grant access. Grants append to a durable list with stable reference numbers.
Cancellation preserves the prior folder and configured apps keep their existing
paths. Long paths wrap on phones. Monitoring-only setup needs no media folder.

The extracted package's real Docker/browser check exercised busy dashboard,
controller and app ports, both late-conflict paths, a media folder with spaces and
non-Latin characters, three privately connected/wired Arr/downloader apps, and
reopening with saved addresses and container IDs intact. Standalone Kuma then
installed, completed protected setup and reached fresh monitoring with no media
root granted. Existing listeners received **zero connections** from the checks.
The existing main stack's nine integration settings/credential hashes and **16
media/data hashes** matched. The final dashboard/controller upgrade also preserved
all nine app containers and returned fresh monitoring for all nine integrations.

Two harness assertions were corrected: connection-result text includes the app
name, and refresh queues work with HTTP 202. Accumulated disposable networks also
exhausted Docker's default address pools. Only this task's verified stopped test
projects were released, keeping every configuration volume and media file; every
running container stayed running. No global prune or Docker restart was used.

Evidence: `test-results/docker-folder-ports-018b3c86d2dc/report.json`, its desktop/
phone folder and conflict screenshots, `test-results/setup-frozen-smoke-rc3.json`,
`test-results/setup-network-capacity-repair.json`, and the main preview's
`update-main-preview-report.json`. Final regression: **409 passed, 3 skipped**, two
upstream deprecation warnings; both browser smoke modes and Ruff passed. Portable
source audit: **211 files, zero findings**.

Cancellation UI uses a response fixture; persistent grants, cancellation and path
rejection are separately contract-tested. Native Windows folder-dialog interaction
and a novice recipient walkthrough still need a person. Whole-host recovery,
Stackarr/optional-app updates, signing and deferred Windows/LAN certification retain
their release gates.

## Packaged companions and nine-app monitoring

The preceding companion bundle was **Stackarr-Docker-Companions-Preview-20261017-rc4.zip**,
with image `sha256:d0fdb2d7fc304969792e9cf30d3bb67199dcfb4eec8d08b437cf9295cb4b5aa5`.
The extracted executable passed its frozen smoke check outside the source checkout,
including the protected companion setup and bounded Kuma polling protocol. The
allowlisted ZIP contains no runtime state, credentials or media.

The packaged browser installed Tautulli, Uptime Kuma and Cleanuparr as a separate
owned group, without requesting a media folder. A reviewed setup step creates
generated local logins, links Tautulli to the identified Docker Plex server, adds
nine TCP service monitors to Kuma, and tests/creates Cleanuparr's Sonarr, Radarr and
qBittorrent connections. Private controller handoff activates all three dashboard
collectors. The owner-password-protected login panel verified each generated login.

Cleanuparr 2.10.11 has dry-run enabled, local authentication bypass disabled, four
cleanup job switches off and both Seeker search switches off. Every companion has
exactly one named configuration volume, no media/download bind and no Docker
socket. Stackarr reads safety settings and warns on changed automation; it never
triggers cleanup. Kuma 2.5.6 slim uses SQLite on its local named volume. Its TCP
monitors test port availability; Stackarr independently checks authenticated APIs.

Isolated runtime checks caught and fixed Tautulli's CSRF/token endpoint sequence,
Kuma's required key/monitor fields, and Seeker's separate search switches. An empty
Tautulli activity object now reports unavailable instead of being counted as zero
streams. The final package resumed the owned setup and verified an actual Plex
activity response. Repeating setup in the disposable lab created no duplicate
monitors or connections. Encrypted companion backups and restart persistence also
passed there, including Plex credentials and all cleanup safety switches.

Cached companion images initially contained zero-length executables. Only unused
exact image references and the recorded, stopped failed Kuma test container were
removed; its configuration volume was retained. Repulling official immutable
images repaired startup. No Docker restart, pruning or host reboot was used.
The repair receipt is `test-results/companions-research-20261017/kuma-cache-repair.json`.

The main preview at `http://localhost:29100` now reports **9/9 fresh integrations**
and **nine monitors up**. Its existing six app settings, encrypted credential values,
container identities and all **16 media/data file hashes** matched the baseline.
Only the dashboard/controller changed during package upgrades. No personal native
Plex instance or media was adopted. The 03:00 nightly plan still retains seven
scheduled copies per installation on D:, now including the companion group. A
verified encrypted companion snapshot was copied to D: without stopping the
existing six apps.

Evidence: `test-results/docker-plex-bc615eaf1fe6/companions/report.json`,
`companions/nine-apps.jpg`, `test-results/docker-companions-20261017/report.json`,
and `test-results/companions-frozen-smoke-rc4.json`. Final regression: **399 passed,
3 skipped**, two upstream deprecation warnings; both browser smoke modes and Ruff
passed. Portable source audit: **206 files, zero findings**. Recipient walkthroughs,
each companion alone, optional-app image updates and whole-host reconstruction
remain separate gates. Companion review now works inline in both Apps and the
setup wizard; both paths passed the browser regression.

## Scheduled backups, retention and separate-disk recovery

The preceding backup bundle was **Stackarr-Docker-Backups-Preview-20261017-rc1.zip**, with
dashboard image
`sha256:871aacf97b5daed3e7893a4872250adeef22ca91e3eef19dae3a579f47d2eba1`.
All eight ZIP payloads and the ZIP checksum passed verification; no runtime state,
credentials or media are bundled. The extracted executable passed its frozen
smoke test outside the checkout, including the new backup modules.

Backups → Automatic backups offers selected installations, nightly host-local
time, 1–90 scheduled copies per installation and a host-approved second-disk
folder. The Windows folder dialog grants the destination; browser paths are not
accepted. Physical-disk metadata, direct paths and a namespace ownership marker
bound external storage. The controller's exclusive worker claims due jobs
transactionally; missed nights run once, failed runs retry after an hour, and an
interrupted running backup disables its schedule pending an app-state check.

New manual, scheduled and before-restore snapshots are verified locally and copied
encrypted to the selected disk before scheduled retention. Manual, safety and
update/rollback recovery snapshots are preserved. Cleanup removes exact owned
payloads only and refuses unexpected files or links. Registered external copies
can restore missing local archives with existing ownership/version checks and a
separate before-restore safety copy. Owner-protected recovery-key export passed
against the packaged private controller; the key was neither printed nor saved in
the acceptance report. Keep the recovery key separately and privately.

The extracted package's real wall-clock scheduler completed a due nightly backup
in the disposable four-app Docker lab. Two browser Run now actions exercised
retention: exactly two scheduled snapshots remained and historical manual/safety/
update snapshots were preserved. D: was confirmed as a different physical disk
from C:, which contains both controller state and Docker's virtual disks. After
removing the local snapshot and deliberately changing a setting in each real app,
a corrupt D: copy was rejected before downtime. The repaired valid copy then
restored all four original settings, generated logins and library records through
the browser. Container identities, dashboard settings and all **six original
media/data file hashes** matched, and all four collectors returned fresh results.

The harness initially expected the enabled-plan notice while disabling the test
schedule after successful recovery. That assertion was corrected; a verification
pass checked completed jobs, original encrypted settings checkpoints and fixture
hashes without repeating the restore. Evidence:
`test-results/docker-core-05cebfd84fd1/scheduled-backup-report.json`,
`scheduled-backup-cleanup-report.json`, `scheduled-backup-results.png` and
`backup-key-acceptance.json`.

The same package now runs the main six-app preview. Its plan is enabled for
**03:00 nightly**, retaining **7 scheduled copies per installation** in
**D:\Stackarr Backups**. The initial browser Run now action saved and verified
Plex, Seerr and all four core app configurations on D:. No main data was restored.
Dashboard settings stayed unchanged, all **16 media/data file hashes** matched and
all six collectors returned fresh authenticated results. The dashboard upgrade
also preserved app images/container identities and unrelated running containers.
The test schedule was disabled and its four apps, dashboard and controller stopped;
all test volumes, media and external backups were retained. The main controller and
nightly plan remain active. Evidence:
`test-results/docker-plex-bc615eaf1fe6/scheduled-backup-report.json`,
`update-main-preview-report.json` and `scheduled-backup-controls-proof.jpg`.

Regression: **379 passed, 3 skipped**, two upstream deprecation warnings. Both
browser smoke modes and Ruff pass; the portable-source heuristic audit scans
**200 files with no findings**. Media is excluded and needs its own backup.
Whole-host reconstruction, network/cloud destinations, key rotation and unattended
Windows startup remain separate work.

## Docker app updates and image/data recovery

The preceding private bundle was **Stackarr-Docker-Update-Preview-20261017-rc1.zip**,
with dashboard image
`sha256:d44b003e3ea94f5b6e9f47a8bfe11fe1dcea198dcc17f35a79d16b9db7467cbf`.
The extracted executable passed its frozen-runtime smoke test outside the checkout,
including the bundled update catalog. All eight allowlisted ZIP payloads and the
ZIP checksum were verified; runtime data, credentials and media are excluded.

The dated catalog pins newer LinuxServer container builds for qBittorrent, Sonarr,
Radarr and Prowlarr, verified against official registry image metadata. Their app
versions remain the same; these are compatible container-build updates. Plex and
Seerr already match the reviewed candidates. The dashboard accepts app/update IDs
only, with session-bound single-use review; browser images/Compose are rejected.

The updater downloads first, verifies platform/version and the current app, then
stops only the selected service. It saves and verifies an encrypted configuration
snapshot before recreation. Three authenticated health checks and protected
settings, library records/identity and connection readback gate commit. A failed
update restores the previous image and matching data. Manual rollback retains a
safety copy of newer settings and attempts forward recovery if the old version
fails. Snapshot compatibility ignores only the controller's operational update
label; app images and other installation settings remain version bound.

An encrypted durable journal records image identities, snapshot references and
both receipt variants before mutations. Receipt file/database commit is journaled;
startup marks unfinished operations needs-recovery without replaying writes.
Reviewed recovery verifies the recorded container/volume and supports interruption
between removal and creation. An unresolved recovery blocks another app mutation.
The app never prunes images/volumes or invokes media/download deletion APIs.

The real Docker failure fixture used the disposable core lab's official Prowlarr
candidate. After its authenticated startup, the test deliberately changed an Arr
UI preference in the actual database and created a configuration marker, then
rejected the health gate. Automatic recovery restored the old image/settings,
normal generated logins and library records, removed the candidate marker and
preserved all six media/data file hashes. A second case interrupted the transaction
after those writes and between saving the Compose file and database receipt.
A fresh process recovered the old image/data pair with the same preservation checks.
These are injected failures; no upstream defect or major schema migration is claimed.
Evidence: `test-results/docker-core-05cebfd84fd1/update-fault-report.json`.

The extracted final package passed real browser update and manual rollback for
Prowlarr, Sonarr, Radarr and qBittorrent. Each pair preserved the other app
container identities, protected settings, generated logins, library records and
all six media/data file hashes. All eight actions completed before a final
screenshot hit an asynchronous page refresh. A read-only verification resumed the
capture, checked the completed encrypted journal and original fixture hashes,
and saved the final report without repeating updates. The four test apps,
dashboard and controller were then stopped; volumes, backups and media remain.
Evidence: `test-results/docker-core-05cebfd84fd1/update-browser-report.json`,
`update-browser-cleanup-report.json` and `update-browser-results.png`.

The update package was deployed to the main preview at `http://localhost:29100`.
Apps → Updates & rollback offers four reviewed candidates; Plex and Seerr already
match the packaged catalog. Only the Stackarr dashboard/controller changed.
All six main app containers and images stayed in place, all six collectors
returned fresh authenticated results, settings stayed unchanged and all **16
media/data file hashes** matched. Unrelated running containers were preserved.
Evidence: `test-results/docker-plex-bc615eaf1fe6/update-main-preview-report.json`
and `update-controls-proof.jpg`.

Regression: **366 passed, 3 skipped**, with two upstream deprecation warnings.
Both browser smoke modes and Ruff pass. The portable-source heuristic audit scans
**196 files with no findings**. Updates remain limited to reviewed same-major Linux
x64 candidates. Major migrations, Stackarr self-update, off-disk/scheduled backups,
optional-app update coverage, LAN/startup certification and signing remain open.

## Docker lifecycle and encrypted configuration restore

The preceding private bundle was **Stackarr-Docker-Recovery-Preview-20261017-rc3.zip**,
with dashboard image
`sha256:a9c71f9f963ced09f61e6bf53f6236d8e3328866b1bf5b2bba190dfcff2a02cc`.
Its extracted executable passed the frozen-runtime check outside the source tree.
The bundle contains eight allowlisted payloads and no runtime state or secrets.

Apps now offers installation checks and reviewed Start, Stop and Restart through
the private controller. Actions recheck receipts and immutable container IDs;
no app is recreated or upgraded. Cached installations stay visible during a
controller outage. Dashboard RPC calls are serialized, so background status polls
cannot interrupt a user's reviewed operation. Interrupted actions require a new
review instead of replaying writes.

Backups now offers encrypted app-configuration snapshots, verified before restore,
with a separate before-restore safety snapshot. Running apps stop cleanly and
restart afterwards; stopped apps stay stopped. The helper checks exclusive owned
volume consumers, has no network and never mounts media/download folders. Archive
checks reject traversal, special files, escaping links, link chains and writes
through links, while supporting Seerr's safe relative log links. Failed extraction
attempts rollback; failed rollback keeps the apps stopped with the safety copy
retained. The encrypted controller checkpoint preserves receipts/credential state;
normal app restore leaves active dashboard/controller settings unchanged.

The extracted package passed real browser Stop, Start and Restart, then backup and
restore on the original four-app disposable import lab. Each app's UI/preference
setting was deliberately changed after the snapshot. Restore recovered the saved
values, authenticated APIs and all three normal Arr forms logins. Original
container IDs, movie/series database records and all **six pre-existing media/data
file hashes** were preserved, including the local movie/TV samples. A safety copy
remained available and all four collectors produced new results. The lab's four
apps, dashboard and controller were then stopped; volumes, backups and media were
retained. Evidence: `test-results/docker-core-05cebfd84fd1/maintenance-report.json`
and `maintenance-cleanup-report.json`.

The recovery package was also deployed to the main six-app preview. Browser-reviewed
snapshots saved Plex, Seerr and the four core apps. All six encrypted archives
were decrypted, checksum checked and path/link validated in temporary private
staging without restoring main data. Dashboard configuration stayed unchanged,
all original media/data hashes matched, unrelated running containers stayed up,
and all six collectors returned fresh authenticated results after the downtime.
Evidence: `test-results/docker-plex-bc615eaf1fe6/maintenance-report.json`.

Manual snapshots are limited to the same owned installation and pinned app version.
Keep the controller data directory and `state/secrets.key`; same-disk snapshots
cannot protect against disk failure. Media is excluded and needs a separate backup.
Whole-host recovery, scheduled app snapshots/retention, off-disk destinations,
Plex/Seerr restore acceptance and safe app updates/rollback remain release work.

Regression: **357 passed, 3 skipped**, with two upstream deprecation warnings.
Both browser smoke modes, Ruff and whitespace checks pass. The portable-source
heuristic audit scanned **191 files with no findings**. No publication occurred;
the package remains an unsigned private preview. Next implement reviewed safe
updates/rollback, then continue optional-app and recipient acceptance.

## Docker recovery and Seerr request acceptance

Docker Desktop was restarted using its supported start command. The same Linux
engine/context returned, the existing apps restarted, and the main dashboard and
checksum-verified packaged controller reconnected using the existing enrollment.
All five existing integrations returned fresh data. The earlier import lab's guarded
shutdown subsequently passed; its seven containers, data and volumes were preserved.

Seerr **3.5.0** was added at local port **42464** through the packaged browser's
Add another app review/install flow. Its pinned image source revision is
`e2f24cb46079746936516c723b09820360f95113`. The existing authorized Docker Plex
credential completed Seerr's supported Plex sign-in without exposing a token or
copying a key. The exact Docker server identity and only **Test Movies**/**Test TV**
libraries were verified. No existing local Plex server was selected.

The fixed private `seerr-connection` operation now reads the bounded settings file
only for an unchanged receipt-verified owned Seerr container after account setup.
Dashboard handoff verifies the API and saves activation/credentials atomically.
The browser then reviewed and created two Seerr Arr connections, including their
existing profile names and library folders, after Seerr's connection tests. Existing
connections and profiles are preserved; a repeat preview proposed zero changes.
All six integrations reached fresh monitoring.

The original-media acceptance submitted **one movie request and one six-episode
season request to Seerr**. No direct Arr add, release grab or manual import command
was used. The local private BitTorrent source and separate seeder served only
generated colour bars and silence under known metadata stand-in names. Inert MKV
attachments met the existing TV size floor, so quality settings were unchanged.
Radarr and Sonarr automatically downloaded/imported all seven files; library hashes
matched every generated original and import history matched the torrent hashes.

Plex's supported library refresh found the movie and all six episodes in the correct
libraries with the expected metadata IDs. Seerr's supported Plex scan then marked
both requests **Completed**. That scan was triggered to bound the test instead of
waiting for its scheduled interval. The collector now preserves Seerr v3.5's
separate Completed count; it does not relabel the API's Available count.

The temporary test source was removed and its two fixture containers stopped.
The six main apps and sample files remain available. Private evidence is under
`test-results/docker-plex-bc615eaf1fe6/seerr-*-report.json` and
`test-results/docker-seerr-request-20261017/{imports-report,flow-report}.json`.
This is a local original-sample request/import/library check, not personal-provider,
LAN, imported-file playback or Windows signed-out startup certification.

The preceding private package was `Stackarr-Docker-Seerr-Preview-20261017-rc2.zip`.
All eight extracted payloads and the ZIP checksum were verified. The exact dashboard
image is `sha256:f676a71ee15e85a08e2e495cc89fe637dacd46fe925438d76bd557cb86db20da`.
The actual extracted executable passed its temporary-state frozen smoke test.
A restart of only the unchanged owned Seerr container retained its API key,
configuration and both completed requests. Dashboard settings were unchanged,
all six collectors returned new authenticated results, and connection preview
still proposed zero changes. Evidence: `seerr-final-report.json` in the main lab.

Regression: **342 passed, 3 skipped**. Both browser smoke modes, Ruff and whitespace
checks pass. The portable-source heuristic audit scanned **188 files with zero
findings**. The ZIP remains unsigned and private; no publication occurred. The
seven completed test torrents were stopped without deleting files, and the two
fixture services and their temporary source were cleaned up. Personal provider
choices still use the guided setup. The following maintenance checkpoint above
adds Docker lifecycle and app-configuration backup/restore; update rollback and
optional-app acceptance remain next.

## Simpler Arr logins and source setup

At the earlier checkpoint, private `Stackarr-Docker-Import-Preview-20261017-rc2.zip`
ran the existing five-app preview. It preserves the Plex settings, credential, fixture,
owned app identities and all four connections. Generated Sonarr, Radarr and Prowlarr
logins were privately handed to the dashboard and each normal forms login verified.
The Apps screen now offers an app selector, owner-password verification, copying and
automatic hiding. Existing or subsequently changed app logins are preserved.

A fresh extracted predecessor package completed four-app installation, generated
login setup, owner-protected reveal and the four reviewed connections. A disposable
local Torznab source was then tested/saved through the new browser form and
Prowlarr automatically shared it to both Sonarr and Radarr. Both apps found their
exact original-media fixtures. Personal provider choices were not made. The test
videos contain only generated colour bars and silence; known film/series names are
metadata stand-ins. The seeder and downloader are separate Docker containers.

The owner authorized the disposable seeder's first-run password handoff. Its test
port mapping was corrected to match the qBittorrent Web UI listener, preserving
Host-header validation and all authentication protections. No product port-mapping
change was needed. The documented setup then saved a generated durable password.

Both fixtures were found and grabbed through their Arr release APIs and the shared
Prowlarr source. qBittorrent transferred **4,332,168 movie bytes** and **1,088,379 TV
bytes** over local BitTorrent from the separate seeder. Radarr and Sonarr's normal
completed-download handling imported them into their library folders without a
manual import command. Both imported files matched the generated originals by
SHA-256, and each Arr history recorded `downloadFolderImported` for the correct
private torrent hash and download category. The disposable lab's 720p quality size
floor was relaxed because bars and silence compress heavily; production quality
settings were unchanged. This proves the bounded local transfer/import path, not
real-provider account acceptance, Plex playback of those imports or LAN operation.
The owner chose guided provider selection for personal sources.

A receipt-verified restart of only the disposable four-app batch retained the same
container identities. The transfer/import checks passed again without duplicate
grabs; all three generated Arr logins and fresh monitoring passed after restart.
The seeder's durable generated login also worked with a fresh session.

During final cleanup Docker's Linux engine endpoint became unavailable. The
ownership guard stopped before any container cleanup command, so stopping the
seven disposable containers remains pending Docker availability. The disposable
host controller was stopped separately by its exact lab root. Media, volumes and
evidence were retained. The main controller was not targeted. This later runtime
outage does not replace the completed pre-outage transfer/import evidence.


Final-package checksums and all eight payloads were verified. Its exact image is
`sha256:7af9f4fe26a90092d04679cd4ee5700ee92e7f365017dd94a1d6954211d56f5a`.
The frozen executable smoke test, both browser-smoke modes and Ruff pass.
Regression: **334 passed, 3 skipped**. The portable source audit scanned **181
files with zero findings** after shortening a synthetic test credential that the
heuristic flagged. These are private, unsigned local builds, not published releases.

Evidence is retained under ignored `test-results/docker-core-05cebfd84fd1`, including
`import-report.json`, `import-restart-report.json` and `import-cleanup-report.json`, and `docker-plex-bc615eaf1fe6/core-report.json`; the final executable smoke report is
`import-final-frozen-smoke.json`. The first existing-batch verification stopped on
an overly exact UI text selector after saving the logins. Its corrected repeat
passed and confirmed normal login access for all three Arr apps.

## Packaged Docker core apps

The live Plex preview now also runs qBittorrent, Sonarr, Radarr and Prowlarr, added
through the browser's **Add another app** flow using the new bundled controller.
Private handoff verifies the owned receipt and all four APIs, then saves the batch's
encrypted credentials and completed state atomically. The existing Plex settings,
credential, media fixture and running container were preserved during verification.
The dashboard shows five of five integrations with fresh data.

Sonarr has `/data/media/tv` and Radarr has `/data/media/movies`. Both have tested
qBittorrent download clients, using separate `sonarr` and `radarr` categories at
`/data/downloads/sonarr` and `/data/downloads/radarr`. Prowlarr has tested Sonarr and
Radarr application connections with add-only synchronization. Readback confirmed
the four connections; a repeated preview proposed zero changes. A receipt-verified
restart of only these four app containers preserved their IDs, credentials, paths
and connections, and required new authenticated collection timestamps for all five
apps. Arr web-login choices remain manual; no indexers, media requests, torrents or
downloads were added. Download/import acceptance remains open.

The new private package is `Stackarr-Docker-Core-Preview-20261017.zip`, with the same
eight-file distribution boundary and no runtime data or secrets. The actual ZIP was
extracted and all payload checksums verified. A separate fresh four-app browser
walkthrough used its packaged startup helper, executable and prebuilt image without
recipient Python. It completed installation, private handoff, four reviewed/tested
connection writes, a duplicate-free repeat preview and fresh monitoring. Its
disposable containers and controller were stopped; their data was retained.
The exact image is
`sha256:bcc1219740286da9450068d611a0b66378dfeea91ebf94cdb4ec0de7bb19755e`.

Evidence is retained under ignored `test-results`: the live lab's `core-report.json`
and `core-restart-report.json`, and `docker-core-97312db98f11/report.json` for fresh
package acceptance. The initial live browser attempt completed the connections but
stopped on an assertion; its follow-up existing-batch check and the separate fresh
walkthrough passed. The frozen executable self-test, both browser-smoke modes, Ruff
and whitespace checks passed. Regression: **324 passed, 3 skipped**. The portable
source audit scanned **171 files with zero findings**; it remains heuristic. The ZIP
is unsigned and has not been published. Windows reboot and second-device gates
remain deferred.

## Plex account and playback

The existing Docker Plex preview completed account setup on the same computer as
**Stackarr Docker Test**, with **Test Movies** and **Test TV** mapped to the isolated
media folders. Outside-home access was disabled in its setup wizard. Private
Finish connecting returned `connected`, and fresh authenticated monitoring reached
`ready`. Repeating the action returned `saved` and remained ready. Docker stayed
ready, the same owned Plex installation was preserved, and both Docker and existing
local Plex server identities remained unchanged.

The original five-second AVI sample played in the in-app browser: rendered colour
bars and progressing playback were observed, and the player returned to the test
library after completion. A replay was paused at three seconds for evidence. This
is a local browser playback check, not LAN, audio, GPU or full-length media
certification. Private reports and screenshots remain under ignored `test-results`.

The walkthrough exposed a usability gap: signing into Plex can display an existing
server's library while the Docker server is still unclaimed. Comparing the selected
server ID with the local identity endpoints distinguished them. The Docker server
now has a clear name; the setup guide includes the distinction. The completion plan
separates this passed Docker slice from the deferred Windows and second-device gates.

The earlier Plex package and regression evidence below were recorded on 16 October.

## Packaged Docker Plex preview

The owner requested Docker-only work on the existing computer because no second
Windows machine is available. Clean-Windows, signed-out reboot and second-device
playback gates remain deferred. Docker Desktop's Linux x64 engine and Compose
5.5.1 are now running; read-only Windows inventory reported virtualization available
and AutoAdminLogon disabled. No Windows startup, service, firewall or router changes
were made.

The first private package is `Stackarr-Docker-Plex-Preview-20261016-rc2.zip`. It
contains a prebuilt dashboard image, frozen Windows controller, startup helper,
readme, licenses and checksum manifest. The eight-file archive and its SHA-256
were verified. No lab database, credentials, media, enrollment or certificate is
included. The package is unsigned and identifies its source as `e169c71` plus
working-tree changes; this is local evidence, not a hosted release claim.

The extracted ZIP passed a fresh real browser walkthrough using its own controller
executable and prebuilt image. Its startup helper required no recipient Python or
source build. The test selected an explicit isolated media folder, ran host Docker
checks through the private connection, reviewed and installed only Plex, verified
the `/web` link, reloaded saved progress and checked unfinished-account guidance.
Plex's media mount was read-only, the sentinel remained unchanged, and unrelated
running container identities were preserved. The exact tested dashboard image was
`sha256:d95401585b9b8066855a201b1aea9cfed4690ab2114e0334216099315fae7a69`.

A separate live lab also reconnected after replacing its source controller with
the frozen executable, retaining the same Plex installation and enrollment. The
actual packaged executable passed its temporary-state smoke test and read-only
Docker check outside the source directory. Package testing found and fixed
console-dependent controller logging and reliance on PowerShell module discovery.
The normal package folder dialog is implemented; automated acceptance supplied the
root explicitly, so native dialog usability still needs a human check.

The Docker dashboard now has a private Plex Finish connecting path. It binds the
handoff to a completed deployment ID, reviewed port and dashboard settings revision,
verifies owned container/configuration identity on the host, tests the API from
the dashboard and encrypts the credential. Repeated checks preserve saved details;
newer settings and failed credentials are not replaced. Synthetic tests cover a
successful claimed credential and races. On 16 October the live server was still
unclaimed; account completion, monitoring and local sample playback subsequently
passed on 17 October as recorded above. The original five-second AVI fixture was
also decoded by Plex's transcoder before the browser playback check.

Final local regression: **311 passed, 3 skipped**. Both launcher-mode and Docker-mode
browser smoke checks passed, including desktop/tablet/phone layouts. Ruff passed.
The skips remain Windows filesystem-link cases. The package and image have not
been published.

Next work: simplify Arr logins and first-run Plex identification, finish an
authorized download/import fixture and the private Seerr handoff; handle
occupied ports and connection recovery for older or uncertain-response installations;
then continue multi-app
configuration and maintenance gates. See [DOCKER-PLEX-PREVIEW.md](DOCKER-PLEX-PREVIEW.md).

## Installation recovery

The Docker dashboard now saves the last authenticated controller operation
snapshot. If the host controller disconnects or the dashboard restarts, the
wizard shows that snapshot as last known progress instead of implying that no
apps were installed. It disables Resume while disconnected, distinguishes a
busy controller from an unavailable one, and polls for reconnection. An
uncertain install response consumes its browser approval and refreshes status
before offering another action; it cannot submit the same approval twice.

An isolated live Docker dashboard on port 28100 exercised two recovery paths.
First, a deliberately failed Seerr operation was resumed after the API client
closed; it reached `needs-setup` and returned HTTP 200. Next, Prowlarr was
interrupted while the controller was paused immediately before Docker pull.
The controller and dashboard were restarted separately. The dashboard retained
the last running state while disconnected, then displayed the interrupted
operation and resumed it to `needs-setup`. Prowlarr returned HTTP 200. Seerr's
container ID and saved settings remained unchanged. The test-owned containers
were stopped, and their volumes and operation receipts retained. The original
preview on port 28000 and unrelated `open-easyx` remained healthy. The
injected interruption was before pull, so recovery from a partially downloaded
image layer remains unverified. See [INSTALLATION-CONTROLLER.md](INSTALLATION-CONTROLLER.md).

## Docker wizard to host installation

The Docker dashboard now sends the saved wizard's scoped port checks, review,
install, status and resume through the enrolled Windows controller. A host
approval reference stays on the dashboard server; the owner session receives
a separate single-use token bound to the current draft revision. Completed
operations show local Open links. Connection loss shows an unavailable state.
Host folder browsing now uses approved controller roots and stores a root
reference for host-side review. Guided root sharing and a native host chooser
remain open; the source controller currently requires approved roots in its
environment.

The next-app path now recognizes completed host operations in the Docker wizard
and offers **Add another app**. It starts a fresh app selection and keeps
existing app cards unavailable for a second installation request. In an
isolated live host-controller test, Seerr stayed on the same container ID and
retained its saved connection settings while a later Prowlarr-only batch
completed. Both returned HTTP 200 on their selected local ports. The two
test-owned app containers were stopped afterward; volumes and receipts were
preserved. The recovery tests above now cover client closure and controller
and dashboard restarts in a separate isolated batch.

An isolated dashboard on port 28100 installed Seerr through the real wizard
and host worker into a new Compose project. The operation reached `needs-setup`,
Seerr returned HTTP 200 on port 28007, and the dashboard supplied its Open link.
The original preview on port 28000 and unrelated `open-easyx` stayed healthy.
This does not verify Seerr account setup, Stackarr monitoring, media sharing or
the packaged installer. A separate Uptime Kuma attempt failed at container
startup with `exec format error` in the pinned image; its failed operation and
volume are retained for diagnosis. See [INSTALLATION-CONTROLLER.md](INSTALLATION-CONTROLLER.md).

## Private controller connection slice

The Windows source launcher now provisions a stable private enrollment, starts a
loopback TLS controller and probes it from the Docker dashboard. The container
receives a read-only shared key and pinned certificate, not the host TLS private
key or Docker socket. The deployment API can report connected/unavailable
controller status and reconnects on later requests. The wizard bridge described
above adds reviewed installation through that connection.

Local verification: 276 tests passed, three Windows filesystem-link tests
skipped; Ruff passed. A temporary controller on `127.0.0.1:28010` accepted a
real pinned-TLS test. The verified existing preview container reached that
loopback listener through `host.docker.internal` in a read-only socket check.
A bounded disposable container on the same network completed a signed TLS status
request and was removed. A newly built disposable dashboard on port 28100 used
tmpfs state and reported `connected`, `unavailable` and `connected` through its
authenticated API across a controller restart. It was removed; the preview
image was not rebuilt, and no app was installed through the Docker wizard. The
packaged one-download launcher, automatic recovery after host process failure,
and key renewal/revocation
remain open.

## Usability correction following the first human walkthrough

The first walkthrough failed novice usability acceptance. Do not call the Docker
preview an end-to-end installer. The wizard now places a single port selection
section beneath the app cards (app defaults, Stackarr range, custom editable
table), reduces storage to a folder choice and a small summary, and removes the
reviewed-JSON download from onboarding. It explicitly distinguishes saved choices
from installed apps. Native launcher checks test real host ports; a container-only
dashboard reports those checks as unavailable.

Folder browsing is restricted to administrator-declared media mounts. Users can
choose a folder by browsing and explicitly create missing movies/TV/download
subfolders; existing files are retained. The display and creation use the same
app-specific layout. This is not yet arbitrary Windows drive selection from a
Docker browser: the host connection and novice mount setup remain unfinished.

Tautulli, Uptime Kuma and Cleanuparr now have pinned x64 installation definitions
and install/connect choices. Registry metadata was checked against official
distribution locations. Their runtime first-run behavior is not yet validated;
no cleanup automation or existing download client is connected automatically.
References: [Tautulli installation](https://github.com/Tautulli/Tautulli/wiki/Installation),
[Cleanuparr installation](https://cleanuparr.github.io/docs/installation/detailed/),
[Uptime Kuma distribution](https://hub.docker.com/r/louislam/uptime-kuma).

Next acceptance gates:

- A new user starts Docker Stackarr, chooses a disk/folder without editing paths,
  and gets accurate host free-space, write-access and port checks.
- The review's primary action starts a scoped, resumable install through a
  separate controller. No raw Docker socket is exposed to the dashboard.
- All nine app installation paths finish with clear account/connection steps;
  complete their isolated runtime tests before claiming support is finished.
- Real progress ends in a working dashboard and an explicit next action, not a
  downloaded file. Retest restart, failed download, unavailable port and storage
  permission failure with no modifications to an existing stack.

Verified locally for this correction: 231 tests passed, three filesystem-link
tests skipped on this Windows account; the Docker-mode automated browser walk
covered custom port conflicts, persistence, folder selection and creation,
mobile layout, absence of the JSON download, and mixed existing/new choices.

The updated isolated preview was built and its saved review screen verified in a
fresh browser tab. It retained the same state volume and shares only a dedicated
test-media folder. A subsequent `tools.install_wizard_check --companions` run
failed during image download: Docker Desktop reported its WSL/Linux engine was
unavailable. The preview then failed its health request. No Docker/WSL restart was
performed because it would affect unrelated containers. Companion runtime
acceptance remains unverified; the saved failed operation must not be counted as
a successful install. Recovery needs the user's approval for a Docker restart.

The Docker first-run token prompt has now been removed. Start Stackarr opens an
owner-authorized password page automatically; direct unclaimed visits show plain
startup instructions. Local verification: 228 tests passed, two platform skips,
and the Docker-mode browser walkthrough passed. The live disposable dashboard at
port 28787 was updated and the password-only page visually verified. Its existing
data volume, all six media containers, unrelated container and media sentinel were
preserved. This does not complete container-based app installation.

The Docker-first installer is now exercised through the browser on Windows Docker
Desktop and a fresh Linux CI runner. This is substantial working progress, not a
claim that the entire public-release roadmap is complete.

| User journey | Implemented and checked | Still required |
| --- | --- | --- |
| One Windows download | Launcher packaging, owner pairing, local browser, bundled installer modules/image lock | Signing, fresh Windows host and native dialog acceptance |
| New app installation | Reviewed pinned images, private project/network/volumes, available-port suggestions, bounded download retries, saved jobs, explicit resume and reviewed start/stop | Docker prerequisite installation, owned-app upgrade/repair/uninstall UI |
| Media folders | Explicitly reviewed missing folders, existing-file preservation, Sonarr/Radarr root-folder setup | NAS permission matrix, full import/hardlink/playback acceptance |
| App credentials | Owned-container identity checks, encrypted Arr/qBittorrent handoff, guided private Plex/Seerr connection retrieval after account setup | Real owner-account acceptance for Plex/Seerr, OS-backed encryption key |
| App connections | Browser review of four real Arr/Prowlarr/qBittorrent writes, upstream tests, duplicate preservation | Multiple installation batches and cross-host reachability guidance |
| Existing apps | Review and save chosen addresses without replacing existing settings or importing secrets | Broader discovery and authenticated identity/version checks |
| Usability | Local-password explanation and reveal option, sign-in recovery, advanced ports collapsed, optional wiring hidden, guided next steps and folder chooser | Native dialog human check, complete accessibility and novice walkthroughs |
| Operations | Read monitoring, container drift checks, status freshness, local settings backups and notification delivery | App-native backups/restore, LAN HTTPS, automatic startup, rollback and safe updates |

Beginner setup revision (`74bb87a`; connection behavior tested at `05bad1c`):

- Normal fresh installation has no API-key/token copying between Stackarr and its
  installed apps. Plex/Seerr account sign-in remains an upstream human step.
- **Finish connecting** is explicit, authenticated and limited to exact verified
  owned container IDs and fixed bounded settings files. API checks precede encrypted
  storage. Existing secrets and newer settings are preserved; disabled apps are skipped.
- Connection setup blocks competing installs and start/stop actions. Failures remain
  visible, never return private file contents, and do not claim the app is ready.
- Password setup explains the local account, offers Show password and recovers to
  sign-in after a temporary login failure. No cloud registration is introduced.
- Port overrides are behind Advanced installation options; unrelated download wiring
  is hidden for a Plex-only setup. Progress uses plain-language labels.
- Local validation: **225 passed, 2 skipped**, source audit **140 files / no findings**,
  and desktop/tablet/phone browser checks passed. The final hosted results follow.

Validation evidence:

- **Current verified application revision: `74bb87a`.** All **227 tests passed on
  Linux and Windows**. [CI](https://github.com/FrankieJLyons/MyMediaStack/actions/runs/37410377895),
  [six-app Docker tests at matching application behavior `05bad1c`](https://github.com/FrankieJLyons/MyMediaStack/actions/runs/37410164037)
  and [Windows package](https://github.com/FrankieJLyons/MyMediaStack/actions/runs/37410377863)
  passed. The only application change after the Docker run adds a packaged-module
  self-test assertion. The actual downloaded executable's checksum/build revision
  matched, and its temporary-data self-test passed locally, including the new
  connection module. See LOCAL-LAUNCHER.md for the checksum.
- The real six-app test exercised **Finish connecting** on unclaimed Plex and
  unfinished Seerr, confirmed actionable setup guidance, and saved no account
  secrets. Successful account credential retrieval and rejection/race cases use
  synthetic tests until the test owner completes upstream sign-in.
- The real browser test cancelled a Seerr stop review, then approved stop/start.
  It verified the same container was reused, the other five apps kept running,
  settings remained identical and the synthetic media sentinel was preserved.
  Stale inspection results are cleared after an approved action.
- The clean source boundary scan covered **140 files with no heuristic findings**.
  Dependency audit found no known vulnerabilities in the pinned Python requirements.
  Neither result certifies all native libraries, upstream images or historical Git data.

- Earlier local suite at `a0b5064`: **211 passed, 2 skipped**. Both skips are symbolic-link tests
  unavailable to this Windows account; they remain part of hosted validation.
- Connect-only choices skip Docker/host prerequisites without probing the computer.
  Missing optional services are not reported as installation failures.
- The wizard can suggest unused ports without contacting an existing service.
  It rechecks availability at installation review; suggestions are not reservations.
- Only known temporary image-download failures get bounded retries. App configuration
  writes still require explicit installation resume after failure.
- Apps now checks installed containers for changed ownership, images, mounts, ports,
  networks and privileges without restarting, repairing or deleting anything.
- Reviewed start/stop uses the exact owned container ID, rejects changed receipts,
  preserves volumes/media, records action results and requires a new review after
  interruption. It never recreates containers or automatically replays actions.
- Password checks are serialized and return a recoverable message under memory
  pressure. Account creation remains retryable and failed login creates no session.

- The expanded six-app browser test exposed a fresh Plex startup failure. Its
  previous image had an empty server executable. Plex's `public`/`beta` images also
  fetch server binaries at startup, so they are unsuitable as immutable runtime
  pins. The installer now uses the prepackaged x64 `1.43.4.10903-e5521bd8c` image by
  registry digest. The six-app test passes, including Plex API readiness, read-only
  media access and a deliberately dropped progress response. Browser progress now
  reconnects automatically after a transient read failure.
- Docker restarted during the failing local test. The cause was not established.
  The failed fixture was stopped without deleting volumes. The older disposable
  lab was restored using its original containers and verified receipt/sentinel;
  no image replacement or media migration was performed there. This incident is
  why container isolation is not a guarantee against shared Docker-host failures.

- Application revision `6b33ef0` passed all **178 tests on Linux and Windows**.
  [CI](https://github.com/FrankieJLyons/MyMediaStack/actions/runs/37390056773),
  [Docker acceptance](https://github.com/FrankieJLyons/MyMediaStack/actions/runs/37390056306)
  and [Windows build](https://github.com/FrankieJLyons/MyMediaStack/actions/runs/37390058763)
  all passed. The downloaded executable checksum matched, and its packaged-runtime
  self-test passed locally using temporary state. It remains unsigned.

- Local fresh Docker browser tests passed for Seerr, Sonarr, Radarr, Prowlarr and
  qBittorrent with real encrypted credential handoff and four reviewed connections.
- Library root folders and password-protected generated-login access passed against
  fresh real containers. Repeat connection review offered no duplicate writes.
- Desktop, tablet and phone synthetic browser checks pass, including draft resume,
  mixed existing/new app choices, Settings, stale/partial data and unsaved changes.
- Hosted five-app installation passed at `4f93ef5` in
  [Docker lab run 37388763493](https://github.com/FrankieJLyons/MyMediaStack/actions/runs/37388763493).
  Later commits require their own build/test results.
- Tests preserve the original review lab and unrelated containers. Successful wizard
  fixtures stop only their newly created project; volumes remain preserved.

Next release work, in order:

| Work | Why it still blocks the full promise |
| --- | --- |
| Plex/Seerr account setup, import and playback acceptance | Container/API readiness does not prove a household can watch or request media |
| Clean Windows setup, Docker prerequisite flow and native dialog check | A bundled executable is not yet proof that a novice can start from an empty machine |
| LAN HTTPS, second-device access and reboot/startup | Current safe defaults expose app ports only on the installation computer |
| Owned app upgrade, rollback, repair and removal UI | Reviewed start/stop reuses existing containers; it does not update images or restore app databases |
| Consistent application backups and verified restore | Current backups contain Stackarr settings, not app databases or credentials |
| Signing, complete native/component inventory and public clean-export approval | Current downloads are unsigned private previews, not a public release |

NAS agents, offsite backup targets, Storage Guard and broader platforms remain
later roadmap work. The open issues are intentionally not closed on the strength
of these implementation slices.

Human acceptance before calling this ready for a household:

- [ ] Launch the exact built executable on a disposable Windows computer without Python.
- [ ] Select a folder through the native dialog, cancel once, then complete selection.
- [ ] Choose only desired apps and verify skipped integrations stay hidden.
- [ ] Review ports/folders, install, close/reopen Stackarr and verify saved progress.
- [ ] Check an installed test app, cancel a stop review, then stop/start it and verify its settings/media persist.
- [ ] Complete Plex claim and Seerr setup using the test owner's accounts; return to **Finish connecting** and verify connection succeeds without copying secrets.
- [ ] Confirm an unfinished account shows a clear next step, a disabled app disappears, and repeated connection checks preserve saved details.
- [ ] Explain the local Stackarr password to a new user; verify the show-password option and successful sign-in retry without recreating the account.
- [ ] Import and play an authorized sample and verify queue/download/library states.
- [ ] Test a second LAN device over the intended HTTPS setup.
- [ ] Reboot, restore a backup and verify preservation before recommending regular use.

The source repository remains private. Public distribution requires the clean
export boundary and explicit publication approval. The working media stack is not
a test environment. The historical checkpoint below records the previous scope;
the table above supersedes its implementation status.

---

# Previous delivery checkpoint — 3 October 2026

## Docker-first follow-up

The owner requested an isolated Docker setup before VM work. Docker Desktop is now
available locally; the personal media stack remains out of scope. Runtime evidence
must use a separate Compose project, network, volumes, ports and synthetic media.

The setup draft now supports mixed install/connect choices and configurable new-app
ports. Existing connections are explicitly unverified and independently managed;
they never enter the generated installation services or media mounts. Credentials
still follow separately in Settings. Legacy drafts retain install intent. Unit and
browser checks cover saving, resuming and reviewing existing Plex plus new Seerr.

The isolated Docker Desktop lab now runs six real app images and Stackarr on
separate loopback ports and fresh volumes. Actual API checks exposed and fixed
qBittorrent custom-port/login-response and Arr category-schema bugs. Four connection
writes passed upstream validation, repeated previews propose no duplicates, and
credentials/connections survive container restart. Compose down/up preserved data
and the media sentinel. These are maintainer-driven fixtures, not a completed
consumer installer. See [DOCKER-LAB.md](DOCKER-LAB.md) for evidence and remaining
Plex/Seerr, playback, import, HTTPS and Windows reboot checks.

The goal remains one Windows download that installs selected media apps on a new
machine and guides the owner to a working private LAN setup. The current executable
is a **setup and management preview**, not that finished installer.

## Available to review

- Local launcher with matching-code approval and owner sign-in.
- Saved setup drafts, feature choices, folder layout preview, local prerequisite
  checks and explicit default-port discovery hints.
- Optional app monitoring including Seerr request counts. Missing apps stay hidden;
  unrelated failures do not erase working counts, and stale data is labeled.
- Session-bound, expiring connection previews with single-use apply.
- Encrypted credentials and webhook destinations; schema upgrades and import drafts.
- Persistent connection checks and audit records; Health operation history.
- Configuration backups with checksums, preview-before-save restore and a persistent
  daily schedule. These are not third-party app/database backups.
- Persistent webhook deliveries, bounded retries and visible delivery results.
- Unsaved-change protection and contextual help.

## Issue status

These are implemented slices, not claims that the full issues are closed.

| Issues | Working foundation | Remaining acceptance work |
| --- | --- | --- |
| #1–#2 | Export boundary, license, schema migrations, encrypted secrets | Public-export review, field metadata, OS-backed key protection |
| #3–#4 | Durable read jobs, declared capabilities and guarded writes | Installer reconciliation, full adapter fault/version matrix |
| #5–#6 | Hosted Windows build, Python inventory, browser and executable smoke gates | Signing, complete native inventory, immutable images, fresh-host/reboot lab |
| #7–#10 | Saved wizard, storage map, local hints, deployment receipts | Mixed connect/install wizard, folder picker, scoped host executor, deployment networking |
| #11–#16 | Read collectors, Seerr preview, reviewed Arr/Prowlarr wiring | Owned-app installation, first-run authentication and credential exchange; real-app verification |
| #17–#18 | Responsive views, unsaved protection, scoped health and counts | Final navigation, full accessibility audit, broader fault taxonomy |
| #19–#20 | Local settings recovery and persistent webhook delivery | App-native restore tests, filters and provider-specific integrations |
| #21–#22 | Contextual help, synthetic browser CI and documented limits | Novice walkthroughs, screen-reader/contrast and real-container compatibility |
| #23–#26 | Product decisions and safety boundaries documented | NAS agent, offsite storage, Storage Guard actions, scoped Docker proxy and HTTPS/update workflows |

## Evidence and boundaries

Unit and contract tests run locally and in GitHub CI. Browser checks use synthetic
data at desktop, tablet and phone sizes. The hosted Windows job builds the executable
and exercises its temporary-data self-test before uploading it. See each workflow
run for the tested commit; an older artifact does not include newer source changes.
The artifact includes its build revision, checksums and dependency inventory.

No personal media server is a test environment. No software was installed on the
development computer for this work. Real media-app installation, Plex playback/GPU
behavior, NAS shares, LAN trust, upgrade/rollback and startup before Windows sign-in
remain unverified. The private repository and historical deployment snapshot must
not be published; the public project needs the reviewed clean export.

## Next implementation order

1. Complete the wizard's per-app connect/install choices and credential handoff model.
2. Choose the supported Windows runtime using the disposable-host lab; keep the
   launcher usable when that runtime is absent.
3. Implement the scoped host executor and reviewed download/install jobs, starting
   with Plex, Sonarr, Radarr, Prowlarr and qBittorrent.
4. Validate a brand-new-machine path end to end, then LAN access, backup recovery and
   reboot before sign-in. Expand to optional apps and NAS only behind equivalent gates.

Reviewing the executable now is useful for the setup/dashboard experience. It must
not be presented to a new user as a completed automatic media-stack installer.
