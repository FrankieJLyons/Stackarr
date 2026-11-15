# Download protection and Plex library mapping

Open **Apps → Safer downloads, in the right library** (also available in Setup's
connections step). Both features show a preview before saving. Imported native
apps stay read-only.

## Download protection

**Check & preview protection** reads the connected qBittorrent settings, retains
the existing exclusion patterns and proposes executable/script exclusions. The
default also excludes archives and disk images; turn this option off if you need
legitimate archived releases. This does not remove exclusions you already had.

Applying enables filename exclusion and disables the external-program hooks for
added and completed torrents. The stored command strings, network settings,
passwords, existing torrents and their file priorities are preserved. Settings
are read back after saving. **Saved changes** offers recovery, including after
a lost response; recovery refuses to overwrite subsequent edits. Restoring also
restores the previous automatic-program switches.

The filter applies to new torrents when filenames become known. It is **not an
antivirus or a guarantee of zero malicious bytes**: media can be disguised or
malicious, and torrent pieces can span both selected and skipped files. Keep the
OS and players updated and never execute downloaded programs. Existing queued
torrents are not retroactively filtered.

Cleanuparr remains optional. Its deletion jobs and dry-run settings are not
changed. If its blacklist-sync job is enabled or cannot be checked, Stackarr
stops this protection setup because that job may replace qBittorrent's list.

## Downloads into existing Plex libraries

1. Finish connecting your downloader and writable Sonarr/Radarr installations.
   Use **Preview app connections** to connect them if needed.
2. Connect a claimed Plex server. **Find native app settings** can now import the
   current Windows user's already signed-in Plex connection and library folders,
   without copying its account token or changing Plex.
3. Choose **Detect TV library** or **Detect movie library**. A unique matching
   library folder is selected automatically; multiple libraries or locations
   require an explicit choice.
4. Review the staging → Arr import folder → Plex library route, then save it.

The host controller checks recorded installation receipts and current container
IDs, mounts, ports, context, runtime state and real host directories. A matching
path string alone is insufficient. It translates shared host folders into each
container's path and rejects missing, linked, unshared, read-only, overlapping or
shadowed locations. Downloads and library folders must be separate.

Existing dedicated `sonarr` / `radarr` categories must point to verified staging
folders. Stackarr tests the matching saved download client. If needed, the review
enables **Use category paths in Manual Mode** for new downloads; it does not
toggle automatic management or relocate existing torrents. This preference
applies to all qBittorrent categories and is shown explicitly in the preview.

Missing Arr roots can be added after review. Completed imports can be enabled
only when the Arr queue is empty, checked again before writing. Existing media
records, root folders, files, custom categories and connections are preserved.

The saved mapping supplies the folder for **new requests through Stackarr** and
rechecks the selected library, Plex identity, mounts, downloader and Seerr's
actual Arr identity before submitting. Adding or removing an unrelated Plex
library leaves that explicit mapping usable; moving or removing the selected
folder still blocks the request. Existing shows keep their current folder. Requests made directly in
Seerr or other tools retain those tools' defaults. **Pause Stackarr folder
override** restores use of those defaults; it does not delete roots or revert
application settings. Partial setup is recorded and can be re-reviewed safely.

For writable Plex connections, a missing Arr Plex notification can be tested and
created, including verified path translation. Existing notifications are kept.
Native Plex remains read-only: its scan settings remain in place, and a manual
scan may be necessary if automatic detection was not already enabled. No claim,
new Plex library, file move, delete, search, or request is issued by this setup.

An existing native Plex folder outside the installed apps' reviewed mounts is
detected but **not automatically mounted**. Share that storage deliberately when
planning the installation; Stackarr does not reconfigure a running stack's mounts
or grant an isolated test installation access to the working media library.

## Verification on 2026-10-21

- Real isolated qBittorrent 5.2.4: a private, trackerless, stopped synthetic torrent
  selected MKV/subtitle files and skipped EXE (including uppercase and double
  extensions), PowerShell and RAR names. Zero downloaded bytes; only that test
  torrent was removed. Previous settings were restored and verified, then the
  reviewed protection was enabled in the isolated downloader.
- Real isolated Sonarr/Radarr and qBittorrent accepted the staging configuration
  and mapping. The initial positive Plex case used an explicit claimed-library
  protocol fixture while the isolated server was unclaimed. The actual unclaimed
  server correctly blocked mapping. The real-server follow-up below supersedes
  that earlier playback limitation.
- Native Windows Plex identity and its two library folders were read and verified
  without mutation. The UI refuses to map them into the isolated apps because
  their real media storage is not shared.
- Regression coverage includes stale/session-bound previews, native write blocks,
  credential changes, partial saves, recovery, category drift, ambiguous libraries,
  nested mounts, notification tests, and lazy database initialization.
- Original native Arr fingerprints, native Plex identity/libraries and all 17
  protected container identities, start times, restart counts, mounts and ports
  remained unchanged.
- Final validation: **1,032 Python tests passed, 3 skipped; 87 JavaScript tests
  passed**, plus browser smoke and desktop/phone acceptance. The packaged update
  succeeded in the isolated dashboard on port 29480; its authenticated host RPC
  verified both owned Docker storage and native Plex library evidence. The source
  preview on port 29490 retains the previous quality rules and includes this flow.

### Real download-to-playback follow-up

After the owner claimed the isolated Plex server on port 42401, the complete
local pipeline passed against the real applications:

1. Account completion created the real Movies and TV libraries and connected
   the isolated Seerr using the owner's completed Plex sign-in.
2. Library mapping verified the running installation receipts and shared storage,
   selected the actual Plex folders and created the missing import notifications.
   Reviewed automatic import discovery was also enabled.
3. Stackarr Home submitted a movie and TV-season request with the mapped roots.
   Prowlarr supplied a private local test source; a separate seeder supplied
   original generated colour bars and silence. Known title names were used only
   to exercise metadata matching, not to acquire those films or episodes.
4. qBittorrent transferred 4,332,168 movie bytes and 1,088,379 episode bytes.
   Radarr and Sonarr imported both automatically. Imported SHA-256 hashes matched
   the generated originals, and each Arr import history referenced the exact
   torrent hash. No manual import or manual Plex scan was used.
5. Real Plex discovered both files automatically. Stackarr confirmed the movie
   as available and the TV season as partially available, with links to the
   correct isolated Plex server.
6. Plex Web played both 720p samples for 12 seconds each. Chromium decoded 17
   frames per sample with zero dropped frames and no video error; the real Plex
   sessions endpoint independently reported each item as playing. Browser network
   guards blocked access to the working Plex servers.

The small generated fixtures needed a temporary, lab-only 720p minimum-size
override; those original limits were restored. The temporary source was removed,
the two helper containers and exact test torrents were stopped, and the test
titles were left unmonitored. Imported samples remain available in the isolated
Plex. Download protection remains enabled. The original 17 protected container
records and native Arr/Plex fingerprints were unchanged.

That initial run was a local 720p playback smoke test. The subsequent
[quality-rule acceptance](QUALITY-RULES.md#real-end-to-end-verification--2026-10-21)
also verified SD, 1080p and full-resolution 4K SDR/H.264 playback. A subsequent
[HEVC/HDR10 playback check](QUALITY-RULES.md#hevc-and-hdr10-playback-verification--2026-10-21)
verified full-resolution HEVC/HDR10 delivery in Edge and H.264/SDR fallback in
Chromium; Chromium's automatic quality reduced the 4K sources to 2276×1280.
The subsequent [Dolby Vision/HLG checks](QUALITY-RULES.md#dolby-vision-hlg-and-format-preference-acceptance--2026-10-21)
verified Profile 5 refusals, Profile 8.1 playback, HLG-to-SDR fallback, and the
new Dolby/10-bit/codec download preferences. The subsequent
[AV1 acceptance](QUALITY-RULES.md#av1-download-and-playback-acceptance--2026-10-30)
completed four preference-driven downloads and imports, verified the Seerr
profile-cache fix, and played each imported file in both browsers. AV1 4K/10-bit
files remained intact, but Plex Web converted them to 2276×1280, 8-bit H.264.
Physical HDR-display output, remote
and TV-device playback, sustained streaming and antivirus effectiveness remain
unverified. Private
evidence is retained under `test-results/fresh-review-20261020/`, including
`download-to-playback-report.json`, the scoped acceptance scripts, and the
`playback-fixture-state/plex-playing-*.png` captures. No production deployment or
published package was changed during this follow-up.

Protocol references: [qBittorrent API implementation](https://github.com/qbittorrent/qBittorrent/blob/master/src/webui/api/appcontroller.cpp),
[qBittorrent filename filtering and category paths](https://github.com/qbittorrent/qBittorrent/blob/master/src/base/bittorrent/sessionimpl.cpp),
[Sonarr qBittorrent requests](https://github.com/Sonarr/Sonarr/blob/develop/src/NzbDrone.Core/Download/Clients/QBittorrent/QBittorrentProxyV2.cs),
[Cleanuparr blacklist sync](https://cleanuparr.github.io/docs/configuration/blacklist-sync/),
[Cleanuparr malware blocker](https://cleanuparr.github.io/docs/configuration/malware-blocker/).
