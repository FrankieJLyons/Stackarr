# Finding existing apps

In Setup, choose **Find existing apps** before installing anything. With no apps
selected, Stackarr checks the supported catalog; otherwise it checks your selections.
The local launcher performs the check. A Docker dashboard delegates it to its
enrolled host controller. Both components need the updated discovery capability;
older previews still allow manual addresses.

The check reads running-container image/service hints and published IPv4 loopback
or wildcard TCP ports from a verified local Docker context, then makes bounded,
unauthenticated API probes on loopback. It also checks known default ports. No
container environment, config file, API key, volume or credential is read. It does
not follow redirects, scan a LAN, inspect remote Docker engines or change apps.
At most 128 container rows and three Docker addresses per app are considered.
HTTP responses are limited to 64 KiB; each candidate has an eight-second deadline.

Choose **Use this … app** to save a connect-only draft with that address. Continue
to review the address, save it and enter credentials in Apps. Nothing inside the
existing application is modified. Existing saved connections and credentials are
preserved. Docker API routes use `host.docker.internal`; browser links keep the
local address. The connection review displays the API address before saving.

An API identity match is stronger evidence than a container label. A 401/403 only
means a service requires authentication, so its identity still needs confirmation.
Tautulli, Uptime Kuma and Cleanuparr can receive Docker address hints but still need
manual identity/connection checks. Missing results do not establish absence:
HTTPS, reverse-proxy subpaths, host networking, IPv6-only binds, arbitrary image
names, native apps on custom ports and other computers may require manual entry.
Multiple instances are offered separately; Stackarr does not choose one silently.

## Draft compatibility

`AppChoice.browser_url` is an optional, credential-free HTTP(S) URL. Older drafts
default to an empty value and use the API address for browser links, as before.
Saving a discovery choice changes only the draft; applying an existing-connection
review saves the API and browser addresses without installing or migrating the app.
Editing the API address clears a previously inferred browser address.

## Importing native Windows settings

The updated source build adds **Find native app settings** in Setup and Apps.
It supports Sonarr, Radarr and Prowlarr using their standard
`%ProgramData%/<App>/config.xml` files, including custom HTTP ports and URL bases.
This is a separate, authenticated check from the unauthenticated address discovery
above. It reads the API key privately, verifies the API's app name and data folder,
and reads settings through bounded GET requests. It never opens an app database.

Choose **Review … import** to see library paths, quality profiles and their actual
allowed qualities, download client names, or Prowlarr sources and linked apps.
**Import connection and settings** saves an encrypted credential and sanitized
snapshot together with the connection. The setup draft switches that app to
connect mode. Existing profiles and paths remain in the original app; no default
quality is inferred, provider secrets are not copied, and Windows folders are
never silently translated to Docker paths. Use the same flow to refresh a snapshot.

The review is session-bound, single-use and expires after five minutes. Apply
re-reads the native configuration and settings, checks the dashboard route as well
as the host route, and refuses a changed review, a changed Stackarr revision, or a
different saved connection. Credentials never appear in the browser, audit log,
or portable configuration export. Private controller handoff uses the existing
authenticated transport.

Imported apps are read-only. Stackarr can collect status, but connection wiring,
source tests/additions, automatic import scans, and requests that could write to
an imported app are blocked. Ordinary settings saves cannot remove this protection.
Native apps receive no Stackarr restart, update or removal ownership. This is
connection in place, not database migration or a Docker conversion.

Automatic import currently requires an updated Windows host controller (or local
host launcher), readable standard configuration files, and an HTTP API reachable
from both host and dashboard. Custom data directories, HTTPS-only services,
Plex account tokens and qBittorrent password recovery need separate support.
Missing, linked, oversized or malformed configuration fails closed. The import
does not edit listening addresses or firewall rules to make a connection work.
For Docker-to-Windows access, Stackarr retains the app's original loopback HTTP
Host header while connecting through `host.docker.internal`. This supports native
Windows listeners that reject Docker's hostname. The override is restricted to
the same port on a read-only Docker-to-host connection.

## What remains

Previewed quality policies, verified existing Plex folder mapping, additional
native adapters, and an explicit transition from read-only access to reviewed
changes remain separate work. See [the setup review](SETUP-REVIEW-2026-10-20.md)
for the proposed sequence. Native database migration is not implemented.
# Native Plex libraries

The Windows native-settings scan also reads the current user's fixed Plex
registry location in read-only mode. It verifies the stored server identity and
account token against the local Plex API before offering its library snapshot.
The credential handoff uses the private controller channel; the browser receives
only the reviewed library summary. Importing does not claim, scan, migrate or
reconfigure Plex. A different saved Plex connection is preserved.

See [downloads and libraries](DOWNLOADS-AND-LIBRARIES.md) for verified shared
storage mapping. Detection alone does not authorize remounting working media into
a separate installation.
