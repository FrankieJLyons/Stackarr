# Whole-host recovery in the Docker preview

This recovers the Stackarr dashboard account and settings, encrypted credentials,
generated app logins, controller receipts and the configuration volumes of every
owned app. It creates new containers using the original immutable images. It is a
configuration recovery, not a Windows disk image. Media and downloads are excluded.

## Prepare before a loss

1. Open **Backups → Prepare whole-host recovery**. Review the app list and approve
   **Create recovery file**. Each running app stops briefly for a consistent
   configuration snapshot, then returns to its previous running state.
2. Maintenance results show the saved `.stackarr-recovery` file. If you have
   configured a separate backup disk, Stackarr verifies a copy there too. Otherwise
   copy the file to storage that survives losing this computer.
3. Save **Download recovery key**, using your Stackarr password, in a separate
   private location. Keep the complete Stackarr ZIP too. The recovery file includes
   credentials and account databases, encrypted with this key; keep both private.
4. Back up media separately. Refresh the host recovery file after changing accounts,
   app settings or installed apps. Existing nightly app snapshots continue on their
   own schedule; they do **not** automatically refresh this complete host file.

A host file is committed only after all selected app archives and both SQLite
checkpoints verify. A failed or forced app shutdown cancels the backup rather than
claiming a consistent snapshot. Media is never mounted by a backup helper.

## Recover

1. Start Docker Desktop with Linux containers. Unpack the complete recovery-capable
   Stackarr package and open **Recover Stackarr.cmd**.
2. Choose the encrypted recovery file, its separately saved key and an empty folder
   for new Stackarr state. Choose the existing media folder corresponding to each
   saved location. Media may be on a different host path; apps still see `/data`.
3. Review the apps and destination, then approve recovery. Original app ports must
   be free so saved app-to-app addresses remain valid. Available dashboard and
   private-controller ports are chosen automatically. Existing app containers,
   configuration volumes or matching networks block recovery; nothing is adopted.
4. The recovered dashboard opens. Sign in with your saved Stackarr password. Saved
   app logins and credentials are retained. Browser sessions and setup invitations
   are revoked, and a new private controller enrollment is generated.
5. Review app health/account setup, media locations and backup storage. App backup
   schedules are paused until you review and enable them. Historical update and
   backup inventories that cannot be fulfilled on the new host are cleared;
   previous backup files on your backup disk are preserved.

Recovery validates the key, authenticated stream, complete inventory, checksums,
configuration tar paths and fixed catalog Compose recipes before creating Docker
resources. It restores configuration only into new, labelled, unshared volumes.
It never extracts an archive onto media or downloads. Images may download again;
internet access or a local cache of the original images is required.

If extraction fails, only the newly created recovery containers are stopped; their
volumes and checkpoint remain. **Resume a saved recovery** opens the review saved
beside the state folder. Retry checks the same container IDs, ownership, image,
mounts and volume consumers before restoring again. Failures before the new
container inventory is committed, or externally changed recovery resources, may
need manual inspection rather than automatic retry. A completed recovery cannot
be replayed over its running installation.

## Acceptance boundary

The acceptance harness creates its own nine-app Docker lab and copied original
sample media. It removes only that lab's generated volumes, makes its original
host state unavailable, injects an extraction failure after a real volume write,
then resumes recovery in a fresh packaged executable. It checks account access,
core app settings and generated logins, Kuma monitoring, nine independent volume
fixtures, media hashes, and preservation of the main installation's settings,
credentials, running container IDs and media hashes.

Plex, Seerr and Tautulli use first-run fixture configurations in that original
nine-app recovery lab. The claimed-account follow-up below now covers their
account, library and pending-request recovery.
Cleanuparr uses generated authentication, dry-run and disabled automation. The
native recovery-dialog walkthrough and recovery onto a replacement Windows host
remain open. The automated test runs on the existing Windows host with isolated
Docker resources, without reboots, firewall changes or personal-media operations.

Developer-only packaged entry points use host-local request/review JSON files:
`--host-recovery-review REQUEST --recovery-report NEW_REVIEW`, then
`--host-recovery-apply REVIEW --recovery-report NEW_RESULT`. These are not browser
upload endpoints and do not place key contents in command-line arguments. The
normal recipient uses the local recovery wizard.

## Claimed-account follow-up — 18 October 2026

The separate `test-results/docker-claimed-host-recovery-20261018` lab passes
whole-host reconstruction with a claimed Plex server, Seerr's real Plex owner,
Tautulli's generated web account and authenticated Plex connection, and Sonarr/
Radarr dependencies. It uses the extracted
`Stackarr-Docker-Seerr-Plex-Maintenance-Preview-20261018-r2` package.
No product change or main-installation upgrade was required.

Only the earlier disposable account labs supply configuration snapshots. Their
original containers remain stopped with their configuration volumes intact.
Encrypted snapshots populate five fresh, exclusive source volumes; the same
claimed Plex identity runs in only one test copy at a time. Three original lab
media files are copied into a separate folder. No main configuration, Plex
identity, credential or media folder supplies this fixture.

The packaged browser reviews and creates the complete recovery file and exports
its key through owner-password authorization. Independently retained file/key
copies authenticate before simulated loss. Only this task's five new source app
volumes and dashboard volume are removed. Its original state directory is renamed
and unavailable at the source path. Recovery uses the complete file/key and a
different copy of the media folder.

A deliberate extraction failure occurs after the claimed Plex configuration is
actually written. Its original machine identifier is verified in that stopped
candidate. All five new recovery containers remain stopped. A fresh packaged
executable then resumes the saved review and completes recovery. Wrong keys,
occupied original ports and existing stopped resources are rejected before
overwriting or adopting anything.

Recovered acceptance verifies:

- Plex remains claimed with the same machine identifier, library IDs/UUIDs and
  media records. Normal Plex authorization can read the original video bytes;
  missing and invalid authorization are rejected.
- Seerr signs in through Plex with an empty cookie jar. The same owner,
  permissions, enabled library, Sonarr/Radarr connections and pending test request
  return; local login and admission of new Plex users remain disabled.
- Tautulli accepts its saved web password and API key, monitors the same Plex
  server, and preserves library/user records. All three account-app databases
  pass integrity checks and preserve the checked records/counts.
- The saved Stackarr password and private credentials work, all five dashboard
  integrations authenticate freshly, old Stackarr sessions are rejected and
  private controller enrollment is regenerated. Backup schedules remain paused.
- Both three-file media copies and the original lab media match their hashes.
  All nine main integrations authenticate freshly; main container IDs, settings,
  credential fingerprints, nightly policy and 16 tracked media/data files match
  the baseline.

The recovered apps, dashboard and controller are stopped after acceptance.
Original lab volumes and containers remain; recovered configuration volumes,
keys, encrypted backups and media copies are retained. Private evidence includes
`acceptance.json`, `verification.json`, `recovery-acceptance.json`,
`backup-acceptance.json` and `claimed-recovered-dashboard.png`.
The fixed maintainer entry point is `tools/docker_claimed_host_recovery_check.py`;
do not repoint it at personal installations.

This tests Docker reconstruction on the same computer with still-valid account
authorization. Replacement-Windows recovery, native dialog walkthroughs,
invited/shared-user or revoked-credential changes, populated playback history
and client playback remain separate checks. The source/key copies are independent
files on this test host, not a physical-disk-loss exercise. Media remains excluded
from the recovery archive and needs its own backup.

Upstream data boundaries: [Plex Docker configuration](https://github.com/plexinc/pms-docker),
[Seerr settings/database backups](https://docs.seerr.dev/using-seerr/backups/),
and [Tautulli configuration/database recovery](https://github.com/Tautulli/Tautulli/wiki/Frequently-Asked-Questions).
