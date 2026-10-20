# Weather Intelligence 0.1.24-alpha

This alpha update fixes the two warnings found during the HACS compliance check.

The manifest now declares its weather alerts category. Setup also uses Home
Assistant's standard declaration for integrations configured through the UI,
rather than YAML. No checks are disabled or ignored.

The existing HACS catalog submission remains open. This release does not imply
catalog approval. You can install it through HACS as a custom repository now.

Includes official NWS alerts, radar, home and travel context, guided notification
setup, hazard grouped settings, Do Not Disturb choices, optional daily outlooks,
marine notices in an early state, optional error reporting, shared outage and
alert feed delay awareness, and manual feedback.

Reporting and outage participation require separate consent. The private
maintainer inbox is not part of this release. The project uses AGPL v3 only.

Requires Home Assistant 2026.9.2 or newer. The maintainer reports Android phone
testing. iPhone behavior needs community testing. Marine notifications need more
testing and are not navigation advice. Keep other official warning sources
available. No universal compatibility or guaranteed delivery is claimed.

After downloading in HACS, restart Home Assistant and add Weather Intelligence
through Settings, Devices & services. Existing internal installations should keep
their saved settings. Do not delete the entry or reset onboarding to update.
