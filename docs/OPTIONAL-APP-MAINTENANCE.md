# Plex, Seerr and companion maintenance

Use **Apps → Check installation → Review repair** to recreate one owned app with
its saved image, ports, configuration and login. A stopped app remains stopped.
Repair retains Plex's original anonymous transcode volume. It never resets an
account or deletes media, downloads, configuration volumes or another app.

Use **Apps → Check packaged updates** for reviewed, immutable, same-major image
candidates. Each update verifies the current app, stops only that app, encrypts
and verifies its configuration snapshot, then checks the candidate's release,
authenticated API and saved settings. **Review rollback** restores the previous
image with its matching data. **Recover interrupted update** explicitly resumes
recovery after a controller interruption. Keep the controller encryption key and
the saved snapshots. Major-version migrations remain outside this preview.

The update catalog now covers all nine supported apps. Tautulli's official image
uses a branch label and Kuma omits a release label; Stackarr verifies their actual
running releases as well as the approved immutable image metadata. Companion
login checks use the reviewed candidate recipe before the receipt is committed.
The dashboard's owner/session review and single-use approval contract covers all
nine apps and still rejects browser-supplied images or Compose settings.

Protected checks include Seerr's actual Arr library paths, profiles, Plex settings,
users and request identities, with pagination and a bounded record limit; Tautulli's
login, API key and Plex identity/connection; Kuma's authenticated monitor IDs,
settings and API-key records; and Cleanuparr's complete configuration and saved
connections. Cleanuparr 2.10.11 adds an errored-torrent option. Only its exact inactive
default is treated as equivalent to absence in 2.10.10; enabling its threshold or
deletion settings still rejects the update. Dry-run and disabled automatic jobs
remain protected. Companions have no media, downloads or Docker-socket mounts.

## Isolated acceptance

The fixed maintainer lab is `test-results/docker-optional-maintenance-20261018`.
It owns fresh volumes, a separate network and ports 43250–43254. Three fresh
auxiliary Arr/download services provide real test connections. No existing server
identity, configuration volume, media folder or account token is cloned.

| App | Fresh baseline | Reviewed candidate | Fixture |
| --- | --- | --- | --- |
| Plex | 1.43.3.10896-cb3ebc72d | 1.43.4.10903-e5521bd8c | Separately claimed **Stackarr Maintenance Lab**, original generated video |
| Seerr | 3.4.1 | 3.5.0 | Generated local administrator and separate Sonarr/Radarr connections |
| Tautulli | 2.18.1 | 2.18.2 | Generated web login and authenticated monitoring of only the new Plex server |
| Uptime Kuma | 2.5.5 slim | 2.5.6 slim | Eight owned-service TCP monitors and a generated metrics key |
| Cleanuparr | 2.10.10 | 2.10.11 | Generated login, three isolated connections, dry-run and all five jobs disabled |

Plex setup targets the new server's original machine identity. Invalid tokens from
its private peer are rejected; remote access and the temporary network-authentication
exception are disabled. Original fixture files remain intact. Plex deliberately
ignores filenames containing “sample”, so the scan uses a separate copy named
**Stackarr Maintenance Fixture**.

The native matrix runs repair, recovery after a failed repair with confirmed
configuration writes, a distinct-image update and rollback, failed-update recovery,
fresh-process recovery after an actual worker exit in the receipt file/database gap,
and encrypted backup/restore. Every completed case compares saved settings/logins,
peer container IDs, sample-media hashes and the untouched main installation.
All **30 native cases** passed. Each app's encrypted before-repair and
failed-candidate snapshots were independently inspected to verify both the
original sentinel and the actual candidate overwrite/new marker before recovery.

The extracted-package browser matrix repeats repair, update and rollback through
the owner review controls and frozen private controller. All **15 browser actions
across five apps** passed using the final r4 package. The same owned fixture apps
were reused after copying only their native controller state into the new packaged
lab with its controller stopped; no additional Plex server identity was cloned.
Evidence and generated
credentials stay in the ignored lab directory. The distributable ZIP contains only
the fixed package payload, never lab state, account tokens, media or backups.

The bundle used for this earlier matrix is `Stackarr-Docker-Optional-Maintenance-Preview-20261018-r4.zip`.
Its nine allowlisted entries/eight payload hashes verify; its executable passes
17 frozen checks outside the checkout. The regression suite passes 503 tests
with three existing Windows filesystem-link skips. The main installation remains
on its earlier Self-Removal r4 dashboard/controller package throughout this work.

Final `acceptance.json` verifies the package/controller identity, original image
versions and saved settings after rollback, all nine main connections from the
actual dashboard and preservation of the main container/settings/media fingerprints.
The isolated eight apps, dashboard and controller are stopped. Volumes, all three
original fixture files, keys and encrypted snapshots are retained; generated
plaintext crash-work directories are removed only inside the fixed lab root.

Maintainer tools are `tools/docker_optional_maintenance_check.py` and
`tools/docker_optional_browser_check.py`. Their fixed lab guard prevents selecting
the main installation. A new acceptance run requires a new isolated root and
explicitly reviewed free ports; do not repoint these tools at personal data.

This earlier maintenance matrix does not itself certify major-version migrations,
replacement Windows hardware, second-device playback or whole-host reconstruction.
Seerr uses a disposable local account in this earlier matrix. The follow-up
[Plex-owner maintenance matrix](SEERR-PLEX-MAINTENANCE.md) passes compatible Seerr
updates/recovery with fresh Plex sign-in, protected owner permissions, libraries,
connections and a pending request, including recovery of this package's older
checkpoint. Invited/shared-user permissions, major/account migrations and
replacement-host recovery remain separate gates. The subsequent
[claimed-account Docker recovery lab](HOST-RECOVERY.md) passes reconstruction of
the same Plex, Seerr and Tautulli identities, libraries, connections and logins.
The existing main
dashboard, nine apps, nightly backup policy and 16 tracked media/data files remain
outside the maintenance test scope.

Release provenance: [Plex's official Docker source](https://github.com/plexinc/pms-docker),
[Seerr 3.5.0](https://github.com/seerr-team/seerr/releases/tag/v3.5.0),
[Tautulli 2.18.2](https://github.com/Tautulli/Tautulli/releases/tag/v2.18.2),
[Kuma 2.5.6](https://github.com/louislam/uptime-kuma/releases/tag/2.5.6), and
[Cleanuparr 2.10.11](https://github.com/Cleanuparr/Cleanuparr/releases/tag/v2.10.11).
