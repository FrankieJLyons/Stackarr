# Code signing policy

## Current status

No publicly trusted signing identity is configured. The public 0.1.0 release and
0.1.1 candidate are unsigned. The prepared SignPath integration remains disabled;
no application approval, certificate or SignPath sponsorship is claimed.

If the Foundation approves the project, the attribution will be:
Free code signing provided by [SignPath.io](https://signpath.io), certificate by
[SignPath Foundation](https://signpath.org). This sentence describes the proposed
arrangement, not an existing service or endorsement.

## People and approval

Committer, reviewer and designated signing approver:
[FrankieJLyons](https://github.com/FrankieJLyons), the repository owner.
External contributions require maintainer review. Each signing request requires
the owner's manual approval in SignPath after checking the source revision,
workflow results and requested files. MFA is required for participating accounts;
GitHub MFA has been confirmed by the owner, and SignPath MFA must be enabled during
onboarding. No automated approval is configured.

## Scope

Only Stackarr's Windows launcher, its generated Inno Setup uninstaller, and the
Stackarr installer wrapper are signing targets. Product metadata must name
Stackarr and match the source release version. Upstream binaries such as Caddy,
Python libraries and application images are not re-signed as Stackarr products.
Bundled dependencies retain their own licenses and notices.

Requests must originate from this repository's GitHub-hosted builds, on `main`,
through an explicit manual workflow run. The signing workflow checks the exact
source revision and accepts only artifacts from that same run. Returned files
must retain their executable contents and carry a valid timestamped signature
from the approved certificate. Checksums are calculated after signing.

The signing workflow produces reviewable candidates. It cannot create a GitHub
release. Signing does not certify playback, Docker configuration, clean-host
installation or the absence of SmartScreen warnings.

## Privacy and network behavior

Stackarr stores its owner account, configuration, encrypted integration secrets,
audit records and backup metadata on the user's host. Its application code does
not include a Stackarr-operated telemetry or crash-reporting service. Do not post
credentials, backups or private diagnostic files in public issues.

Connecting apps enables requests to the configured services. Those requests may
include account credentials, search terms, library information and media requests.
Previously enabled schedules and library discovery can continue in the background
while the controller is running. They are not new consent prompts on every request.
The user can disable the relevant configuration or stop the controller.

Docker prerequisites and app installation can contact vendor download sites and
container registries after review. Plex account connection contacts Plex; catalog
and artwork features can contact the chosen apps and their metadata providers.
Optional secure home-network setup communicates with the chosen local gateway.
These integrations have their own privacy terms, including
[Plex](https://www.plex.tv/about/privacy-legal/) and
[Docker](https://www.docker.com/legal/privacy/). Provider accounts, configured
indexers and other apps are governed by their respective operators' policies.
This is not a claim that third-party software never sends telemetry.

See [licensing and bundled components](LICENSE-NOTES.md),
[candidate installer behavior](https://github.com/FrankieJLyons/Stackarr/blob/codex/windows-startup-installer/docs/WINDOWS-INSTALLER.md) and
[security reporting](../SECURITY.md).
