# Replace an existing setup without starting over

20 October evidence: the separate six-app preview passed a real UI update,
rollback and forward update with app identities, settings, credentials, media
and browser session preserved. The older main nine-app alpha is still untouched
and its exact cutover rehearsal remains pending. The follow-up automatic
movie/TV request-to-playback test now passes without manual scans using generated
samples and a real Plex account; see [AUTOMATIC-IMPORT-TEST.md](AUTOMATIC-IMPORT-TEST.md).
Use the replacement matrix below before approving a main cutover.

The next acceptance phase must prove a reversible replacement before touching the
owner's current installation. Current owned-app repair, compatible image updates,
Stackarr self-update and host recovery are useful foundations; connecting an
external app does not currently transfer ownership of its containers or settings.

## Preferred experience

Offer **Use my existing setup** alongside a fresh installation. Start with a
read-only inventory and a plain summary: apps found, accounts and libraries kept,
quality profiles and sources kept, media locations, proposed changes and any
incompatibilities. Never treat a connected app as an empty new installation.

For the current Stackarr alpha, first prove **Update Stackarr, keep my apps**.
The dashboard/controller can be replaced while the nine working media and
monitoring app containers remain in place. Preserve their receipts, logins,
enrollment, settings and media. App image upgrades are separate reviewed changes,
with a stated benefit and their own rollback checkpoint. A new dashboard alone
must not silently replace a quality profile, content source, library or schedule.

External/unmanaged apps need a separate import operation: copy supported
configuration into new isolated volumes, validate copies, then review a controlled
cutover. Do not mount the same writable databases into two running app instances.
Do not replace a claimed Plex identity with a new server identity. Never make the
user rebuild a library or lose watched state just to gain the new Home screen.

## Disposable acceptance test, after real first-watch acceptance

1. Build a separate older-release stack with generated media, distinct logins,
   customized sources, download categories, movie/TV profiles, pending requests,
   watched state and companion settings. Record identities, versions, database
   integrity, configuration/credential fingerprints and media hashes. No main
   configuration or media mounts may be writable.
2. Use the packaged **Choose downloaded update → Review Stackarr update** path
   with the new preview. Verify the account/session, app ownership, nine unchanged
   app containers, sources, profiles, requests, schedules and media. Sign in to
   Plex normally and play the same generated movie/episode from Home.
3. Roll back through the packaged review. Verify the older dashboard works with
   the same apps and media. Update forward again and reopen from the older
   launcher: it must follow the saved active release, never silently downgrade.
4. Update one supported app image at a time. Verify its real application data and
   cross-app links, then perform a real rollback. Include stopped apps, in-flight
   downloads, occupied ports, failed candidate health checks and interrupted
   workers. Preserve before-change snapshots and confirm recovery after restart.
5. For an external-app import prototype, use a second wholly disposable source
   stack. Start candidates on different ports with background work paused and
   copied data. Verify identities/settings before cutover. Roll back by restoring
   the original source running state. Reject missing/shared volumes, incompatible
   schemas, unexpected mounts, changed inputs and insufficient backup space.
6. Remove all test containers and unused test networks afterward. Retain labelled
   recovery data and generated samples; verify the main preservation baseline.

## Cutover gate for the owner's current stack

Do not claim replacement readiness from an HTTP health check or fixture test.
Require the real first-watch journey and the disposable forward/rollback matrix
above, with a concrete package/version compatibility report. Before any actual
cutover, prepare a verified configuration/recovery backup and a separately kept
recovery key, check available disk space, show the exact downtime and changes,
and present a one-action return to the previous working release. The owner has
not authorized changing or stopping the main installation during these tests.

Success means the new experience preserves the current setup and adds useful
discovery, quality choice and request tracking. Any app/configuration improvement
must be shown and tested; resetting working preferences is not an improvement.
