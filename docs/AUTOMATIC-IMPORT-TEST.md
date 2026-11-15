# Automatic request-to-playback acceptance — 20 October 2026

The isolated real-account movie and TV test now passes without post-import manual
scans. The main installation remains unchanged. This closes the automatic
discovery failure recorded for the R6 preview; it does not certify the older
nine-app installation's replacement or clean-Windows/device acceptance.

## What changed

Plex acknowledged native Sonarr/Radarr partial refreshes without discovering new
title directories. Stackarr now checks successful import history every 15 seconds
after reviewed connection setup. A new import starts a root scan of only the
matching movie or TV sections. Imports are combined, with at most one scan per
section per minute. No scans run merely because the dashboard is idle or reopens.
This deliberately uses a whole matching section rather than the unreliable
partial directory refresh, so very large libraries still need a scale test.

The reviewed binding includes the Plex machine, section IDs, library paths, Arr
roots, app addresses and credential fingerprints. Changed destinations or folders
stop automatic writes until reviewed again. Sections with unrelated extra folders
are excluded. Existing native notifications and custom Seerr schedules are kept.
Seerr's own scheduled checks update availability; Stackarr does not force a title
to Available. Its Plex handoff still verifies the actual library item.

Durable import checkpoints advance only after Plex accepts the scan. Failed scans
retry, including after restart. A brief storage failure cannot permanently stop
the worker. Unconfigured startup/review leaves update fingerprints unchanged;
configured discovery bindings are protected during updates while routine cursor
progress is allowed. Fresh watching setup includes this connection automatically.
Stackarr must remain running; the browser window can close.

Regression runs also exposed intermittent native Windows access/sharing locks
during atomic update-journal replacement. Those specific errors now retry for at
most 0.75 seconds. Persistent denial still fails with the previous journal intact.

## Live test evidence

The retained, already claimed disposable server was reused, so no additional Plex
account association was needed. Only its generated sample requests, downloads and
two new libraries were reset. New empty Movies/TV libraries were prepared through
the product helper before requests. The earlier deleted server/libraries were
never restarted or recreated. This test reused a real signed-in Plex account;
fresh signed-out credential entry was not repeated.

1. Enabled discovery through Stackarr's actual Preview app connections → Apply
   reviewed changes flow.
2. Requested the movie catalog stand-in at **1080p** and TV **season one at 720p**
   through Stackarr Home. Native Seerr/Arr profile assignments agree.
3. The real local source, Prowlarr, downloader and Arr apps transferred/imported
   seven original generated files (**13,241,396 bytes**). Every SHA-256 matches;
   imports are hardlinked to downloads. No personal source provider was tested.
4. Stackarr automatically initiated one movie and one TV root scan. Seerr's own
   scheduled job fulfilled both requests; the whole TV show remains partially
   available because only season one was requested. That season is Available.
   No manual Plex scan or Seerr scan/availability override was used after import.
5. Open in Plex played the generated movie at **1920×1080**, advancing from
   **0.007 to 34.291 seconds**, and episode S1E1 at **1280×720**, advancing from
   **2.650 to 72.637 seconds**. Both had ready video and no video error. Native
   Plex sessions matched the imported movie/episode. Back returned to Stackarr.
6. Restarting the dashboard retained its checkpoints and available title links,
   without replaying scans for those imports.

The media are original animation/tone samples with catalog metadata stand-ins,
not copies of those named productions. Small-file size allowances and disabled
public peer discovery are confined to the disposable test.

Private evidence is retained under `test-results/automatic-import-20261020/`:
preparation guards, native profiles/import checks, worker audits, browser video
measurements, native sessions, screenshots, package checks and cleanup receipts.
See [PROGRESS.md](PROGRESS.md) for the final package and regression counts.

## Remaining replacement work

Run the [existing-stack replacement rehearsal](STACK-REPLACEMENT-TEST.md) with the
older nine-app alpha, including preserved Plex identity/watched state, accounts,
sources, profiles, requests, schedules and a verified rollback. The earlier
six-app preview update/rollback test is narrower evidence. Second-device playback,
clean Windows and signed-out startup remain separate acceptance gates.
