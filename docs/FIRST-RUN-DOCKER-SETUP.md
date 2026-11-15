# Docker prerequisite setup and preview cleanup — 19 October 2026

The main Windows Docker preview now includes this reviewed prerequisite flow;
see [integrated first run](INTEGRATED-FIRST-RUN.md). The standalone artifact and
earlier verification recorded below remain useful for focused prerequisite tests.

Open **dist/Stackarr-Readiness-Preview-20261019-r3/StackarrReadiness.exe**.
The ZIP is **dist/Stackarr-Readiness-Preview-20261019-r3.zip**, SHA-256:

```text
b114155ab2dff6e333e3dc61c6cb07c6dbc13f5238d9adc823d371562b294186
```

## Installation experience

When Docker is missing, choose **Install Docker Desktop**, review the changes
and choose **Download & install**. The page displays progress and allows download
cancellation before the native installer opens. Docker installs for the current
Windows account through the documented `install --user` route. Follow the vendor
prompts, open Docker Desktop from Start and choose **Check again**. Docker terms
are left to the user; Stackarr does not accept them or issue a reboot command.

The pinned official release is **4.95.0**, build **242831**, **636,811,696 bytes**.
Its published SHA-256 is:

```text
73431db38491f770543880366228a23c993f84d1e8e045f56d83b8a98940cf76
```

The downloader enforces the approved HTTPS host, size and time limits. Both the
checksum and a Valid Windows Authenticode signature for organization **Docker
Inc** must pass. A Windows file handle prevents replacement between verification
and process creation. Existing Docker executables/installed-app records refuse
fresh installation. Review expires and is revalidated immediately before starting.

A separate per-user journal and OS operation lock prevent duplicate installation.
Interrupted jobs never automatically rerun the installer. The user must review
again and confirm any earlier installer is finished/closed. A required restart
is recorded explicitly. Progress writes serialize with reads and retry bounded
Windows sharing denials while preserving the last complete record.

Sources: [Docker installation](https://docs.docker.com/desktop/setup/install/windows-install/),
[release notes](https://docs.docker.com/desktop/release-notes/) and the
[official checksum file](https://desktop.docker.com/win/main/amd64/242831/checksums.txt).
Full implementation/build notes remain in [FIRST-RUN-READINESS.md](FIRST-RUN-READINESS.md).

## Verification

- **91 focused tests pass**, including native Windows payload locking, publisher
  checks, review/replay/eligibility gates, cancellation, interruption, duplicate
  windows, sharing-denial retry and protected HTTP input/authentication.
- **11 readiness browser cases** and **5 prerequisite browser cases** pass. The
  latter verify review without side effects, approved download/cancel, verification
  before simulated installation, restart guidance, reopening without reinstall
  and acknowledgement after interruption. Desktop and phone screenshots were inspected.
- **12 frozen executable smoke checks pass outside the source checkout**, using
  synthetic prerequisite bytes/signature/installer results. The frozen executable
  also passes actual current-host readiness and absent-Docker-discovery reports.
- The actual official **637 MB installer was downloaded**, hashed and checked by
  Windows Authenticode. Its checksum and publisher pass. It was **not executed**.
  The temporary test payload was removed after recording verification.
- The actual existing-Docker review is refused before creating prerequisite state.
- The ZIP/payload allowlist and source snapshot hashes pass. Its 15 source inputs
  contain only readiness and read-only Docker/network modules. A focused 20-file
  source audit has **0 findings**. Ruff passes.

Private evidence is under **test-results/first-run-readiness/**:
**installer-final-tests.xml**, **docker-browser-r3/**, **browser-r3/**,
**frozen-installer-r3/**, **docker-download-verification.json** and
**installer-package-verification.json**. No real Docker installation, Windows
feature enablement, elevation, reboot or clean-PC certification was performed.
Automatic WSL/Windows feature setup and real installation/reboot acceptance remain
separate work on a disposable Windows machine.

## Docker Desktop cleanup

After the Seerr chat completed its checks, the cleanup removed **44 stopped
Stackarr test containers** and **20 empty owned networks**, using exact resource
IDs and a fresh state check before each removal. No force removal, global prune,
volume deletion or image deletion was used.

All **11 running services**, including the working nine-app installation and
unrelated service, retained their original running container IDs. All **238 data
volumes** and all images were retained. Backups and host/media folders were not
modified. The remaining container list has **11 containers**.

Before removal, container/network recreation definitions were encrypted and saved
under **test-results/first-run-readiness/docker-cleanup/**. Retain
**container-recovery.key** with **container-definitions.encrypted** privately;
they include sensitive configuration needed for recreation. The filtered inventory,
exact reviewed plan and **cleanup-result.json** are retained alongside them.
These files are ignored private evidence and are not in the readiness package.
