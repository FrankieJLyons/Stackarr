# Stackarr update and rollback

The Windows Docker preview updates the Stackarr dashboard and its private Windows
controller together. Open **Settings → Stackarr updates & rollback**. Docker must
be running; your media apps continue running during Stackarr maintenance.

For removal with settings kept and reviewed reinstall, see
[Remove and reinstall Stackarr](SELF-REMOVAL.md). A completed removal is kept
offline until you approve the local reinstall review.
For a stopped, missing or unhealthy dashboard, use
[Stackarr runtime repair](RUNTIME-REPAIR.md). It keeps the same release and account,
checks storage before downtime and retains recovery data if a write fails.

1. Download a complete compatible Stackarr preview ZIP from the trusted release
   owner. These private packages are unsigned; checksums detect changed contents
   but do not establish who published a package.
2. Choose **Choose downloaded update…** and select the ZIP in the Windows dialog on
   the installation computer. No extraction, terminal commands or credential
   copying are required. Cancellation preserves the current installation.
3. Choose **Review Stackarr update**, read the review, then **Update Stackarr**.
   The dashboard reconnects automatically and shows the maintenance result.
4. To return to the previous compatible release, choose **Review Stackarr rollback**
   in maintenance history, then approve **Roll back Stackarr**.

Each update retains an encrypted safety checkpoint, the earlier complete package
and dashboard volume. An independent copy of the working controller supervises
the update. It checks the candidate controller and Docker dashboard against
separate database copies, with background app jobs disabled. Release identity,
controller enrollment, account, encryption keys, saved settings and credential
fingerprints must match before promotion. A healthy HTTP response alone is not
enough. The entire Stackarr configuration volume is copied, including its local
configuration backup files. Media-app containers and their configuration volumes
are never targets of Stackarr self-update.

Rollback restores the previous Stackarr preferences and release. It retains the
current owner password and browser sessions, and first takes a checkpoint of the
current state. Changes to app connections, credentials or installation ownership
after the update block an older checkpoint from overwriting them. An incompatible
state schema also blocks the update. Major migrations need a separate upgrade
path; replacing an image alone cannot undo a database migration.

If checks fail, Stackarr automatically returns to the previous release, database
and original dashboard volume. If the computer or maintenance worker stops during
the update, restore Docker/storage availability and reopen **Start Stackarr.cmd**
from a package with this recovery feature. Startup follows the saved active release
and recovers pending maintenance before opening the dashboard. Reopening an older
recovery-capable package does not silently downgrade a completed update. Very old
preview launchers without this feature must not be used for recovery.

Keep the entire Stackarr state directory and a recovery-capable downloaded package.
The state directory contains staged releases, controller enrollment, encrypted
checkpoints and their private recovery keys. Do not share it or remove its contents
to fix an update. Earlier releases and safety checkpoints currently have no
automatic retention policy; reserve disk space for both the old and new packages,
the database copies and configuration-volume snapshots. Self-update checkpoints
are local recovery copies. [Whole-host recovery](HOST-RECOVERY.md) and a separate
media backup are still needed for loss of the host disk.

The packaged Docker acceptance uses only disposable installations with original
local samples. It covers successful update, reviewed rollback, a candidate that
writes a wrong database while reporting healthy, and fresh-process recovery after
the worker is killed during candidate checks. See [PROGRESS.md](PROGRESS.md) for
the dated results and [TESTING.md](TESTING.md) for the maintainer harness. Native
file-dialog and novice walkthroughs, signed distribution and replacement-Windows
certification remain release gates.
