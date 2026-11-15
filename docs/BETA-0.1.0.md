# Version 0.1.0 beta acceptance

This beta targets Windows 11 x64 and Docker Desktop with Linux containers.
The release ZIP includes the executable and images needed to start Stackarr;
selected upstream apps download their pinned images during reviewed installation.

## New-user walkthrough

- Download the Windows ZIP and its checksum from the public GitHub release.
  Extract into a new permanent folder. Do not reuse an old Stackarr data directory.
- Open Start Stackarr.cmd and check Docker readiness. Complete any vendor setup
  prompts, then continue. Existing Docker/media installations must remain working.
- Create a new local password. Choose a small app set or Movies & TV, use an empty
  media folder and automatic ports, and review installation before applying.
- Complete Plex sign-in yourself. Give the test server a distinct name. Prepare
  libraries and requests through the Stackarr checklist, then connect a source
  you are authorized to use. Check movie and TV searches separately.
- Request permitted test content. Confirm download, import, library visibility,
  request status and actual playback on your intended device. Catalog visibility
  alone is not a successful download or playback check.
- Close and reopen the launcher: the account, settings and checklist should resume.
  Restart Windows and reopen Docker/Stackarr manually. Unattended startup before
  sign-in is not provided or certified by this release.
- Optionally test an encrypted configuration backup and its recovery-key handling
  using only the disposable test apps. Media requires its own backup.
- Optionally test Home network & recovery on another device. Trust the generated
  public certificate on that device and verify the configured HTTPS address.
  Firewall rules, device trust and local name resolution are host responsibilities.

## Reporting a problem

Use the public repository's issues. Include the release version, Windows/Docker
versions, selected apps, the failing checklist step and sanitized error text.
Do not attach databases, recovery keys, API keys, provider credentials, setup URLs,
raw logs or screenshots containing private media/account information.
Security concerns should follow SECURITY.md rather than a public issue.

## Release criteria and limits

Automated checks cover source lint, Python and JavaScript regression tests,
synthetic browser flows, source privacy scanning, dependency audit, source/wheel
builds and a frozen Windows runtime smoke check. These checks do not certify
personal Plex/provider accounts, playback codecs, network access or every host.

The Windows executable is unsigned. LAN setup and whole-host recovery are beta
features; do not use the first walkthrough to replace a working household stack.
Imported native apps remain read-only. Managed migration, macOS/NAS/ARM installers,
automatic firewall/router configuration and internet hosting are out of scope.
