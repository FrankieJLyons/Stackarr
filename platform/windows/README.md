# Native Windows runtime (preview)

This directory is the source for an optional native Windows runtime. It is for an existing Windows media server that cannot, or should not, move its applications into containers. It is not run by Docker Compose and it does not alter a machine merely because this repository is cloned.

`Install-StackarrWindows.ps1` is plan-first. With no `-Apply` switch it validates a JSON settings file and prints the files it would stage. With `-Apply`, it copies only this directory's `runtime` payload into a new versioned release directory, validates the staged manifest, then changes the `Runtime` directory junction. The prior release is retained for rollback. It never points a scheduled task at the repository checkout.

The first preview deliberately does **not** take over existing application services or scheduled tasks. Existing Plex, Arr, qBittorrent, Tautulli, Kuma, and Caddy registrations are discovered and reported as external. A later, separately reviewed migration can create only tasks explicitly marked `create: true`; it must not replace an existing task. This protects a working pre-login server while its startup behavior is verified.

Copy `stackarr.windows.example.json` outside the checkout, fill in only the components you own, and keep it private. It contains no credential field. Put API keys and passwords in Stackarr's encrypted settings store or the Windows credential vault, never in this file. See [../../docs/WINDOWS-MIGRATION.md](../../docs/WINDOWS-MIGRATION.md) before using it.

```powershell
# Review only
.\platform\windows\Install-StackarrWindows.ps1 -SourceRoot $PWD -ConfigPath C:\Secure\stackarr.windows.json

# Apply after reviewing the printed plan and a successful staged validation
.\platform\windows\Install-StackarrWindows.ps1 -SourceRoot $PWD -ConfigPath C:\Secure\stackarr.windows.json -Apply

# Roll back the Runtime junction to the immediately previous release
.\platform\windows\Install-StackarrWindows.ps1 -ConfigPath C:\Secure\stackarr.windows.json -Rollback
```

The scripts do not change autologon, power policy, Windows crash behavior, firewall rules, router settings, certificates, application settings, downloads, media, or backups. Each of those requires an explicit, reviewed future adapter or a documented manual step.
