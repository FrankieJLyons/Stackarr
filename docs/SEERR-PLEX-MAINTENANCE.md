# Seerr maintenance with Plex sign-in

This extends the [five-app maintenance matrix](OPTIONAL-APP-MAINTENANCE.md) from a
local Seerr account to a real Plex owner account. It covers compatible Seerr
3.4.1 → 3.5.0 updates and recovery in an isolated Docker installation. Major
migrations and invited-user access changes remain separate acceptance gates.
A subsequent [whole-host recovery lab](HOST-RECOVERY.md#claimed-account-follow-up--18-october-2026)
also passes reconstruction of the claimed Plex, Seerr and Tautulli accounts.

## Completed acceptance — 18 October 2026

All **six native cases** and **five packaged browser app actions** pass. Fresh
Plex sign-in works after every case with the same owner, permissions, selected
library, Sonarr/Radarr connections and pending request. The failure cases include
an API-healthy candidate that disabled Plex sign-in, actual request-database
writes, and a real worker exit between receipt-file and database commits.
Independent inspection of the encrypted snapshots confirms the failed writes
and matching restored configuration.

The earlier packaged controller created a real update checkpoint; the new
package successfully rolled it back. Stackarr package promotion produced **zero
Seerr container lifecycle events**. The final lab returns to Seerr 3.4.1.

All nine existing main integrations authenticate freshly. Their container IDs,
settings, credential fingerprints, nightly backup policy and **16 tracked
media/data files** match the baseline. All **three original lab media files**
also match. The isolated dashboard, controller, Seerr and three borrowed test
dependencies are stopped. Configuration volumes, keys and encrypted recovery
files remain available; no media was removed.

The tested private bundle is
**Stackarr-Docker-Seerr-Plex-Maintenance-Preview-20261018-r2.zip**.
Its nine allowlisted entries and eight payload hashes verify. The extracted
executable passes **17 frozen smoke checks outside the checkout**. Regression:
**511 passed, 3 skipped** (existing Windows filesystem-link cases); Ruff passes;
the portable-source audit reports **239 files, 0 findings**.

- Dashboard image: `sha256:737f186343a43505b697cf3052e7a6253dd8994bd0d836c0907e916be9d52889`.
- ZIP SHA-256: `293c99a0f347c1eeebdb01c0fc4ecfdc1d93a0ea4e66189e3c4bf4474bf97cee`.
- Private reports: `acceptance.json`, `native-report.json`, `browser-report.json`,
  `package-promotion-preservation.json` and `package-verification-r2.json` beneath
  the lab directory. `packaged-browser-results.png` records the final app history.

The existing main installation stays on its earlier Self-Removal r4 package.
The new preview was exercised only in the isolated installation.

## Account and data boundary

The fixed lab is `test-results/docker-seerr-plex-maintenance-20261018`. Seerr has
its own configuration volume and port 43270. Its packaged Stackarr dashboard and
private controller use ports 29240 and 29091. The existing main dashboard and
nine media apps are outside every maintenance target.

The lab reuses only the previously isolated **Stackarr Maintenance Lab** Plex
server and its separate Sonarr/Radarr dependencies. Those stopped test containers
are started with their original identities and returned to stopped state afterward.
No existing main configuration, media-server identity or account token is cloned.

Plex authorization uses a fresh normal OAuth PIN and the remembered Plex account.
The in-app browser did not expose Seerr's popup, so the supported Plex authorization
was opened in a regular tab. The resulting authorization is submitted to Seerr's
normal `/auth/plex` endpoint and retained encrypted in the private lab. No token
is extracted from an existing application's database. Every subsequent check
starts with an empty cookie jar, verifies that `/auth/me` initially rejects access,
signs in through Plex, then checks the same owner identity and permissions.
Local sign-in and automatic admission of new Plex users are disabled in this lab.
The native popup itself still needs a recipient-browser walkthrough.

Seerr intentionally excludes Plex personal-video libraries whose agent is
`com.plexapp.agents.none`. A separate movie library, **Stackarr Seerr SSO originals**,
therefore references the existing original generated video in the test media folder.
The original library and its video remain. Library synchronization uses the API
for the running version: 3.5.0 changes sync/enabling to explicit mutation endpoints.
Maintenance checkpoints read `/settings/plex`, which does not toggle library flags.
[Seerr's library filter](https://github.com/seerr-team/seerr/blob/v3.4.1/server/api/plexapi.ts),
[3.5.0 API change](https://github.com/seerr-team/seerr/releases/tag/v3.5.0).

One synthetic pending movie request is stored only in the new Seerr database.
It uses an original test identifier, remains pending and triggers no download,
search, actual media request or main-library change. This provides nonempty request
and owner records for preservation checks.

## Protected settings and recovery

New Seerr checkpoints protect Plex account IDs/usernames, user types/permissions,
media-server type, Plex/local sign-in settings, admission/default permissions,
Plex server/library selection, Arr profiles/paths and request identities/statuses.
Only the Plex library `lastScan` cursor is omitted from new checkpoints because
a background scan can advance it after a healthy update. Library IDs, enabled
flags and all other settings remain protected.

Encrypted runs retain their checkpoint version. Older records keep their original
comparison shape during recovery; new records include the stronger authentication
checks. Repair records also save that version before taking their protected digest.
This avoids interpreting an older checkpoint as if it contained new fields.

The native matrix covers repair, failed-repair recovery, distinct-image update
and manual rollback, rejection of a healthy API candidate that disabled Plex
sign-in and changed the request, fresh-process recovery after an actual worker
exit in the receipt commit gap, and encrypted configuration restore. Faults make
real writes to the new app's settings and request database. They exist only in
maintainer test processes, with no production fault switch.

The packaged browser matrix creates an update checkpoint with the earlier
Optional-Maintenance r4 controller, promotes only the isolated Stackarr installation,
and rolls that older checkpoint back with the new controller. It then exercises
new-package repair, update and rollback. Fresh Plex sessions and the same saved
request, owner, libraries and connections are checked after each action.

Private evidence, keys and account records stay under the ignored lab directory.
The distributable ZIP contains only the allowlisted executable/image/helper payload.
Maintainer entry points are `tools/docker_seerr_plex_maintenance_check.py` and
`tools/docker_seerr_plex_browser_check.py`; do not repoint them at personal data.

The older Seerr image's `DOCKER` marker can produce a mount warning when Docker
populates a fresh named volume. That warning is now addressed for new Stackarr
installations by [verified Seerr storage setup](SEERR-SETUP.md), which checks real
ownership, exclusive storage and durable writes before clearing only the empty
image marker. The maintenance lab above remains unchanged. A warning alone is
not accepted as proof of either lost data or successful persistence.
