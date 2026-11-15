# Recommended app settings

Research reviewed 14–15 November 2026. Recipe version `2026-11-14.1`.

Stackarr now has **Settings → Recommended settings**. Choose Sonarr or Radarr,
preview a recipe, then apply it. These are deliberately simple Stackarr recipes,
not full TRaSH Guide profiles or a guide synchronization service.

## Quality recipes

| Recipe | Use | Behaviour |
| --- | --- | --- |
| Everyday 1080p · recommended | A starting point for an HD library | 1080p HDTV, WEBRip, WEB-DL and Blu-ray encodes |
| Smaller 720p | Prioritise a lower resolution | The corresponding 720p sources; no fixed size guarantee |
| High resolution 4K | A separate, deliberate choice for tested players | Corresponding 2160p sources; no remux or full-disc downloads |

Each recipe creates or reuses only the dedicated profile it needs. It resolves
quality IDs against the connected app's schema, excludes CAM, workprints, disc
images and remuxes, leaves codec and language preferences alone, and disables
quality/custom-format upgrades in that profile. A uniform recipe uses the same
resolution for every release year, including an unknown year. It does not
automatically downgrade older films or series. Title exceptions are replaced in
the preview; users can cancel or customize before saving.

The recommended 1080p choice and disabled upgrades are Stackarr product decisions:
an approachable HD starting point with fewer repeat downloads. They are not
universal best settings. Existing global proper/repack processing remains in the
app's control. A resolution restriction does not establish release quality,
bitrate, language, audio format, HDR support or a storage budget.

Saving affects **new requests made through Stackarr**. Requests made directly in
Seerr, Sonarr or Radarr continue to use those apps' own defaults. Existing title
assignments require a separate library preview and apply. No search, file move,
transcode or deletion is started by saving a recipe.

The preceding Stackarr policy is saved in an encrypted, transactional snapshot.
**Preview restore previous rules** rechecks the app connection, settings revision
and profiles before the normal reviewed apply. A first-time save can be restored
to paused rules. Created profiles remain available; restoring request rules does
not undo separate library assignments, which have their own per-title undo.

## Research and tradeoffs

- [Sonarr profiles · TRaSH Guides](https://trash-guides.info/Sonarr/sonarr-setup-quality-profiles/)
  and [Radarr profiles · TRaSH Guides](https://trash-guides.info/Radarr/radarr-setup-quality-profiles/)
  prioritise quality-oriented sources and distinguish profiles by user needs.
  Stackarr's smaller recipes do not reproduce their release-group scoring,
  format collections, quality merging or language recipes. Prefer a purpose-built
  profile for anime or a specific language. Codec labels alone are not a reliable
  quality ranking; do not universally prefer HEVC or AV1 for every player.
- [Servarr's Sonarr settings](https://wiki.servarr.com/sonarr/settings) explain
  upgrades and cutoffs. Enabling upgrades can fetch a better eligible release
  later. Stackarr leaves that choice available in custom upstream profiles.
- [Sonarr file sizes · TRaSH Guides](https://trash-guides.info/Sonarr/Sonarr-Quality-Settings-File-Size/)
  describe size thresholds as a preference, with different needs for animation.
  Quality definitions are app-wide. These recipes preserve them, rather than
  silently applying large quality-first limits to every existing profile.

## The other apps

| App | Preferred starting point | Available control |
| --- | --- | --- |
| qBittorrent | Media filename exclusions; disable automatic external program hooks; optionally exclude archives | Preview/apply safeguards and durable undo in Stackarr. Existing exclusions retained; current torrents unchanged. |
| Sonarr / Radarr / Plex | Verified shared paths, separate TV/movie download categories and completed import routing | Existing reviewed library connection tool, linked from Recommended settings. |
| Prowlarr | Add and Remove Only when preserving per-app indexer choices is important | Guidance and Open app. Full Sync is appropriate when intentionally managing those indexer settings centrally. |
| Plex | Consider keeping unavailable entries in the library; avoid costly thumbnails until wanted | Guidance and Open app. No automatic server preference changes. |
| Seerr | Request permission, deliberate quotas, manual approval initially; grant 4K and automatic approval deliberately | Guidance and Open app. No automatic permission changes. |
| Cleanuparr | Observe first, then reviewed safeguards, recovery or completed cleanup | [Version-checked presets](CLEANUPARR-PRESETS.md), dry-run apply, independent live confirmation and encrypted settings recovery. |
| Tautulli | Establish viewing statistics first; add notifications and scripts deliberately | Guidance and Open app. |
| Uptime Kuma | Local availability monitors with a tested notification and deliberate interval | Guidance and Open app. |

The following are supporting product documentation, not an endorsement of every
upstream default:

- [qBittorrent's official WebUI API](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-(qBittorrent-5.0))
  documents the exclusions and external-program preferences used by the existing
  safeguards tool. Filename filters are not antivirus. Seeding targets, deletion,
  speed limits, interface binding and authentication are preserved.
- [Prowlarr settings](https://wiki.servarr.com/prowlarr/settings) explain the two
  sync modes and the settings Full Sync can replace. Prowlarr does not synchronize
  download clients into the library apps.
- [Plex library settings](https://support.plex.tv/articles/200289526-library/)
  describe library trash behaviour and the CPU/storage costs of preview thumbnails.
  Keeping trash entries is useful while removable or network storage is unavailable;
  it is a library database preference, not an instruction to retain torrent files.
- [Seerr user settings](https://docs.seerr.dev/using-seerr/settings/users/)
  document default permissions and quotas. Changes to new-user defaults do not
  retroactively change existing accounts.

## Verification

Tests cover recipe application to both apps, actual schema IDs, selected profile
creation only, preservation of existing profiles and titles, restart-persistent
restore snapshots, stale/replaced-connection rejection, encrypted snapshots,
session/CSRF requirements and single-use review tokens. Browser checks exercise
the preview/apply/restore flow against isolated synthetic apps, never household
libraries. Imported read-only apps cannot receive preset writes.
