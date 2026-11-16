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
| First name, last name and email | Owner enters directly in the private application form |
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

## Current form fields

The live application form was inspected on 2026-11-16. Use these concise public
answers; keep the longer version/build disclosures above and below as supporting
information, rather than adding release-specific details to the description field.

| Form field | Prepared answer |
| --- | --- |
| Tagline | A local dashboard for setting up and managing a home media stack. |
| Category | Other (there is no media-administration category) |
| Description | Stackarr is an open-source home-media administration application. It guides users through installing and connecting media apps or connecting services they already run, then provides a local dashboard with reviewed configuration, maintenance, backup and recovery tools. Users supply their own accounts and content sources; Stackarr does not supply media or subscriptions. |
| Maintainer type | Individual maintainer(s), subject to owner confirmation |
| Build system | GitHub Actions |
| Privacy policy URL | After merge: https://github.com/FrankieJLyons/Stackarr/blob/main/docs/CODE-SIGNING.md#privacy-and-network-behavior |
| Primary discovery channel | AI / LLM tools, if this conversation was the owner's first introduction |
| Exact discovery source | ChatGPT / Codex, if applicable |
| Company name | Optional; leave blank unless the owner identifies an applicable organization |
| Wikipedia URL | Optional; leave blank |

Required **Reputation** answer, if the owner has no further public evidence:

> Stackarr is newly public and has an initial unsigned 0.1.0 release. We do not
> yet have independent reviews, established adoption or media coverage to cite.
> Our public repository, release history, pull request and GitHub Actions build /
> test evidence are available at https://github.com/FrankieJLyons/Stackarr. We
> understand that technical CI evidence is not a substitute for established
> reputation, and request an eligibility assessment for an early public beta.

Owner input needed before submission:

- Private first name, last name and email for the SignPath account; these can be
  entered directly in the form instead of shared in chat.
- Confirmation of repository ownership, maintainer/reviewer/approver roles and
  GitHub MFA; enable SignPath MFA when the account becomes available.
- Any actual public reviews, community discussions or adoption evidence to add
  to the required reputation answer, or confirmation that none exists yet.
- Review and agreement to the Foundation Code of Conduct and required personal
  data storage/processing consent. Optional marketing consent stays unchecked.

The form includes reCAPTCHA. The owner may need to complete it. This packet does
not accept terms, transmit personal details, create an account or submit the form.
The download field asks for a signing acknowledgement; explain the pending status
and ask how they want it worded before approval, without implying 0.1.0 is signed.

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
