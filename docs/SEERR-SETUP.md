# Seerr storage and Plex sign-in setup

The latest [security package](SEERR-PERMISSIONS-FIX.md) also retains these storage
and sign-in improvements. The evidence below records the earlier setup r3 slice.

The final private bundle is
`Stackarr-Docker-Seerr-Setup-Preview-20261018-r3.zip`. Its nine entries/eight payload
hashes and 21 frozen-executable checks pass. Python regression reports 579 passed,
3 skipped; Ruff, JavaScript syntax checks and the 264-file source audit pass.
The matrix records 12 passing results across 10 scenarios: six native storage
cases, official/blocked popup cases and two packaged journeys repeated for final
r3 after screenshot review corrected garbled setup punctuation. A further human
fresh-sign-in/session-persistence case passes on 19 October: 13 recorded results
in total. The original automatic popup checks alone do not certify a callback.

For a new installation, Stackarr shows only the account steps needed by the apps
you selected. Its new-app links open those saved local addresses.

1. If you installed Plex, open **Plex setup**, sign in and finish Server Setup.
   Give the server a name you can recognise. Its movie and TV folders are
   `/data/media/movies` and `/data/media/tv`. Choose that server name when Plex
   lists your servers.
2. Open **Seerr setup**, choose **Configure Plex**, then **Login with Plex**.
   Use the Plex account that owns your server, then choose the server and libraries.
3. Return to Stackarr and choose **Finish connecting**. Stackarr verifies and
   privately saves supported connection details; no key or token copying is needed.

If the Plex window does not open, expand **Plex sign-in window did not open?**
in Stackarr. Copy Seerr's address into your usual browser, allow pop-ups for that
address, then choose **Login with Plex** again. Complete the Plex window and
return to Seerr. If clipboard access is denied, Stackarr selects the address for
manual copying. It never asks for your Plex password.

Seerr-only setup does not ask you to create another Plex server or choose media
folders. The separate Plex server step appears when a new Plex installation is
included. Once connected, the account instructions disappear and normal app links
and saved connection results remain.

## Why the old mount warning appeared

Seerr's image includes an empty `DOCKER` marker under `/app/config`. Docker can
copy that marker into a new named volume. Seerr's warning checks the marker's
presence instead of Docker's mount inventory, so a correctly mounted volume can
still trigger it. Seerr's own Windows guide documents this named-volume caveat.
See the [Seerr marker check](https://github.com/seerr-team/seerr/blob/v3.5.0/server/utils/appDataVolume.ts)
and [official Docker guide](https://docs.seerr.dev/getting-started/docker/#windows).

Stackarr keeps the official pinned image, its normal startup command and the
existing named-volume layout. It does not replace the database path with a
Windows bind mount or patch Seerr's UI.

During a new Seerr installation, after startup and before credential handoff,
Stackarr verifies the receipt's exact image, environment, privileges, private
network and exclusive local config volume. A short check as Seerr's normal
container user creates a unique file, writes and flushes random bytes, reads them
back, removes only that probe and flushes the directory. It rechecks container
identity and storage metadata before removing only the empty regular `DOCKER`
marker. A missing marker is already ready.

A nonempty marker, symlink/hardlink, changed/shared settings volume, stopped or
changed container, or denied write stops the operation with a fixed storage
message. Other files, app settings, databases and account details are retained.
Resume repeats the check safely. Existing installations are not adopted or
modified by this new-install step. Maintenance and recovery keep their existing
recipes and volume paths; no image or schema migration is introduced.

## Acceptance boundary

The checks use the real pinned Seerr 3.5.0 image, fresh owned config volumes and
copies of three original sample files. Native checks reproduce the actual old
warning, verify its disappearance after storage checks, refuse unexpected marker
files/links, exercise a real write denial and a real read-only foreign volume
consumer, and replace only the new container. Its settings-file hash, database,
volume identity and original test marker remain; the warning stays cleared.

The extracted package's Seerr-only and Plex-plus-Seerr browser journeys verify
the appropriate instructions, copy/manual-copy fallback and desktop/phone layouts.
The clipboard checks use browser fixtures so the person's actual clipboard stays
untouched. Fresh Seerr pages show no mount warning. A real upstream login button
opens the official HTTPS Plex authorization page. A separate browser fixture
blocks `window.open` to exercise the missing-window situation; it does not fake
authentication. Incomplete accounts remain pending when **Finish connecting** is
chosen. The combined setup uses a distinct unclaimed test Plex server with
read-only access to copied sample media.

The blocked-window check uses the attempted window creation and unauthenticated
session as evidence. It does not depend on Seerr showing an inline error;
Stackarr's fallback instructions remain available without waiting for one.

The original automatic checks stop before a person completes fresh authorization.
On 19 October the owner chose fresh sign-in, completed the usual-browser fallback
and returned to **Configure Media Server**. The new lab contains a Plex owner with
owner permissions. Maintainer checks connect only the already claimed, separate
maintenance Plex server and its existing original-sample library, using Seerr's
new authorization internally. No earlier sign-in authorization is reused, no
existing Plex library is created or modified and no download is requested.
The check uses Seerr 3.5's separate library-sync and library-enable endpoints from
its [versioned API contract](https://github.com/seerr-team/seerr/blob/v3.5.0/seerr-api.yml).

The packaged private connection completes, repeat handoff preserves it and fresh
dashboard monitoring succeeds. Replacing only this new Seerr container keeps the
same settings volume, owner/authorization fingerprint, settings-file hash and
selected library; the warning stays cleared and authenticated APIs work. The
owner refreshed the same usual-browser page and confirmed the session survived.
The connected package screen removes the completed account guide.

This follow-up uses an already claimed test server and API-assisted library
selection. A novice recipient's server claim/library-selection walkthrough,
other browsers and invited/shared-user permissions remain separate gates. The
earlier [Seerr Plex-owner maintenance checks](SEERR-PLEX-MAINTENANCE.md) retain
their separate update/recovery matrix. Stackarr never brokers a Plex password.
The later [permission/revocation matrix](SEERR-PERMISSIONS.md) exercises real Seerr
enforcement with synthetic external identities and a packaged invited user. It
records the open-session revocation boundary and an unresolved delegated-admin
permission flaw; real second-account Plex cloud behavior remains separate.

Maintainer entry points are `tools.docker_seerr_guidance_check` (`native`,
`storage_persistence`) and `tools.docker_seerr_guidance_package_check`
(`verify_package`, `seerr`, `resume_seerr`, `combined`, `finalize`). The optional `persistence`
phase is excluded from normal execution and requires explicit human approval
before enabling its test-authorization-reuse flag. That flag is not authorization
on its own. No account credentials are included in the product package.

Private proof remains under `test-results/docker-seerr-guidance-20261018-r1/`.
Finalization compares the original app/dashboard IDs, settings/credential hashes,
nightly backup policy and 16 media/data files, then freshly authenticates all nine
main integrations. The follow-up's `fresh-plex-signin/` proof uses a new morning
baseline, after normal overnight activity, and records the human session result.
Only the new lab containers/networks are removed; settings volumes, state, keys
and sample files remain. The earlier test Plex is returned to its original stopped
state. The main package is not upgraded.
