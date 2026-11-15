# Fresh installation

This path is for a new machine with no existing media applications. It starts with only Stackarr. The guided browser setup then lets the owner choose any subset of applications, using existing-app connections only when the owner adds them later.

## Local launcher path (current preview)

1. Start the private Windows executable from a build containing the October 6 installer work. The build metadata identifies the exact source revision.
2. Keep Docker Desktop running with Linux containers. Installing Docker or its prerequisites is still a separate vendor-guided step.
3. Approve the matching browser code in the launcher and choose your Stackarr password. This is a local control-panel password; no email or Stackarr online account is needed. Use **Show password** if helpful, then **Continue to setup**.
4. Choose only the apps you want. For each app, choose a new installation or an existing connection. Leave **Advanced installation options** closed unless you need a particular port.
5. Use **Choose a folder** in the local launcher, or enter an existing dedicated data folder. Save and run the host checks. Use **Use available ports in my plan** to suggest unused local ports. Review the changes; availability is checked again before installation.
6. Review the apps, ports, shared folder and proposed new folders. **Download & install these apps** is the explicit installation approval.
7. Follow saved progress. Known temporary image-download failures get up to three attempts. A failed installation preserves data and requires **Resume installation**; app writes are not retried silently after a restart.
8. Review and apply app connections in the wizard. Existing entries remain unchanged. New Sonarr/Radarr libraries and encrypted Arr/qBittorrent credentials are prepared during installation.
9. Finish Plex sign-in/claim, Seerr setup, Arr UI accounts, source selection and quality preferences in their respective apps. Return to **Finish connecting** for newly installed Plex and Seerr: Stackarr verifies and privately saves their connection details, without asking you to copy a key or token. If account setup is incomplete, the page explains what remains. Your generated qBittorrent login can be viewed after re-entering your Stackarr password; it is hidden after 60 seconds or leaving the page.
10. In Apps, use **Check installation** to verify container settings without changing them. Matching running/stopped containers offer separately reviewed stop/start actions; they preserve volumes and media. Test saved connections and review Health. Media acquisition, importing and Plex playback still need an end-to-end acceptance test before calling a household setup ready.

New installations currently support Plex, Sonarr, Radarr, Prowlarr, qBittorrent and
Seerr on x64. Other apps remain optional existing connections. Selected new apps
receive a separate Compose project, network, configuration volumes and loopback
ports. No Docker socket is mounted in the dashboard. Closing the launcher stops
Stackarr's local web server, not the installed media containers.

For existing-app choices, **Review existing app connections** lets you save the
reviewed addresses, then enter credentials in Apps. Existing saved settings and
credentials are preserved; this is not a migration or adoption workflow.

The read-only `stackarr host-check <reviewed-plan.json>` command now accepts the entire wizard download (or a plain configuration export). Run it on the intended installation computer. It reports a settings fingerprint, timestamp, scope, and actionable checks. It refuses known container environments and remote/unverified Docker contexts, and never starts an installation. The wizard's **Save & check installation computer** button is wired to the same service; checks remain disabled on the ordinary web server until the local launcher explicitly supplies host access (`create_app(host_checks=True)`). Do not enable this on a remote dashboard. Passing preflight does not certify service-account permissions, Plex playback, LAN HTTPS or startup before sign-in.

Build a portable source release with `python tools/package_release.py`. The resulting ZIP contains the Docker files, application, guides, Windows bootstrap, tests, and checksum; it excludes `outputs/`, runtime state, virtual environments, generated artifacts, secrets, and certificates.

## Developer container-dashboard path

1. Install Docker Engine or Docker Desktop with Compose v2 and Linux containers, following the vendor's instructions for Windows, Linux, macOS, or the NAS platform. Stackarr does not install Docker, enable router access, or add firewall rules.
2. Unpack a reviewed Stackarr release into an empty directory and start the control center:

   ```text
   copy .env.example .env
   docker compose up -d --build
   ```

3. Open Start Stackarr from the release folder. It opens the password-creation page automatically; no setup code is entered. See [Docker setup](DOCKER-SETUP.md).
4. In the wizard, select only applications you want to install. Choose a single existing host data folder before selecting Plex, Sonarr, Radarr, or qBittorrent.
5. Download the generated plan, run `stackarr preflight <config.json>`, and only then run `stackarr prepare <config.json> <empty-install-directory>` followed by `stackarr apply <empty-install-directory>` on the Docker host.
6. Complete each upstream application's first-run setup yourself: Plex claim and library choice, qBittorrent password, Arr root folders and quality profiles, Prowlarr indexers, Seerr permissions, and any Cleanuparr automation. Stackarr never preselects indexers, imports credentials, enables destructive cleanup, or exposes a service publicly.

The initial Stackarr container binds to loopback. Configure a trusted LAN reverse proxy only after local setup works; follow [NETWORKING.md](NETWORKING.md).

## Windows bootstrap

The newer [local launcher preview](LOCAL-LAUNCHER.md) opens the wizard and uses local approval instead of manual setup-token copying. Its executable recipe is prepared but not yet certified on a clean machine. The PowerShell flow below remains a developer-only alternative.

On a new Windows machine, unpack the release and use the plan-first bootstrap from a normal PowerShell window:

```powershell
.\platform\windows\Install-StackarrFresh.ps1 -SourceRoot $PWD -InstallRoot C:\ProgramData\Stackarr\App
```

It reports whether Docker Compose and the target directory are ready. After reviewing that plan, add `-Apply`. It copies the release to the selected machine-owned directory, creates a loopback-only `.env`, and starts only the Stackarr container. It does not create tasks, services, firewall rules, certificates, downloads, media folders, or media applications.

To remove a fresh control-center installation, stop it from its install directory with `docker compose down`. This preserves the named Stackarr data volume unless the owner explicitly removes that volume later. Do not use an unreviewed recursive deletion command.

## Acceptance checks

- The Stackarr login page is reachable at localhost and cannot be reached from another machine before a reverse proxy and firewall scope are deliberately configured.
- The local launcher uses matching-code approval; it does not ask the user to locate or copy a setup token. The Docker starter opens a short-lived, single-use invitation automatically; the browser removes it from the address and exchanges it for an HTTP-only setup cookie.
- A configuration with only one selected app produces a plan containing only that app.
- Preflight rejects an occupied port, a missing/insufficient data folder, an unavailable Docker daemon, or a non-Linux container engine.
- Applying a plan creates only the Stackarr-owned Compose project. Stopping it preserves media and volumes.

Prepared deployments now contain a receipt with the redacted settings, adapter
schema, selected images and exact plan digest. Lifecycle actions reject changed
plans or mismatched project ownership before contacting Docker. Change settings and
prepare a fresh reviewed plan instead of editing `compose.json` directly. Older
unreceipted experimental plans are not adopted automatically. Rollback checks its
previous receipt and preserves volumes; it is not a database-schema rollback.
Apply no longer removes orphan containers automatically. This older CLI plan path uses upstream tags. The local wizard instead uses the
reviewed image digests in `stackarr/images.lock.json`; these are distinct paths.

The old `Install-StackarrWindows.ps1` native migration experiment is now plan-only.
Its unverified junction replacement and rollback mutations have been removed.
`-Apply` and `-Rollback` fail before reading configuration or inspecting tasks.
This does not disable the separate fresh Stackarr control-center bootstrap.
