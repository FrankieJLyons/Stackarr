# Local launcher preview

The Windows Docker release now uses the main executable for readiness and reviewed
Docker prerequisite setup before opening its Docker dashboard. Start with
**Start Stackarr.cmd**; see [integrated first run](INTEGRATED-FIRST-RUN.md).
**Connect apps I already run** opens the local launcher described below, retaining
its matching-code approval and separate per-user data. The standalone executable
without a Docker package and the developer command keep their existing behavior.

Implemented: a local setup window that starts Stackarr on a reserved loopback socket, opens the browser, and enables explicit local prerequisite checks. First-run setup pairs the browser with the local window using a matching six-digit display code. The actual authorization secret is a short-lived HTTP-only cookie; it never appears in a URL. The local window approves a request, and authorization expires after two minutes or account creation. Approval only permits creating the first account; normal login is still required.

The ordinary container/web deployment retains its existing setup-token flow. Local approval endpoints do not operate there. The launcher stores progress in the platform's per-user application-data folder, not in the executable's temporary extraction directory or checkout. Closing the window stops this preview server and preserves saved data. This is not an unattended Windows service or a complete media installer.

The native folder chooser selects an existing directory without saving or installing anything. Folder selection requires an authenticated browser request with CSRF protection and is unavailable on a remote dashboard. The native dialog still needs a human acceptance check on a disposable Windows desktop.

## Developer launch

From the repository with its existing dependencies and Tk available:

```text
python -m stackarr.launcher
```

This command opens a visible window and writes per-user Stackarr state. Automated tests instead use temporary state, simulated approval, and loopback-only fixtures. No live media system is needed.

## Windows artifact

The manual `Windows launcher preview` GitHub Actions workflow builds `StackarrPreview.exe` and its SHA-256 checksum. It does not create a public release. Build recipe: `python -m PyInstaller platform/windows/Stackarr.spec` with the pinned build dependency listed in the workflow. [PyInstaller spec documentation](https://pyinstaller.org/en/stable/spec-files.html) describes inclusion of the static assets and embedded runtime.

Verified preview: [Windows build 37410377863](https://github.com/FrankieJLyons/MyMediaStack/actions/runs/37410377863), application revision `74bb87a`. All **227 tests passed on Windows and Linux**. The actual downloaded executable matched both its checksum file and build metadata, then passed its temporary-data self-test locally. That check initialized the bundled installer and app-action journal, Tcl, the new Plex/Seerr connection module, credential encryption, loopback authentication boundary and clean shutdown without Docker calls. SHA-256:

```text
af16a70341527f705877d2be3ffe3aaba40c5fd322ac4f6028f38b25237c077b
```

The private Actions artifact is named `unsigned-windows-launcher-preview` and is
retained for seven days. It includes `dist/StackarrPreview.exe`, checksum, source
archive and build metadata. Older `6b33ef0` artifacts predate the Plex image fix and
must not be used for fresh Plex installation.

This is an unsigned private preview. The self-test installs no apps and is not a
fresh-machine or native-dialog acceptance test. Signing, publisher identity,
Docker prerequisites, startup/service installation, upgrade/rollback/repair/removal and
clean-machine certification remain release work. Use the build metadata to
identify the exact revision; later application changes require a new executable.


## Acceptance walkthrough

1. On a disposable Windows machine without Python, launch the private preview artifact.
2. Confirm it opens the local page and does not request administrator rights.
3. Request approval in the browser; confirm the code matches the native window before approving.
4. Choose a local Stackarr password, try Show password, and select Continue to setup. Verify no terminal command, email registration or token copying was needed.
5. Save a draft, close the window, reopen, sign in, and verify Resume setup restores progress.
6. Verify an unapproved second browser cannot create an account and expired approvals are rejected.
7. Verify closing the launcher stops only its own server and preserves data.

The launcher installs selected Docker apps only after the explicit browser review. It does not install Docker, register Windows services, change firewalls, create certificates or restart Windows. See [FRESH-INSTALL.md](FRESH-INSTALL.md) for the current wizard walkthrough.

The preview workflow rebuilds for changes anywhere in the application, tests or
packaging tools. Its download includes the executable checksum, clean source ZIP,
build revision and environment inventory, complete project license, and a Python
dependency CycloneDX report generated by [pip-audit](https://github.com/pypa/pip-audit).
Dependency-audit failures block artifact upload. The report does not yet inventory
native Python/Tcl/Tk libraries or third-party application images. Code signing,
complete binary attribution, broader platform/image certification and clean-host validation
remain public-release requirements.
