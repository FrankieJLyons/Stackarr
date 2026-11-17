# Unsigned 0.1.1 candidate testing

The owner selected unsigned beta testing on 2026-11-17. Public 0.1.0 remains the
released version. This candidate is for acceptance testing; signing is disabled
and publication of 0.1.1 remains a separate decision after the results are reviewed.

## Download the tested candidate

[Download the complete unsigned candidate](https://github.com/FrankieJLyons/Stackarr/actions/runs/43921837030/artifacts/14254629162)
from the [successful hosted build](https://github.com/FrankieJLyons/Stackarr/actions/runs/43921837030).
GitHub sign-in may be required. The artifact is approximately 723 MB and expires
on **2026-11-23**. It was built from commit
`287f10233d281673eccb7c20df89dcf2d6ddf778`; later documentation-only changes do not
change these binaries. If it expires, request a new hosted build rather than use
an unrelated launcher or synthetic installer fixture.

Extract the downloaded artifact ZIP. For the installer test, open:

`dist/installers/Stackarr-0.1.1-Windows-x64-Setup-unsigned.exe`

Its adjacent `.exe.sha256` file gives the installer checksum. To display the
downloaded installer's SHA-256 from that folder:

```powershell
Get-FileHash -LiteralPath .\Stackarr-0.1.1-Windows-x64-Setup-unsigned.exe -Algorithm SHA256
```

Compare it with the adjacent checksum before running. The executable is unsigned;
Windows may show an unknown-publisher or reputation warning. Record the prompt and
make the trust decision yourself; do not disable Windows security protections.

The same artifact also contains `dist/Stackarr-0.1.1-Windows-x64.zip`, the portable
alternative. Its SHA-256 is
`cf2b0fcdda60dece509afe941a88dbee7e4f2fe8810953a0c9511d757380d9b1`.
Test one installation route at a time. For the new installer/startup acceptance,
start with the installer, not the portable ZIP.

## First run

1. Run the installer as the intended ordinary Windows user. It installs under
   `%LOCALAPPDATA%\Programs\Stackarr` and adds Start menu entries. It must not need
   administrator privileges or enable startup automatically.
2. Open **Stackarr** from the Start menu. Follow readiness, create a new local
   account, and review the chosen apps, folders and ports before installation.
3. Choose a new empty test media folder and a distinct test Plex server name.
   Leave the regular media stack running. Do not import/migrate its configuration,
   select its media folders or change its Docker settings for this test.

An existing Windows/Docker host can test fresh Stackarr state; it cannot prove
clean-Windows prerequisite installation. Use a spare/disposable Windows 11 host
for prerequisite, sign-out and reboot tests. Do not reboot the household server
merely to complete the checklist. Mark unavailable checks **not run**.

If installation finds an existing unrelated directory or old Stackarr state,
record that result before attempting cleanup. Do not reset Docker, prune shared
resources or remove media to manufacture a clean test.

## Test record

Version / source commit: 0.1.1 / 287f10233d281673eccb7c20df89dcf2d6ddf778  
Environment: existing host with fresh Stackarr state / disposable Windows 11  
Windows and Docker versions:  
Selected apps and test media folder (redact private paths when sharing):  
Installer checksum matches:  
Assistance needed:

| Check | Expected result | Pass / fail / not run | Sanitized observation |
| --- | --- | --- | --- |
| Installer | Per-user install and Start menu shortcuts; startup stays off; no implicit Docker/app changes. | | |
| First launch | Readiness and account setup work without Python or a source checkout. | | |
| Prerequisites | On a clean test host, vendor setup and any prerequisite reboot return to actionable readiness. | | |
| Review and install | Only reviewed apps, fresh test folders and available ports are used; regular services remain usable. | | |
| Account and libraries | Connect the intended test Plex server, test libraries and selected apps through the checklist. | | |
| Movie and TV | With permitted test content, independently verify request, transfer, import, library visibility and playback. | | |
| Existing media | If selected, an owned test sample plays without requiring a download source. | | |
| Reopen | Close/reopen Stackarr; account, configuration and progress are retained. | | |
| Startup opt-in | After successful setup, Startup settings clearly enables and disables current-user sign-in startup. | | |
| Sign-in / reboot | On the chosen test host, saved runtime resumes after sign-in with Docker ready; no availability before sign-in is promised. | | |
| Docker unavailable | On a disposable host only, startup waits within its bound and reports an actionable status; manual reopening recovers when Docker is available. | | |
| Uninstall | Removes installed launcher/shortcuts and its unchanged startup entry; settings, Docker apps, media and unrelated files/entries remain. | | |
| Regular stack | Existing apps, ports, data and media remain unchanged. | | |

Uninstall preserves Docker applications and runtime data by design. It is not a
full Stackarr runtime reset. Runtime removal, if wanted later, needs its separate
reviewed flow. Keep failed test state for diagnosis.

Report the first failing step, expected and actual behavior, and a short sanitized
error. Keep credentials, tokens, recovery keys and raw configuration exports out
of screenshots and public reports. A green container is not a playback pass.

## Release decision

Review blockers, unrun checks and any effects on unrelated apps before publishing
0.1.1. The hosted checks already cover Windows installation/registration/removal,
the frozen launcher, and fresh-runner image import/service startup. They do not
replace Windows 11 onboarding, actual sign-in/reboot or real account/playback tests.
Public certificate approval is deferred for this unsigned testing route. Signature
verification remains mandatory for any future artifact advertised as signed.
