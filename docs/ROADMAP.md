# Stackarr roadmap

Updated 16 November 2026. This is the current delivery plan after the [0.1.0 public beta](https://github.com/FrankieJLyons/Stackarr/releases/tag/v0.1.0). Older planning documents describe historical baselines; their unchecked boxes are not a current missing-feature list.

## Available in 0.1.0

| Area | Shipped scope |
| --- | --- |
| Windows package | Extract-and-run launcher and dashboard; recipient Python is not required. Windows 11 x64 and Docker Desktop with Linux containers. |
| Setup | App presets, independent saved checklists, reviewed installation, automatic ports, generated app logins, and guided account/source connections. |
| Apps | Plex, Seerr, Sonarr, Radarr, Prowlarr and qBittorrent; optional Tautulli, Uptime Kuma and Cleanuparr. |
| Everyday use | Control room, health/activity, browsing, requests, quality presets/title rules, and verified Plex handoff. |
| Existing installations | Discovery and read-only native connection import; existing apps are not adopted for lifecycle management. |
| Maintenance | Encrypted configuration backups, reviewed restore, owned-app repair/removal, compatible updates and rollback. Media is not included in backups. |
| Home network | Experimental reviewed HTTPS setup with a bundled gateway. Device trust, firewall access and name resolution remain host responsibilities. |
| Presentation | Responsive layouts, themes, contextual help and reviewed cleanup presets. |

Shipped does not mean certified on every host. The [beta checklist](BETA-0.1.0.md), [release review](https://github.com/FrankieJLyons/Stackarr/releases/download/v0.1.0/beta-review.json) and [support evidence](SUPPORT.md) define the tested boundaries.

## Next: candidate 0.1.1

This is a proposed maintenance release, not a published version or a delivery-date promise.

| Priority | Work | Current status | Required completion evidence |
| --- | --- | --- | --- |
| 1 | Fresh-user acceptance and fixes | Awaiting the released-package walkthrough | Complete [the walkthrough](BETA-WALKTHROUGH.md), record blockers and retest fixes on the candidate artifact. |
| 2 | Reliable return after Windows sign-in | Implemented on the 0.1.1 candidate branch; physical acceptance pending | Opt-in, removable startup registration; bounded wait for Docker; quiet reuse of the existing installation; recovery from unavailable Docker; no unrelated startup changes. |
| 3 | Conventional Windows installation | Candidate per-user installer and hosted acceptance; not released | Stable owned application/state locations, shortcuts, upgrade/rollback behavior, uninstall preservation and clean-Windows acceptance. |
| 4 | Publicly trusted signing | Publisher signing identity/service required | Verify Authenticode identity and timestamp on executable and installer; signing failure must prevent a release being labeled signed. |
| 5 | Current documentation | Reconciled here | README, roadmap and release limits agree; historical evidence stays labeled. |

Docker Desktop documents automatic start **at sign-in**. A sign-in startup feature must not be advertised as unattended boot before sign-in. The latter remains a separate runtime feasibility and physical acceptance gate. See [Docker settings](https://docs.docker.com/desktop/settings-and-maintenance/settings/) and the [Windows runtime lab](WINDOWS-RUNTIME-LAB.md).

Signing requires a publisher-controlled certificate or signing service and identity validation. Do not use a self-signed test certificate as a substitute for public trust, or promise the absence of Windows reputation warnings. See [Microsoft's signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options).

See [Windows installer candidate](WINDOWS-INSTALLER.md) for implementation, signing inputs and remaining validation.

## Acceptance still required

- Clean Windows prerequisites, vendor prompts and prerequisite-reboot recovery.
- Personal Plex/provider sign-in and the exact released request/download/import/playback journey.
- Another household device, certificate trust, network access, audio and subtitles.
- Real second-account household permissions and revocation.
- Replacement-Windows configuration recovery and native folder/recovery dialogs.
- Uncoached novice walkthroughs and full keyboard, screen-reader and zoom review.
- Physical sleep/reboot behavior; unattended startup before sign-in needs its own supported runtime evidence.

Earlier engineering reports demonstrate specific builds and isolated cases. They do not automatically close these gates for a new public release.

## Later work, separately scoped

- Supported Linux delivery and named macOS/NAS/ARM platforms after platform-specific acceptance.
- Reviewed migration/adoption of existing native installations.
- Broader storage/backup destinations and major-version migration coverage.
- Additional household access and recovery improvements.

Automatic public internet exposure and router configuration are outside the current beta scope. Playback remains Plex's responsibility; Stackarr is not a replacement media player.

## Historical plans

[Product vision](PRODUCT-PLAN.md), [one-download plan](ONE-DOWNLOAD-PLAN.md), [completion ledger](COMPLETION-PLAN.md) and [0.2 usability plan](UX-0.2-PLAN.md) retain historical decisions and evidence. Use this roadmap for priorities and the versioned release notes for shipped capabilities.
