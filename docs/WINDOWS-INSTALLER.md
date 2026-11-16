# Windows installer and sign-in startup candidate

Unreleased preparation for 0.1.1. The public 0.1.0 ZIP and its limits are unchanged.

## Intended user flow

The installer places the complete verified package in the current Windows user's
local application directory under `Programs/Stackarr`. It adds Start menu entries
for Stackarr, Startup settings and Recover Stackarr. It does not require elevation,
install Docker, change firewall/certificates, start apps, or enable automatic startup.
Open Stackarr and complete the existing reviewed setup process.

After setup, open **Startup settings** from the Start menu, or reopen Stackarr's
readiness window and choose **Review startup settings**. Choose **Enable at sign-in**
in the local window. Configure Docker Desktop's own start-at-sign-in setting separately.
If this is the first startup review, Stackarr verifies the running installation
and records its release and saved ports before enabling startup.

Startup waits for the local Linux Docker engine and resumes the saved Stackarr
dashboard/controller without opening a browser. It does not install apps, replay
pending maintenance recovery, start the optional HTTPS gateway, change other startup
entries, or promise service availability before Windows sign-in. Unavailable Docker,
changed packages and recovery requirements produce a redacted local status record.
Open Stackarr manually to resolve them. Turn startup off in the same local window.
Moving/changing the launcher package requires reviewing startup again.

## Installation and removal boundaries

- The target is fixed to the current-user application directory; linked directories
  and existing directories without an installer receipt are rejected.
- Only the enumerated, hash-verified package files are copied. Extra source files
  cannot enter the installer. Repeat installation preserves untracked files.
- Windows uninstall removes the installed launcher, shortcuts and its unchanged
  default-installation startup entry. Runtime state, backups, Docker apps and media
  remain. Use Stackarr's reviewed runtime-removal flow separately when appropriate.
- Startup settings use one installation-specific value in the current user's Run
  registry key. Modified/unrecognized values are preserved. No scheduled task or
  Windows service is created, and Docker's settings are not changed.
- Compatible runtime updates still use Stackarr's existing reviewed update/rollback
  mechanism. The installer is not a replacement for runtime/data migrations. After
  replacing an installed launcher, review startup again to accept its new executable.

## Build an unsigned candidate

Use a complete package created by the matching source revision's Docker packager.
The package must contain the new launcher and `signin_startup: 1` metadata. Do not
add that flag to a 0.1.0 binary: it does not contain the startup commands.

```powershell
python -m tools.build_windows_installer --package dist/Stackarr-Candidate --output dist/installer --version 0.1.1 --compiler 'C:/Program Files (x86)/Inno Setup 6/ISCC.exe'
```

The result is explicitly named `Stackarr-0.1.1-Windows-x64-Setup-unsigned.exe`, with
a SHA-256 file and metadata declaring `signed: false`. It remains an unsigned
candidate until separate release acceptance is complete.

## Signing gate

The publisher must provision a publicly trusted code-signing identity. No signing
identity is configured by these changes. The builder can use Windows SDK SignTool
with a selected certificate already present in the publisher's certificate store;
it does not import, export or store private keys.

Sign and timestamp the launcher **before** producing its package manifest. Then
pass `--certificate-sha1`, `--sign-tool` and `--require-signed` to the builder. It
checks the launcher's valid Authenticode signature and expected certificate,
configures Inno Setup to sign the uninstaller and installer, and verifies the final
installer's signer and timestamp. Missing identity or invalid signatures fail the
build instead of falling back to an unsigned artifact. Signing does not guarantee
the absence of Windows reputation prompts.

[Microsoft signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)
and [Docker sign-in settings](https://docs.docker.com/desktop/settings-and-maintenance/settings/)
describe the external prerequisites. A cloud signing provider needs its own reviewed
authentication/signing integration before it can replace this certificate-store path.

## Acceptance

Unit checks cover opt-in, registry ownership, revocation during readiness waits,
bounded retry, changed packages, unconfigured/removed state, redacted failures and
manifest-only staging. The hosted Windows acceptance compiles and installs a
synthetic package, exercises real current-user registration, rejects an unrelated
destination, repeats installation, and uninstalls while preserving sentinels and an
unrelated startup entry. It never launches a Docker stack.

Still required before publishing 0.1.1: exact candidate package startup with real
Docker, clean Windows installation, real sign-out/sign-in and reboot, human native
dialog checks, signed artifact validation with the chosen publisher, and the
[fresh-user walkthrough](BETA-WALKTHROUGH.md). Hosted Server 2025 evidence is not
Windows 11 recipient certification or before-sign-in support.
