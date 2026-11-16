# Changelog

## 0.1.1 — unreleased candidate

- Added opt-in current-user startup after Windows sign-in, bounded Docker readiness
  waiting, quiet saved-runtime resume and redacted failure status.
- Added a per-user installer with Start menu shortcuts, explicit owned-path checks
  and uninstall preservation of settings, Docker apps, media and untracked files.
- Added publisher-signature/timestamp checks and explicit unsigned artifact names;
  signed builds require a provisioned publisher identity and cannot fall back silently.
- Prepared a SignPath application, code signing policy and disabled GitHub signing
  integration, including launcher/uninstaller/installer handoffs and PE metadata.
- Added a hosted complete-package build with current launcher/dashboard, the
  unchanged pinned Seerr dependency, real unsigned installer, revision/hash checks
  and fresh-runner image loading and isolated service smoke checks.
- Added hosted Windows installation/registration/removal acceptance and readiness
  browser coverage. Startup before Windows sign-in remains unsupported.
- Reconciled the roadmap and added a released-package fresh-user walkthrough.

This candidate is not yet a public release. Clean Windows 11, actual sign-in/reboot,
exact-package Docker startup and publisher-signing acceptance remain release gates.

## 0.1.0 — public beta

- Added the media control room, app catalog, responsive setup checklist and appearance preferences.
- Added existing-app discovery and read-only Windows native connection imports.
- Added independent app completion, recommended quality presets, year/title rules,
  download safeguards, library mapping and reviewed Cleanuparr presets.
- Included the Windows launcher, Docker readiness flow, dashboard, patched Seerr
  image and experimental HTTPS home-network helper in one download.
- Retained reviewed installation, encrypted configuration backup/recovery,
  owned-app maintenance and compatible Stackarr update/rollback flows.
- Prepared a clean source history, checksums and explicit beta acceptance limits.
  The executable is unsigned; clean-host, second-device and reboot acceptance
  remain user test steps. See `docs/BETA-0.1.0.md`.

## 0.1.0a1 — private preview

- Added schema migrations, encrypted webhook destinations and validated import drafts.
- Added durable connection checks, operation history and persistent notification retries.
- Added optional Seerr monitoring, capability-scoped activity and explicit partial counts.
- Added storage layout previews, local API discovery hints and verified deployment receipts.
- Bound connection writes to expiring, single-use reviewed plans.
- Added configuration backup verification, draft restore previews and durable scheduling.
- Added unsaved-change protection and contextual help.
- Added deterministic source packaging, broader audits, dependency inventory, shared
  browser CI and an actual Windows executable smoke gate.

- Added a responsive Stackarr dashboard with Overview, Activity, Health, onboarding, and Settings views.
- Added versioned validation, encrypted credentials, sessions, CSRF protection, audit events, redacted exports, and backups.
- Added read-only collectors for Plex, Sonarr, Radarr, Prowlarr, qBittorrent, Tautulli, and Uptime Kuma metrics.
- Added scoped Docker Compose planning, host preflight checks, resumable apply/stop/rollback, and platform support guidance.
- Added synthetic API tests, browser smoke tests at desktop and phone viewports, source/history scanning, dependency audit, and container build configuration.
- Cleanuparr detailed status, automatic recovery, download deletion, replacement search, native platform installers, and public releases remain planned or experimental.
