# Open Stackarr with Docker

Docker must already be installed and running with Linux containers. In this source
preview, the first start builds the Stackarr image; prebuilt release images are
still planned.

1. Unpack the complete project/release folder.
2. On Windows, double-click **Start Stackarr.cmd**. On a Linux or macOS desktop,
   run `sh "Start Stackarr.sh"` from that folder.
3. The helper starts only the Stackarr service and opens the browser for you.
4. Choose your local Stackarr password and select **Continue to setup**.
5. Later starts open the normal sign-in page and preserve existing data.

There is no setup code to locate or copy. If you opened the address directly before
creating your account, use Start Stackarr to open the private setup page. If the
page says the invitation expired, run the helper again. It lasts five minutes.
The helper must run on the installation computer with permission to use Docker.
It does not install Docker, open firewall ports or change media-app containers.

The Docker dashboard can guide existing-app connections and install reviewed apps
through its enrolled host controller. The [Docker media-app preview](DOCKER-PLEX-PREVIEW.md)
adds prebuilt packaging and private connection completion for Plex and the four core
download/Arr apps, followed by reviewed wiring, generated Arr web logins and guided
Prowlarr source setup. Provider choices stay with the owner. The dashboard has no Docker socket.
Seerr now has private connection completion and reviewed Arr wiring. Original
movie/season requests reached automatic import, Plex libraries and completion.
The packaged dashboard now offers reviewed owned-app start/stop/restart and encrypted
app-configuration backup/restore. See the media-app preview guide for the downtime,
same-installation restriction, safety copy and media exclusions. Updates/rollback,
whole-host recovery and full recipient acceptance still have separate gates.

## Media folder browsing (administrator configuration)

The wizard can browse explicitly shared media folders. It never browses the entire
host drive or asks a browser to upload a directory. Add a dedicated bind mount and
describe its container path and matching host path with `STACKARR_MEDIA_ROOTS`:

```yaml
environment:
  STACKARR_MEDIA_ROOTS: '[{"label":"Media drive","path":"/shared-media","host_path":"D:/Media"}]'
volumes:
  - type: bind
    source: D:/Media
    target: /shared-media
    bind:
      create_host_path: false
```

Keep the existing Stackarr data volume and environment settings. The host folder
must already exist and be shared with Docker. Stackarr's container user needs read
access for browsing and write access for the explicit **Create missing media
folders** action. Existing files are never replaced or moved. Folder links,
parent traversal and paths outside the declared roots are rejected.

This is an administrator bridge for the preview, **not the finished novice
installation experience**. A host connection that offers native disk/folder
selection, checks actual host ports and installs the reviewed apps remains a
release blocker. Checking ports inside a container cannot establish that host
ports are free. The wizard states that limitation instead of showing a false pass.

## For administrators of headless servers

The desktop helper needs a browser on its computer. On a headless deployment,
configure the intended origin and secure access first. An administrator can obtain
a one-use setup invitation with `docker compose exec -T stackarr stackarr setup-link`
and open that private link in the intended browser. Do not publish or share the
invitation. A complete headless/NAS enrollment assistant is still planned.

## Security implementation

Only a host-side command can mint an invitation; the anonymous web API cannot.
The database holds hashed tickets with five-minute expiry. Exchange is atomic and
single-use. The browser immediately removes the URL fragment and exchanges it for
an HTTP-only, SameSite=Strict cookie, with Secure enabled on HTTPS. The fragment
does not reach HTTP request logs or Referer headers; it is nevertheless a temporary
secret and must not be logged by custom launchers. Browser history replacement
reduces exposure but is not a guarantee against browser extensions or local tools.

Setup requests still require the exact configured Origin. The invitation and
cookie authorize only creation of the first local account, never administrator
sign-in. Creating the account clears all invitations; reopening the helper after
setup returns the ordinary sign-in address. Legacy administrative setup-token API
support remains for compatibility, but there is no token input in the UI.

## Web ports

New Compose installations publish Stackarr on **28000**. The wizard's Stackarr
sequence assigns Plex 28001, qBittorrent 28002, Sonarr 28003, Radarr 28004,
Prowlarr 28005, Cleanuparr 28006, Seerr 28007, Tautulli 28008 and Uptime Kuma 28009.
Unused apps retain their reserved slots. Existing apps are not renumbered.
The sequence is an explicit choice; app defaults and custom ports remain available.

The table shows the dashboard's actual browser port. Selecting a sequence changes
new-app choices only, not the running dashboard address. Existing saved draft port
values remain until the owner selects a different port mode.
For a custom Docker dashboard port, set `STACKARR_PORT` and, if already explicitly
set, update `STACKARR_ORIGIN` to match. The internal container port remains 8787.
For an existing installation previously using 8787, set `STACKARR_PORT=8787` before
applying the updated Compose file to retain its address. Keep its data volume.
