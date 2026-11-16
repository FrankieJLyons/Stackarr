# Complete hosted Docker package

The **Complete Docker package** workflow builds an unsigned 0.1.1 candidate. It
does not publish a release or change the public 0.1.0 download. All Docker commands
run on disposable GitHub-hosted Linux; Windows assembly uses an offline image
handoff. The helper refuses Docker operations on local or self-hosted machines.

## Run and download

In GitHub Actions, choose **Complete Docker package → Run workflow**, select the
reviewed branch, and leave **sign** false. Packaging changes also run this workflow
on pull requests. Require the entire run to succeed before using its artifacts.

Download `unsigned-complete-docker-package`. Inside it:

- `dist/Stackarr-0.1.1-Windows-x64.zip` and its SHA-256 file contain the portable
  launcher, dashboard and pinned Seerr images, scripts, documentation and manifest.
- `dist/installers/Stackarr-0.1.1-Windows-x64-Setup-unsigned.exe` and its checksum/
  receipt contain the actual complete package, not a synthetic installer fixture.
- `build/images/image-build.json` records the image IDs, image archive checksum,
  source commit, resolved dashboard base and prior-release dependency checksum.
- `build/launcher/dist/` contains launcher provenance, frozen smoke results and
  the Python dependency inventory. The inventory does not cover every native or
  container dependency.

Download `complete-package-verification` for the fresh-runner check report. These
artifacts last seven days; intermediate images last one day. Artifacts are
unsigned test candidates, not an approved public release. GitHub may require
sign-in to download Actions artifacts.

## Inputs and verification

The Windows build runs the existing full tests and frozen launcher smoke check.
Linux builds the current dashboard with revision/version labels. It resolves the
Python base image to a digest and records the exact base used. This is provenance
evidence, not a claim of byte-for-byte reproducibility.

Seerr remains `3.5.0-stackarr.2` at the digest in `bundled-images.lock.json`. Its
image archive is recovered from the public 0.1.0 ZIP specified in
`platform/docker/release-inputs.lock.json`. Both the release ZIP hash and inner
archive hash are checked, then Docker's immutable reference, architecture and
patch labels are verified. Only the current dashboard tag and reviewed Seerr tag
are exported. The old dashboard is never included. Seerr is not rebuilt in this
run; a Seerr update needs its own reviewed source/build and lock change.

Windows verifies the image receipt, source revision, catalog and archive checksum,
and the launcher's source revision and checksum, before assembling the package.
It re-runs the frozen launcher self-test and builds Inno Setup from the verified
manifest payload. No Docker engine is needed on the Windows runner.

A separate Linux job validates the finished ZIP's exact file list and hashes,
loads its image archive with Docker's containerd image store, rechecks image IDs,
the Seerr digest and labels, and the dashboard source label. It starts each service
with network access disabled, no host/media mounts, and temporary configuration
storage. It checks dashboard health and the running Seerr version, then removes
only those fixture containers.

This proves assembly, import and isolated service startup. Windows 11 Docker
Desktop onboarding, actual sign-in/reboot and the [fresh-user walkthrough](BETA-WALKTHROUGH.md)
remain release acceptance tasks.

## Optional signing

After [SignPath onboarding](SIGNPATH-INTEGRATION.md), an explicit main-branch run
with `sign: true` uploads a separate same-run package artifact. Successful assembly
and fresh-runner verification are prerequisites for the protected signing job.
Launcher, uninstaller and installer signing each require manual SignPath approval.
No test fixture or locally uploaded binary is substituted for this package.

The workflow uses Docker's documented
[containerd setup for GitHub Actions](https://docs.docker.com/build/ci/github-actions/multi-platform/)
to preserve immutable image references across export/import.
