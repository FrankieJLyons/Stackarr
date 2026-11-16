# SignPath application packet

Prepared for owner review; **not submitted**. Use the
[SignPath Foundation application](https://signpath.org/apply) after completing the
owner-only fields and confirming the eligibility questions below. Never put an
API token, private key or personal identity document in this repository.

## Project details to copy into the application

| Field | Prepared answer |
| --- | --- |
| Project | Stackarr |
| Repository and home page | https://github.com/FrankieJLyons/Stackarr |
| Downloads | https://github.com/FrankieJLyons/Stackarr/releases |
| License | Apache-2.0 for Stackarr; bundled components retain their own licenses |
| Public release | 0.1.0, unsigned Windows x64 ZIP |
| Candidate | 0.1.1, per-user Windows installer and opt-in sign-in startup |
| Maintainer account | https://github.com/FrankieJLyons |
| Requested certificate | SignPath Foundation OSS certificate, subject to their approval |
| Proposed roles | FrankieJLyons: committer, reviewer, signing approver |
| Signing policy | `docs/CODE-SIGNING.md` (publish the reviewed policy before submission) |
| Contact name and email | Owner enters directly in the private application form |
| MFA / authority confirmation | Owner confirms directly; not verified by this preparation |

Suggested project description:

> Stackarr is an Apache-2.0 home-media administration application for Windows 11
> x64. It guides users through selecting, installing and connecting media apps,
> or connects to apps they already run. It provides a local dashboard, reviewed
> configuration changes, encrypted configuration backups, maintenance and recovery.
> It does not supply media or provider subscriptions. The current public beta is
> an unsigned ZIP; version 0.1.1 adds a per-user installer and optional Windows
> sign-in startup. We request signing for our launcher and generated installer /
> uninstaller, built on GitHub-hosted runners. Each request will require a
> maintainer's manual approval. Stackarr is newly public; we are not claiming an
> established user base or prior Foundation approval.

## Disclosures and eligibility questions

Send these as part of the application, not as assumptions that eligibility is met:

- The launcher is a PyInstaller executable containing Stackarr, Python/Tcl/Tk,
  Python dependencies, static assets and a pinned Caddy binary. Only the outer
  Stackarr executable is a signing target. The dependency inventory currently
  covers Python requirements, not every native component or Docker image.
- The full package includes the Stackarr Docker image and a separate modified
  Seerr image. Seerr's MIT notice, patch files, pinned upstream inputs and build
  recipe are included. Ask the Foundation whether this distribution and the
  Seerr modifications meet its upstream/fork requirements. No signature over the
  Seerr image itself is requested. The hosted 0.1.1 build preserves the exact
  reviewed Seerr image from the checksummed public 0.1.0 ZIP, verifies its digest
  and patch labels, and records that dependency origin. It rebuilds the Stackarr
  dashboard and launcher; it does not claim to rebuild Seerr in that run. Confirm
  that this dependency provenance is acceptable to the Foundation.
- Plex and Docker Desktop are optional separately downloaded proprietary software,
  not included in the signed payload. Stackarr facilitates their reviewed setup
  and account connections. Ask whether these optional integrations are acceptable
  under the Foundation's OSS criteria.
- Stackarr can configure user-selected indexers and download clients. Users supply
  their own accounts and content sources. Describe this accurately; do not present
  Stackarr as only a passive media-library viewer.
- The installer format is new in the 0.1.1 candidate. The Foundation requires a
  release in the form to be signed; confirm whether the existing ZIP/launcher is
  sufficient for initial approval and what installer sample/release they need.
- The public repository has a short, clean history. Provide actual public releases,
  CI and source evidence; do not invent download counts, reputation or external
  reviews. Acceptance remains the Foundation's decision.

Component evidence: [LICENSE-NOTES](LICENSE-NOTES.md),
[`requirements.lock`](../requirements.lock),
[`platform/seerr`](../platform/seerr),
[`caddy.lock.json`](../stackarr/caddy.lock.json), and the Windows build's
`python-dependencies.cdx.json`, `build-metadata.json`, and `runtime-smoke.json`.

## Before submission

1. Owner reviews the description, role assignments and privacy statement and
   enters a private contact name/email. Confirm MFA for GitHub and SignPath.
2. Merge the reviewed public policy and integration preparation; keep signing
   disabled. Link the policy from the README and future release notes. Do not
   edit the historical 0.1.0 release to imply it is signed.
3. Attach or link the [complete hosted build](HOSTED-PACKAGE.md), its unsigned
   installer/ZIP, exact source revision and verification report. Download the
   samples before their seven-day Actions retention expires. The separate
   installer rehearsal artifact contains **reports only**; its synthetic Docker
   payload is not an end-user installer sample.
4. Submit the disclosures above and wait for eligibility feedback. This packet
   prepares the answers; it does not submit the application or accept terms.
5. Complete [onboarding](SIGNPATH-INTEGRATION.md) only after acceptance. A successful
   unsigned hosted package build does not establish SignPath approval or trust.

References checked during preparation:
[Foundation requirements](https://signpath.org/terms),
[GitHub integration](https://docs.signpath.io/trusted-build-systems/github), and
[artifact configuration](https://docs.signpath.io/artifact-configuration/).
