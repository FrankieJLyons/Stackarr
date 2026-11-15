# Windows migration and verification

## Current state and risks

The original repository snapshot is a useful record of a working Windows stack, but it is not a portable installer. Its `outputs/` files combine a specific machine's paths, ports, scheduled task names, gateway settings, and recovery policies. Some of those recovery routines can restart applications, remove downloads, clear blocklist data, or start a replacement search. They remain reference material only and are excluded from the Stackarr package.

The portable application now keeps configuration and credentials separate, uses read-only status collection, preserves last-known data visibly as stale, and produces scoped Compose plans. It does not control the live Windows host, scheduled tasks, services, Caddy, firewall, certificate store, or downloads. Docker is unavailable on the development host, so a real container run still needs verification in an isolated environment.

The remaining migration risks are practical rather than theoretical: task registration can break boot-before-login behavior; a Caddy change can break LAN access; a mistaken path mapping can affect imports; and a backup on the same disk cannot recover a disk failure. Treat each as a staged migration with a rollback, never as an in-place conversion.

## Additive migration plan

1. **Inventory only.** Record each application's launch mechanism, executable, data path, account, health URL, gateway route, firewall scope, and backup inclusion. Do not import credentials or replace a running registration.
2. **Deploy a machine-owned runtime.** Use the plan-first Windows runtime tool from `platform/windows/` to copy a versioned payload outside the checkout. It changes only a `Runtime` junction after manifest validation and retains the immediately previous release for rollback.
3. **Observe.** Point Stackarr at existing applications using explicit URLs and credentials entered through Settings. Confirm every app reports either fresh, stale, unavailable, or authentication-failed status. A missing optional app is hidden unless enabled.
4. **Verify the gateway separately.** Render and validate any future Caddy configuration in staging; test localhost and a second LAN device; confirm certificate-trust guidance on each client; only then switch a gateway task. Keep the last known Caddy config available for immediate rollback.
5. **Migrate one startup registration at a time.** A task must run from the machine-owned runtime, have a non-interactive principal, and have a documented stop/restart test. Do not enable autologon. Reboot and leave Windows at the sign-in screen before marking the migration complete.
6. **Enable guarded operations last.** Storage Guard may pause only explicitly selected managed categories and resume only items it marked. Backups require a restore test. Recovery begins with observation, retry, resume, and rollback; no deletion, blocklisting, or replacement search is automatic.

## Reboot-without-login acceptance test

- Export Stackarr settings and create a native-app configuration backup before changing startup.
- Reboot, do not sign in, and wait through the configured stagger window.
- From a second trusted LAN device, check the gateway certificate, dashboard, and each enabled application health endpoint.
- Verify the task history has no interactive-window, duplicate-process, or credential failures.
- Confirm the dashboard distinguishes gateway failure, API authentication failure, unavailable application, and stale data.
- Confirm Storage Guard did not touch manually managed torrents and recorded no action unless its configured threshold was crossed.
- Sign in only after the remote checks; inspect application logs and verify no browser opened automatically.
- Exercise the documented rollback before declaring the new registration production-ready.

## Backup and trust guidance

Configuration backups should exclude media, torrent payloads, transcode data, artwork caches, and logs unless a user deliberately changes that policy. Keep a short local retention for recovery from mistakes, and optionally copy encrypted configuration backups to an SMB/NFS share or S3-compatible bucket to cover drive loss. Record a checksum and restore-test result.

For a Caddy `tls internal` deployment, distribute only the public local root certificate through an authenticated local channel. Import it into the Windows trusted-root store for Windows clients, the system trust store on macOS/Linux where appropriate, and the browser-specific store for Firefox when it does not use the system store. NAS client guidance varies by vendor. Never distribute Caddy's private key or its data directory.
