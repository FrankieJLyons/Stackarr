# Cleanuparr presets

Recipe version `2026-11-15.1`, verified against Cleanuparr **2.10.11** and its
[tagged source](https://github.com/Cleanuparr/Cleanuparr/tree/v2.10.11).

Open **Settings → Recommended settings → Cleanuparr presets**, then **Check
Cleanuparr**. **Observe first** is selected by default. Updating Stackarr does not
apply a preset or change an existing Cleanuparr configuration.

| Preset | Reviewed changes |
| --- | --- |
| Observe first | App-wide dry-run; queue checks every 15 minutes; six failed-import/error checks; private downloads ignored; metadata-timeout removal and forced import off. Other jobs paused; existing stall/slow definitions retained. |
| Media safeguards | Existing qBittorrent exclusions retained and extended with executable/script patterns, optionally archives; external program hooks disabled. Cleanuparr jobs paused and dry-run on. |
| Recover stuck downloads | Observe settings plus a public-only stalled rule: twelve checks, progress resets, up to 95% completion. Requires an HTTPS outage-check URL or configured check URLs, matching library sources and no active pre-existing stall/slow rules. |
| Clean completed downloads | One public-only seeding rule for a verified post-import category; both chosen ratio and minimum seeding hours required. Maximum-time override disabled. Source files retained by default. Download Cleaner hourly; other jobs paused. |

Six/twelve checks, 15 minutes, and the editable ratio 2 / 72-hour starting values
are Stackarr product choices, not universal upstream recommendations or tracker
requirements. Existing queue pattern filters are retained. An empty Include
filter is changed to Exclude with an empty list because Cleanuparr rejects an
enabled failed-import rule with no included patterns. An app-specific strike
override must be removed in Cleanuparr before using the queue recipe.

## Dry-run and live cleanup

Every normal preset apply enters and verifies **app-wide dry-run first**, before
creating rules or enabling scheduled checks. It pauses unrelated Cleanuparr
jobs while retaining their definitions, connections, ignored downloads, log
settings, authentication and certificate preferences. It does not start an
immediate cleanup task. Previously running work cannot be undone by a setting.

Dry-run applies to Cleanuparr. The Media safeguards recipe deliberately changes
qBittorrent's handling of **new torrents immediately**, including private torrents.
Existing torrents retain their file selections. Filename filtering is not
antivirus and does not examine media content. Cleanuparr blacklist sync must be
off so it cannot replace these exclusions. No external blocklist is downloaded.

Only an applied recovery/completed recipe offers **Review live cleanup…**. This
creates a second, session-bound preview showing the actual scope and thresholds.
The user must check the irreversible-action acknowledgement and type exactly
`ENABLE LIVE DELETION`. The normal apply endpoint rejects a live-review token;
the live endpoint requires both confirmations, fresh configuration and unchanged
connections. Live operation may affect downloads already eligible in the client.

Observe first cannot grant live deletion. Media safeguards work in qBittorrent
without turning Cleanuparr live. Replacement searches and orphan/unlinked/dead
cleanup remain disabled in these recipes. Private torrents are excluded from the
recovery and completed-cleanup rules.

## Completed-import prerequisites

The selected qBittorrent client in Cleanuparr must match Stackarr's downloader.
Sonarr/Radarr must have completed-download handling enabled and an enabled
qBittorrent connection to that same endpoint. The post-import category must:

- already exist in qBittorrent;
- be configured as `tvImportedCategory` or `movieImportedCategory` in the library
  app's download-client settings;
- differ from every active-download category found across those library apps.

If no category qualifies, the button is disabled with setup instructions. This
release does not automatically change library-client categories or relabel
existing torrents. Manually putting a torrent in the category can defeat this
signal: it is a configuration check, not independent inspection of library files.

Existing seeding rules or enabled orphan/unlinked/dead cleanup block the completed
recipe. Existing active stall/slow rules block recovery. Their definitions are
preserved; users can review them in Cleanuparr or restore the preceding recipe.
Recovery is limited to one matching qBittorrent client in Cleanuparr and in each
connected library app; mixed-client queues need manual rules. These downstream
connections are rechecked at the live-deletion gate.
Other Cleanuparr versions are blocked pending adapter verification.

## Recovery and failure handling

Stackarr records each operation in an encrypted journal **before** sending it.
Every write is read back. Lost replies become an uncertain result with recovery
available; Stackarr does not blindly retry. Rule IDs and contents, app bindings
and setting revisions are checked. Subsequent app edits are preserved rather
than overwritten by restore. Changes also appear in Stackarr's audit log.

**Preview restore in dry-run** restores settings changed by that saved operation
and removes unchanged rules it created. It always leaves Cleanuparr in dry-run,
including when restoring previously live preferences. qBittorrent safeguards have
their selected settings restored only if they still match the saved change.
**Restoring settings cannot restore deleted torrents or files.**

The mode shown in Health distinguishes dry-run observation from live cleanup.
The existing companion setup wizard still requires its original paused safe
mode before changing connections; it will not reset a preset silently.

## Upstream references

- [General / dry-run](https://cleanuparr.github.io/docs/configuration/general/)
- [Queue Cleaner and outage checks](https://cleanuparr.github.io/docs/configuration/queue-cleaner/)
- [Download Cleaner and ratio/time semantics](https://cleanuparr.github.io/docs/configuration/download-cleaner/)
- [Malware Blocker](https://cleanuparr.github.io/docs/configuration/malware-blocker/)

The latest documentation can describe capabilities absent from the pinned app.
Stackarr uses its verified API contracts, rather than assuming all current
documentation applies to every version.
