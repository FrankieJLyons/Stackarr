# Isolated Docker integration lab

This is maintainer test tooling, not the finished one-download installer. It uses a
new Compose project, private project network, fresh configuration volumes, separate
loopback ports and an empty synthetic-media directory under ignored `test-results`.
It never attaches the shared `stackarr-control` network, mounts personal media,
publishes to the LAN, mounts Docker's socket, or enables automatic restart.
Containers share the host's resources; CPU and memory limits reduce their impact.

The six upstream images are pinned in `tools/docker-lab-images.json`. Only
Linux/amd64 was exercised. These are compatibility fixtures, not a claim that the
images have no vulnerabilities. The production catalog still needs its own release
lock and update policy. Stackarr's own lab image uses a locally built immutable ID.

## Recorded Windows Docker result — 3 October 2026

Windows 11 Home, Docker Desktop 4.92.0, Linux engine 29.8.0 and Compose 5.5.1.
No VM, host service, scheduled task, firewall or production media app was modified.
The unrelated pre-existing Docker container retained its identity and original
startup timestamp throughout the test.

| Check | Observed result | Limit |
| --- | --- | --- |
| Build and startup | Stackarr and six real upstream containers started | Fresh app volumes on an existing Docker host, not a clean Windows installation |
| Stackarr boundary | Health responds; configuration API requires sign-in | Full security audit remains outstanding |
| Plex | Sessions collector parses the real API | Unclaimed server; no account sign-in, playback or transcoding test |
| Sonarr 4.0.20 / Radarr 6.4.4 | Health, queues and blocklists collected | Empty libraries; no actual media import |
| Prowlarr 2.6.5 | Health and sources collected; Sonarr/Radarr connections created | No indexers or subscriptions configured |
| qBittorrent 5.2.4 | Authenticated downloads collector works | No torrents or external peers used |
| Seerr 3.5.0 | Container starts; collector reports authentication/setup needed | Account and media-server setup intentionally unfinished |
| Wiring | Four connections created through advertised schemas and test endpoints | Maintainer fixture seeds credentials; consumer handoff remains work |
| Repeat preview | Zero duplicate changes proposed | Concurrent upstream edits are not certified |
| Container restart | Saved credentials, four connections and sentinel retained | Host reboot before Windows sign-in remains untested |
| Compose down/up | Volumes, sentinel and authenticated collectors retained | No volume deletion or application database rollback tested |
| Folder access | UID 1000 Arr/qBittorrent can write/read the synthetic shared folder; Plex write rejected | Not evidence for NAS permissions or hardlinks |

Real testing found and fixed three integration defects: custom qBittorrent WebUI
port mapping, current qBittorrent HTTP 204 login success, and Arr-specific
`tvCategory`/`movieCategory` schema fields. Compose v5 detection was also fixed.

Sources: [LinuxServer qBittorrent port requirements](https://docs.linuxserver.io/images/docker-qbittorrent/#webui_port-variable),
[qBittorrent release changes](https://github.com/qbittorrent/qBittorrent/releases),
[Docker project isolation](https://docs.docker.com/compose/how-tos/project-name/).

## Repeat on an isolated test host

For a fresh automated run, build `stackarr:ci`, then use
`python -m tools.docker_lab_ci --context <verified-local-context>`. This explicitly
starts six application fixtures, sets a fresh qBittorrent password, stores fixture
credentials encrypted in the lab Stackarr volume, creates four connections, checks
real APIs after a restart, and stops only that generated project. It preserves all
volumes. The dedicated **Real Docker integration lab** GitHub workflow runs this on
a disposable Linux runner when manually dispatched or relevant source is pushed;
it is not a scheduled task.

For interactive review, `python -m tools.docker_lab --image <local-sha256-image-id>
--apps plex sonarr radarr prowlarr qbittorrent seerr` only prepares a new directory.
Review its `compose.json`, check the selected local Docker context and free ports,
then use that directory's exact name as `docker compose --project-name` and its
explicit `-f` file for every operation. Never use the repository's normal Compose
file to operate a lab. Do not start two labs on the same reserved ports.

`python -m tools.docker_lab_check <directory> --context <local-context>` verifies
project, network, mounts, volumes and ports before collecting APIs. Reports exclude
credentials. `docker_lab_wire --apply` configures only a fresh verified lab and
refuses an already-configured Stackarr volume; it is not an existing-app adoption
tool. If partially completed, inspect the lab and re-preview the remaining
connections instead of resetting or overwriting application settings.

| Local review page | Address |
| --- | --- |
| Stackarr | http://localhost:28787 |
| Plex | http://localhost:32450/web |
| Sonarr | http://localhost:28989 |
| Radarr | http://localhost:27878 |
| Prowlarr | http://localhost:29696 |
| qBittorrent | http://localhost:28080 |
| Seerr | http://localhost:25055 |

Stackarr's owner account is deliberately left for the human to create. Its setup
token is in the lab Stackarr volume (`/var/lib/stackarr/setup-token`); use the
existing local Docker `setup-token` administration command for this named project.
Do not reuse production credentials or claim the test Plex server accidentally.
The remaining consumer work is to replace this maintainer handoff with the wizard.

Stop with this lab's exact Compose project/file and `down`, without `--volumes` or
prune commands. Named volumes remain available to resume. Plex's upstream image
also creates an anonymous transcode volume; this test tooling does not delete it.

## One-app recovery checks

After a Docker/WSL failure, first confirm the host has recovered and has adequate
memory headroom. Do not restart Docker or Windows automatically: unrelated apps
may share the engine. On the development PC, system-managed virtual memory was
enabled after repeated Windows commit-exhaustion events; host restart and runtime
verification remain pending.

Run one isolated check at a time using `python -m tools.install_wizard_check --only seerr`,
then repeat with `tautulli`, `kuma`, or
`cleanuparr`. This option installs exactly that app, checks that other integrations
stay disabled, and exercises reviewed stop/start on the selected container.
It cannot be combined with `--full`, `--plex`, or `--companions`.
Completed deployments are stopped by the existing cleanup path; evidence and
volumes remain. Failed runs need receipt-based inspection before retrying.
These checks do not certify account setup, Plex connection, monitoring rules,
or cleanup automation. They have not yet passed on the recovering Windows host.
