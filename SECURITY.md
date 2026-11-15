# Security policy

The public beta is not an internet-facing service. Default access is loopback-only.
For experimental trusted-LAN access, use the reviewed HTTPS home-network helper
and device certificate-trust steps. Do not expose Stackarr or its apps to the public internet.

Please report suspected vulnerabilities privately to the repository owner before publishing details. Include the version, deployment type, reproduction steps, and whether credentials or external application changes are involved. Do not include secrets or personal media information.

The beta uses password sessions, CSRF checks, same-origin enforcement, rate-limited sign-in, encrypted credentials, masked logs, redacted support bundles, and a restrictive container profile. Review the threat model before enabling host-management or destructive automation features. Report vulnerabilities using GitHub's private vulnerability reporting for this repository.
