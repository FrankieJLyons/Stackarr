# Alpha 0.1 manual test

The 19 October 2026 package is `dist/Stackarr-Alpha-0.1-Test.zip`.
Its SHA-256 is `2c88ba9238c79e0ff7054557e2f92eb92e5c111908720dede17fa4ed1506e3b5`.
Extract the complete ZIP and open **Start Stackarr.cmd**. The EXE and bundled
Docker dashboard were rebuilt with the library and quality choices below.

Docker now uses the readable groups **stackarr-controller** and
**stackarr-apps**. The dashboard container is **stackarr-controller**; app
containers have names such as **stackarr-apps-sonarr-1**. Another installation
gets a short numbered suffix when containers, networks, retained volumes or
saved receipts already reserve a name. Existing receipts with the older random
names remain supported by lifecycle, backup, updates and recovery operations.

This alpha uses portable state in `alpha-data/docker` beside the launcher. Its
separate `alpha-data/media` test folder is created and offered automatically.
Keep the extracted folder in its original location while using this installation.
The usual AppData state directory remains the normal preview's default; Docker
could not see newly created enrollment files there on this test host. A read-only
probe confirmed the workspace location was visible, so this package uses it.

## Setup choices

- One Movies library at `alpha-data/media/media/movies` and one TV library at
  `alpha-data/media/media/tv`. Quality never creates separate library folders.
- Independent Movies and TV request quality: **1080p**, **4K / UHD**, or
  **Other**, with **SD** and **720p** underneath. New setup controls default to
  1080p; older saved configurations retain their existing behavior until chosen.
- Installation review includes the exact native profile names. Sonarr/Radarr's
  profiles are verified after startup; their profile rules are not rewritten.
- The approved choices are retained separately from later setup drafts and saved
  with the installed app connections. Reviewed Seerr connections use those exact
  profiles, even when another profile is first in the API response. A missing or
  ambiguous profile requires attention instead of silently selecting another.
- Existing-app setup and existing Seerr connections are preserved. When adding
  media directly in Sonarr/Radarr, select the same profile in that app; this is
  Seerr's request preference, not an upstream global default or a media conversion.

Select all nine new apps, keep automatic ports, review installation and approve
the download. Complete Plex and Seerr account setup, review companion setup,
choose **Finish connecting**, then preview and approve the app connections.
Plex libraries use `/data/media/movies` and `/data/media/tv`. Providers and their
credentials remain owner choices. Cleanuparr starts in dry-run with automatic
cleanup disabled. Browser closure leaves the containers running.

## Build and verification

Build the Windows controller with `platform/windows/Stackarr.spec`, build the
dashboard Docker image, then package with:

```text
python -m tools.package_docker_preview --image stackarr:alpha-0.1-20261019-names-r2 --controller-executable dist/alpha-01-runtime-names-r2/StackarrPreview.exe --output dist/Stackarr-Alpha-0.1-Named-r2 --alpha-test
```

The final Python suite passes **751 tests, with 3 skipped**. Source/browser checks
pass eight scenarios covering independent choices, draft reload, phone layout,
preservation of existing-app choices, profile resolution and immutable approval
handoff. The frozen EXE passes 24 checks outside the checkout, including its
quality module. All eight payload hashes and nine ZIP entries are verified.
Private evidence is in `.runtime/alpha-0.1/`, including the browser report,
screenshots, frozen report, package report and final suite XML.

A readiness-check response race discovered by the full suite is also fixed:
the check lock is released before the completed HTTP response is sent, allowing
an immediate retry after a failed check.

This package remains an unsigned private alpha. A successful first-run page does
not certify account completion, all-app installation, acquisition/import/playback,
clean-Windows Docker setup, reboot startup or LAN access. Record the manual run's
actual stopping point before claiming those outcomes.

The manual run passes all ten host-readiness checks. Its final packaged dashboard
is healthy, enrollment files are visible in the container, and the authenticated
controller probe succeeds. The owner created the local password and completed
Plex and Seerr sign-in. All nine app containers are running and the dashboard
shows **9/9 connected with fresh data**.

Plex is claimed as **Stackarr Alpha 0.1**, with outside-home access disabled and
one Movies and one TV library. A locally generated 12-second 1080p movie completed
playback; the test TV library also contains an original demo episode. Companion
setup succeeded, including nine availability monitors and Cleanuparr's safe mode.
Generated Arr logins are saved privately. All six reviewed connections were
created: two download clients, two Prowlarr applications and two Seerr request
services using `HD-1080p` and the matching library paths.

The first image download paused before app creation. A retry of the same approved
pull completed Sonarr's missing image, then **Retry download** in Stackarr resumed
the same installation. This run also needed the portable folder workaround above;
it is a working manual alpha, not evidence of an untouched one-click recipient run.

Providers/indexers remain an owner choice. Prowlarr and the Arr apps correctly
report missing-source warnings; acquisition and automatic import were not exercised
in this run. The apps remain running for exploration.

The running alpha was subsequently moved to the readable Docker names. All ten
settings volumes were copied and compared file by file before startup; the
original volumes were retained. All nine connections, app-volume ownership for
backups, and the dashboard update recipe pass with the new names. Plex retains
its server identity, libraries and demo playback history; Seerr retains both
1080p request profiles. Test media files are unchanged. The refreshed ZIP contains
only its nine distributable entries, with all eight payload hashes verified.

Docker Desktop can report a Windows media mount using its Linux host-mount path.
Ownership checks normalize that spelling while still checking the exact folder
and read-only access. This was verified against the recreated live Plex container
and through the final packaged controller. Reopening the launcher uses the same
installation and permanent Compose files without creating duplicate groups.
