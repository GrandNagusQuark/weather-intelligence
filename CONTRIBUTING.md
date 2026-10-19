# Contributing

Weather Intelligence is in public alpha. Report ordinary bugs or propose changes
at https://github.com/GrandNagusQuark/weather-intelligence. Use the private
vulnerability reporting channel described in SECURITY.md for security problems.

## Changes and tests

Keep changes focused. Separate features into understandable modules and explain
nonobvious safety decisions in comments. Avoid comments that repeat the code.
Follow Home Assistant conventions: Python variables and functions use snake_case,
constants use SCREAMING_SNAKE_CASE and classes use PascalCase. Frontend JavaScript
uses camelCase where appropriate.

Use synthetic locations and recorded public data in tests. Mock notification
sends, provider requests and reporting destinations. Cover cancellation, repeated
saves, restart continuity and account ownership when those paths are affected.
Do not reset onboarding, enroll devices or send tests to real phones without
specific permission.

Explain source facts separately from Weather Intelligence estimates. Never turn
missing data into a claim that a location is safe. Public text should be direct,
readable and free of unnecessary jargon.

Run the Python and frontend suites described in the README. Keep version metadata
consistent. A passing mocked suite does not establish physical phone behavior or
the coverage of a remote map service.

## Rights and attribution

Only submit material you wrote or have permission to contribute. Identify copied
or adapted material and preserve its license and attribution. Contributions to the
core are intended to be distributed under the project's AGPL v3 only terms. Do not
submit incompatible code, private data or material covered by an agreement that
prevents that distribution.

Contributors retain their applicable rights. Contributing does not transfer
copyright to the maintainer. Any future contributor agreement would need its own
explicit review and acceptance.

AI tools may assist development. Contributors remain responsible for reviewing
correctness, provenance, privacy and tests. State material tool assistance when
describing a contribution. Tool output is not a substitute for source verification.

## Releases

Public publication requires a maintainer decision. Internal candidates, local
previews and a functioning Home Assistant installation are not public releases.
Keep private deployment notes, proof screenshots, local paths, caches, credentials
and reset markers out of release artifacts.
