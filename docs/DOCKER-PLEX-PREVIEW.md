# Docker media-app preview

The private Docker preview packages a prebuilt Stackarr image, Windows controller,
readiness checks and reviewed Docker prerequisite setup. Open **Start Stackarr.cmd**,
complete any Docker setup prompts, then **Continue to Stackarr**. Python, a development
checkout, a separate readiness download and a local image build are unnecessary.

The dashboard and selected apps run in Docker. A small background controller on the computer performs only reviewed, owned operations. The dashboard has no Docker socket, and its controller connection uses the private enrollment and pinned TLS certificate. The newest private bundle is `Stackarr-Docker-First-Run-Preview-20261019-r1.zip` with [integrated readiness](INTEGRATED-FIRST-RUN.md) and the [Seerr security backport](SEERR-PERMISSIONS-FIX.md); the existing main installation remains on `Stackarr-Docker-Self-Removal-Preview-20261018-r4.zip` during isolated acceptance.

New setup shows the Plex/Seerr account steps for selected apps. Seerr's steps use
**Configure Plex → Login with Plex**, with a copyable address and usual-browser
fallback if the Plex window is blocked. A fresh Seerr settings volume is checked
for ownership and durable writes before its empty image warning marker is cleared.
Fresh human sign-in/return and browser-session persistence now pass using this
fallback. See [Seerr setup](SEERR-SETUP.md) for the Docker checks and remaining
broader browser/server-library-selection walkthroughs.

**Check Docker** now reports estimated private-network capacity without creating
or removing networks. Exhausted known pools block new app batches with recovery
guidance. Failed/interrupted image downloads offer **Retry download** using the
same saved images, ports and folders. Completed images stay cached and every
image is verified before app storage/startup. See
[NETWORK-DOWNLOAD-RECOVERY.md](NETWORK-DOWNLOAD-RECOVERY.md).

The nine-app update catalog includes compatible Tautulli, Uptime Kuma and
Cleanuparr candidates, with authenticated saved-setting checks. The separate
[five-app maintenance guide](OPTIONAL-APP-MAINTENANCE.md) records the precise
Plex/Seerr/companion versions, account scope and preservation tests.
The follow-up [Seerr Plex-owner maintenance guide](SEERR-PLEX-MAINTENANCE.md)
records fresh Plex sign-in, compatible update/rollback, failed/interrupted recovery
and recovery of an older package's update checkpoint.

**Settings → Review Stackarr removal → Remove Stackarr, keep settings** removes
only the dashboard and stops its private controller after a verified checkpoint.
Media apps keep running; the Stackarr account, settings, keys, app logins and
backups are kept. Reopen **Start Stackarr.cmd** to review reinstall in the local
window. Reinstall checks isolated data copies; failed/interrupted attempts keep
the original removed state. Scheduled backups pause until reinstall. See
[SELF-REMOVAL.md](SELF-REMOVAL.md) for recovery and retention limits.

**Apps → Check installation** now offers reviewed repair and removal for one
owned app. Both save a verified encrypted settings backup first. Removal keeps
settings, logins, media and backups; Repair brings the app back using the same
image and folders. Failed repair restores its checkpoint; interrupted maintenance
requires a recovery review after reopening Stackarr. Retained settings can still
be backed up while a container is absent. See [APP-MAINTENANCE.md](APP-MAINTENANCE.md).

**Settings → Stackarr updates & rollback** now updates both Stackarr components
from a reviewed compatible ZIP, checks isolated database copies and retains the
previous release and encrypted checkpoint. Media apps continue running. Failed
checks recover the working release and data; reopening a recovery-capable launcher
recovers interrupted maintenance. See [SELF-UPDATE.md](SELF-UPDATE.md) for rollback,
state retention, unsigned-package trust and compatibility limits.

**Settings → Stackarr updates & rollback → Review Stackarr repair** recreates
the owned dashboard/controller using the saved release and verified settings copies.
If the dashboard is unavailable, restore Docker and writable storage, then reopen
**Start Stackarr.cmd** for local repair review. Same-release repair preserves the
account, sessions, keys and backups; media apps keep their existing containers and
settings. Failed/interrupted candidates recover the original runtime. See
[RUNTIME-REPAIR.md](RUNTIME-REPAIR.md) for storage failures and recovery boundaries.

Whole-host configuration recovery now has an isolated nine-app Docker route:
**Backups → Prepare whole-host recovery → Create recovery file**, then
**Recover Stackarr.cmd** on an empty installation. Keep the recovery key separately
and preserve media through its own backup. Original app ports are retained; saved
accounts/logins return, old browser sessions are revoked and backup schedules pause
for review. [HOST-RECOVERY.md](HOST-RECOVERY.md) describes setup, retry, exclusions
and the completed claimed-account Docker follow-up plus remaining native-dialog/
replacement-Windows gates. Older
checkpoint notes below retain the acceptance boundaries at their original stages.

## Start the preview

1. Unpack the complete preview ZIP and open **Start Stackarr.cmd**.
2. Choose a local Stackarr password and select your apps. **Choose available ports for me** is recommended; manual ports remain under **Advanced port settings**. A new preview also avoids busy dashboard and private-controller ports, then saves its selected addresses for reopening.
3. Media apps ask for one folder in the wizard. If a single approved folder is available, it is already selected: continue to reuse it. **Choose a folder…** or **Choose another folder…** opens the Windows folder dialog on the installation computer. That human selection grants the folder; browser requests cannot supply a new host path. Cancel preserves the previous choice. Apps such as Uptime Kuma need no media-folder choice. Review installation before approving any app or missing media subfolder.
4. Install Plex. Open its local Web link, sign in and finish server setup. Give this server a distinct name so you can recognise it alongside any existing Plex servers. New library folders are `/data/media/movies` and `/data/media/tv`; existing files elsewhere in the chosen folder remain available beneath `/data` and are not moved.
5. Return to Stackarr and choose **Finish connecting**. Stackarr checks the owned container, retrieves the supported credential privately, verifies the API from the dashboard and encrypts the saved connection. No Plex token needs to be copied.

Plex's local Web setup uses `/web`; see the [official container guidance](https://github.com/plexinc/pms-docker). The preview keeps app ports on loopback. Home-network access and household playback certification remain separate work.

Signing into Plex may show libraries from an existing server. That alone does not complete the new server's setup. Return to the local Web link opened by Stackarr, finish the **Server Setup** wizard, and select libraries beneath the new server's name. The isolated maintainer server is named **Stackarr Docker Test**.

## Add downloads and library management

Choose **Add another app** in setup and select qBittorrent, Sonarr, Radarr and Prowlarr. Choose the same approved media root, review the folders and ports, and install. **Finish connecting** verifies all four APIs from the dashboard before saving their encrypted credentials as one transaction. Existing Plex settings stay in place.

## When a port is already in use

Automatic selection keeps an available requested port and chooses an alternative
for conflicts. It excludes the dashboard and private-controller ports, and checks
without contacting or stopping the service using a port. The final review shows
the actual app addresses. Changes apply only to newly selected installations.

If a port is taken after review, installation approval is rejected before it is
queued. If a port is taken during image download, the attempt stops before creating
app containers, volumes or media subfolders. Choose **Use available ports**, then
**Review installation** and approve the updated addresses. Your folder choice and
existing services stay in place. The previous empty attempt remains in history as
replaced. A conflict during final Docker startup offers **Review available ports**,
then **Apply new ports & resume**. That resumes the same partial installation,
keeps its settings volumes and leaves healthy running apps unchanged. If the
original address is free again, choose **Resume installation**; unstarted
containers are recreated using retained volumes and checked published bindings.
See [STARTUP-PORT-RECOVERY.md](STARTUP-PORT-RECOVERY.md).

## Connect downloads and library management

Choose **Preview app connections**, then **Apply reviewed connections**. Stackarr tests and creates Sonarr and Radarr download clients pointing to qBittorrent, plus Sonarr and Radarr applications in Prowlarr. Existing connections are preserved; another preview proposes no duplicates. Separate `sonarr` and `radarr` download categories use `/data/downloads/sonarr` and `/data/downloads/radarr`. The library roots are `/data/media/tv` and `/data/media/movies`.

New Docker Arr apps receive unique generated web logins. Choose **Review app login setup**, then **Prepare and save app logins**. In **Your installed app logins**, choose an app and re-enter your Stackarr owner password to reveal its login briefly. You can copy the password; it hides after a minute or when leaving the page. Existing app logins are preserved, and changed credentials are never reset by reveal.

**Choose your sources** links directly to Prowlarr's provider chooser and explains its three steps. If a provider supplies a Torznab feed, the expandable form accepts its address and private key, presents a review, then tests before saving. **Check source sharing** confirms which sources reached Sonarr and Radarr. Provider accounts and source choices remain yours. Adding a source does not request or download media.

Reopen the same helper to reconnect after a host restart. State lives under `%LOCALAPPDATA%\Stackarr\DockerPreview`, outside the extracted package. Keep that directory: it contains ownership receipts, enrollment and configuration. Closing a browser does not remove app data. The preview installs no Windows service and changes no firewall, router or automatic sign-in setting.

Approved folder references persist across controller restarts. Selecting another folder changes only the setup draft for new apps; existing installations keep their paths. Native folder-dialog usability still needs a human walkthrough. Whole-host reconstruction, Stackarr/optional-app updates, clean-machine startup and signing retain their separate release gates.

## Add monitoring and safe cleanup companions

Choose **Add another app**, select Tautulli, Uptime Kuma and/or Cleanuparr, and
review installation. These apps need only their own configuration volumes; no
media/download folders or Docker socket are mounted.

In **Apps**, choose **Review companion setup**, read the changes and choose
**Set up companions**. Tautulli requires an owned, connected Docker Plex server.
Kuma receives TCP service-availability monitors for the owned installed apps;
these prove the ports respond, while Stackarr separately checks authenticated
application APIs. Cleanuparr tests connections to owned Sonarr, Radarr and
qBittorrent with **dry-run on**, queue/download/malware/blacklist jobs off and
both Seeker search switches off. No cleanup job is triggered during setup.

Choose **Finish connecting** to verify and save the three dashboard credentials
privately. **Your installed app logins** reveals a generated local login after
checking your Stackarr owner password. Existing or changed accounts and target
connections are preserved; setup does not reset them. Cleanuparr's Health row
warns when dry-run or an automation switch changes. Enabling cleanup remains a
separate owner decision in Cleanuparr.

Include the new installation in **Backups → Automatic backups** to protect its
configuration and databases. Media requires its own backup. Companion image
updates and whole-host migration still need separate acceptance.

## Start, stop and recover

Open **Apps → Start, stop & recover**, then **Check installation**. A stopped app
offers Start; a running app offers Stop and Restart. Review the notice and approve
the chosen action. Restart can recover a stalled service without recreating its
container or changing its image. Check **Health** afterwards for API readiness.

Actions use exact inspected container IDs and saved ownership receipts. Changed
mounts, images, ports, networks or ownership block the action. If Docker is offline,
open Docker Desktop and refresh; cached installations remain visible. Interrupted
actions are not automatically replayed. Check the apps and saved backups before
reviewing a new action. An interrupted restore may leave apps stopped; its
before-restore safety snapshot is available in Backups.

## Back up and restore Docker apps

1. Open **Backups → Docker app backups** and choose **Review app backup** for an installation.
2. Review the selected apps and downtime notice, then choose **Create backup**.
3. Wait for a succeeded maintenance result and choose **Refresh Docker backups**.
4. To recover app configuration, choose **Review restore** beside the intended snapshot, read the replacement notice, then **Restore snapshot**.
5. Wait for the result and check Health. Apps that were running restart; stopped apps stay stopped.

Snapshots contain app configuration volumes, databases and credentials. They are
encrypted with the controller's existing key; keep the entire controller data
directory, including `state/secrets.key`, ownership database and `state/app-backups`.
A separate encrypted controller database checkpoint preserves host receipts and
credentials for manual host recovery. Normal app restore leaves the active
Stackarr/controller settings databases unchanged. After a manual credential change
outside Stackarr, verify the restored app's connection separately.

Restore is limited to the same owned installation and pinned version. Every archive
is decrypted, checksum checked and validated before downtime. A separate
**Before-restore safety copy** is saved before configuration replacement. Failed
extraction attempts rollback; failed rollback leaves the apps stopped with the
safety snapshot retained. Helpers mount only the exact configuration volume and
private staging folder, with no network or media/download mounts. This follows
Docker's [volume archive approach](https://docs.docker.com/engine/storage/volumes/)
with reviewed app downtime for database consistency.

Media and downloads are **excluded**, preserved in place and never restored by
these controls. Redacted Stackarr settings drafts remain a separate feature.
Whole-host migration and restore across upgraded database versions remain release
work. Same-disk snapshots do not protect against losing that disk. Archives over
20 GiB per app, special files, escaping links and unsupported link chains are blocked.

## Schedule backups and keep a copy on another disk

1. Open **Backups → Automatic backups**. Choose **Choose folder on another disk** and select a dedicated folder in the Windows dialog. Stackarr verifies that it is a different physical disk from the controller's data directory. Browser text cannot grant an arbitrary filesystem path.
2. Select **Back up nightly**, a time in the displayed host timezone, the installations to include and the number of scheduled copies per installation to keep (1–90, default 7).
3. Choose the approved **Backup storage**, then **Review backup plan → Save backup plan**. Choose **Run backup plan now** to verify the destination immediately.
4. Check **Maintenance results** and refresh the backup plan for its last verified result and next run.
5. Open **Save your recovery key**, enter your Stackarr owner password and download the key. Keep it privately in a password manager or separate safe location; the second-disk copies do not contain a plaintext decryption key.

Nightly schedules run while Docker and the controller are running; this preview
does not wake a sleeping computer or install an unattended Windows service. A
missed night runs once after startup. A failed run retains existing snapshots and
retries after an hour. A backup interrupted during execution pauses the automatic
plan and asks you to check app state before enabling it again; it never replays
restore writes. A queued backup interrupted before execution can retry once.

Each complete snapshot is decrypted, checksum checked and archive validated. With
a separate disk selected, encrypted app archives, their authenticated manifest and
the encrypted controller checkpoint are copied into a private installation
namespace. Copy completion and ciphertext checks precede retention. Only older
scheduled snapshots are eligible; manual, before-restore and update/rollback
recovery snapshots are preserved. Retention removes exact owned payload files,
never recursively deletes a user folder, and rejects unexpected files or links.
Automatic off-disk copying covers newly created manual, scheduled and before-restore
snapshots. Existing historical and update/rollback snapshots remain local; their
location is shown in the backup list.

If a local snapshot is missing, normal **Review restore** can use its verified
second-disk copy, with the same ownership/version checks and before-restore safety
copy. A disconnected or corrupt copy fails before app downtime or configuration
replacement. Restoring app data still requires the existing owned installation;
whole-host reconstruction from controller checkpoints remains separate work.
Media and download files are excluded and need their own backup. Network/cloud
destinations and backup-key rotation remain future work.

## Add requests with Seerr

Choose **Add another app**, select Seerr, review and install. Open Seerr, sign in
with Plex and select the intended Docker Plex server and libraries. Return to
Stackarr and choose **Finish connecting**; no Seerr key needs copying for an owned
installation. **Preview app connections** shows the proposed Sonarr/Radarr profile
names and library folders before creating tested Seerr services. Existing service
settings are preserved. Request permissions and approvals remain in Seerr.

The local acceptance completed one original movie and a six-episode season request
through Seerr, local BitTorrent, automatic Arr import and Plex library visibility.
Seerr marked both requests Completed after its supported library scan. No direct
Arr add/grab/manual-import command was used, and existing quality settings stayed
unchanged. Known titles identify test metadata only; files contain colour bars and
silence. The temporary source/seeder were removed/stopped after acceptance.

## Update an app and roll back

1. Open **Apps → Updates & rollback → Check packaged updates**.
2. Choose **Review update** for an available app. Review the current/candidate build and downtime notice, then **Update app**.
3. Follow App action history. Stackarr downloads the exact pinned image while the current app runs, then stops only that app, saves and verifies its encrypted configuration snapshot, recreates the selected service and checks authenticated health.
4. Refresh packaged updates/history after completion. A successful update offers **Review rollback**. Rollback restores the prior image **and its matching configuration**, keeping a safety copy of newer settings first.
5. If an operation was interrupted, choose **Recover interrupted update** in history. Recovery is reviewed and rechecks ownership; unfinished writes are never automatically replayed.

The packaged catalog is reviewed and dated; it is not a live feed of every vendor
release. Updates accept only allowlisted immutable Linux x64 images and compatible
same-major versions. The October candidates update the LinuxServer container builds
for the four download/Arr apps; Plex and Seerr already match their reviewed images.
Major-version migrations and optional-app update acceptance
remain separate work. LinuxServer documents why image updates require
[container recreation](https://docs.linuxserver.io/general/updating-our-containers/).

An update must pass three consecutive authenticated health checks and preserve its
protected settings, library identity/records and connections. Failure restores the
old image and verified configuration snapshot. A failed rollback attempts to recover
the current image/settings from its safety snapshot. If recovery cannot be confirmed,
the operation remains explicit in history and blocks another app operation until
reviewed recovery. Docker context, ownership, environment, volume consumers, mounts,
ports, networks and exact reviewed container identity are checked again.

Rollback rewinds configuration and app metadata to the saved snapshot. Later media
and download files stay in place; newer settings are kept in the rollback safety
snapshot. Recovery snapshots appear in Backups with guidance to use the image/data
rollback controls. Normal data-only restore remains version restricted. Stackarr
never prunes images/volumes or issues media/download deletion commands. Keep the
controller data directory and its encryption key.

## Verified scope

Docker-only tests on the existing Windows computer cover a real browser review, Plex-only installation, host folder mapping, correct Web links, reload persistence and unfinished-account guidance. Separate tests cover the private credential boundary, encrypted storage, duplicate calls, newer settings and rejected credentials. A packaged controller reconnect has preserved the same Plex installation. On 17 October the owner-account setup completed for the isolated Docker server; private connection completion and a repeated check both reached fresh monitoring. The original five-second sample played in the local in-app browser. LAN access, audio, GPU and full-length playback remain unverified.

The extracted `20261016-rc2` ZIP passed a fresh Plex-only walkthrough on 16 October. Its report records the image identity and packaged startup; its executable also passed the frozen-runtime smoke check. Checksums detect changed files; this unsigned private preview does not provide publisher authentication. Windows clean-machine, signed-out reboot and second-device certification are deferred at the owner's request while Docker work proceeds.

The extracted `Stackarr-Docker-Core-Preview-20261017` ZIP subsequently passed a fresh four-app browser walkthrough: packaged startup, installation, private handoff, four tested connection writes, a repeat preview with no changes and fresh monitoring. The live Plex preview also passed adding these apps and restarting their containers with credentials and connections intact. A subsequent packaged walkthrough verified generated Arr logins, owner-protected access, and the guided Torznab form. The local original-media source was automatically shared to both Sonarr and Radarr. Personal provider choices remain separate. A separate seeder then transferred the original generated movie and TV samples to the downloader. Radarr and Sonarr imported them automatically; transferred byte counts, matching SHA-256 files and import history all passed. Only the disposable lab's minimum quality size was relaxed for the highly compressible samples. No actual film or episode was downloaded, and personal providers and imported-file Plex playback remain unverified.

## Maintainer commands

Build the controller using the pinned PyInstaller recipe in `platform/windows/Stackarr.spec`, then build a separately named dashboard image. Create the package with:

```text
python -m tools.package_docker_preview --image stackarr:private-preview --controller-executable dist/StackarrPreview.exe --output dist/Stackarr-Docker-Plex-Preview
```

The package contains only the executable, dashboard image archive, helper, readme, licenses and checksum manifest. It excludes lab media, account passwords, enrollment keys, certificates, databases and Git history. Share it through the approved private distribution path; publication remains governed by PUBLICATION.md.

Run `tools.docker_plex_check --package <extracted-package> --keep-running` with unused explicit lab ports for a fresh packaged walkthrough. This is maintainer test tooling, not a recipient prerequisite. Private `access.json`, controller logs and media fixtures remain under ignored `test-results` and must not be uploaded. `tools.plex_preview_status --finish` completes the connection check after the human account step and reports fresh monitoring separately from installation success.

Run `tools.docker_core_fresh_check --package <extracted-package>` for a fresh four-app acceptance on its reserved test ports. It stops only its owned test containers/controller after success and preserves volumes. `tools.docker_core_check` adds the batch to the designated owned Plex lab; `--verify-existing` avoids another installation during follow-up checks. `tools.docker_core_restart_check` verifies the receipt before restarting that lab's core batch and requires newly collected results afterward.

For the bounded original-media test, retain a fresh four-app lab with
`tools.docker_core_fresh_check --package <extracted-package> --keep-running`, generate
its samples with `tools.make_import_media`, then use `tools.docker_import_check`.
The latter is fixed to the designated test ports and fixture source; it is not a
recipient feature or a real-provider recommendation. Use its separate `prepare`,
`source`, `search` and `flow` phases to inspect failures without repeating a grab.
Test-only quality size floors are relaxed, and known titles are metadata stand-ins.
Preserve evidence and stop only the receipt-verified test containers after acceptance.
