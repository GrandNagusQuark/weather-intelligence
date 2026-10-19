# Security

Weather Intelligence is in public alpha. Report suspected vulnerabilities through
GitHub private vulnerability reporting:
https://github.com/GrandNagusQuark/weather-intelligence/security/advisories/new.
The repository has private vulnerability reporting enabled. Do not use a public
issue for credentials, personal locations, household configuration or details
that could expose other installations.

## What to include in a private report

Describe the affected version, expected behavior, observed behavior and a small
reproduction using synthetic data. Explain whether the issue affects account
permissions, alert delivery, location handling or stored data. Do not send real
warning simulations to other users to demonstrate a problem.

## Security boundaries

The authenticated panel checks the acting account and limits ordinary users to
their own choices. Administrators can help manage another account. Such saves
queue a notice identifying the administrator. A local settings comparison can
detect some changes outside the normal save path. Neither safeguard can stop a
server owner from replacing code, modifying stored records or disabling checks.

Do Not Disturb bypass also depends on phone permissions and platform behavior.
An earlier confirmed test is not proof of current operating system permission.

The optional reporting sender accepts a reviewed HTTPS destination and sends only
fixed diagnostic fields. The project service relays to a private receiver on the
maintainer's server. The distributed Cloudflare template remains disabled and
contains no live service credential. Treat received reports as untrusted input,
not proof of an installation's identity. A shared secret embedded in public client
code would not provide that proof.

Outage contributions use separate consent and random installation identifiers.
These are pseudonymous and can be fabricated or regenerated. Distinct identifiers
are not proof of distinct people. Source checks must corroborate a cluster before
an outage notice, and critical delivery also requires separate device consent and
fresh local hazard evidence. An aggregate status response contains no identifiers,
locations or instructions supplied by contributors.

## Development expectations

Keep credentials out of source, browser responses, fixtures and public issues.
Test ownership checks, stale requests, cancellation and unload behavior. Do not
fetch private network targets through user supplied diagnostic URLs. Preserve the
existing transport limits and explicit consent flow when changing reporting.

Security fixes target the current alpha. No response deadline is promised.
Ordinary bugs can use the public issue tracker or the Give feedback form.
