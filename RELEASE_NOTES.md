# Weather Intelligence 0.1.25-alpha

This update makes the last onboarding screen clearer and gives you a way
back into setup.

The screen now says Onboarding complete and asks you to restart Home Assistant
to finish applying your setup. It also explains that you do not need another
restart if you have already restarted since saving. If automatic activation
failed, that remains visible rather than claiming delivery is ready.

The new Review or change setup button returns to setup without deleting saved
alerts or repeating phone tests. Your existing alert choices remain in place.

Review setup or add devices now opens a separate menu instead of reopening the
last completion screen. Administrators can choose to set up another user's
devices from that menu.

This update also fixes cleanup callbacks that could make Home Assistant fail
to reload Weather Intelligence after saving setup. A restart is needed to
recover an installation that has already reached that failed reload state.

The new optional categories field is omitted because the published Hassfest
validator rejects it. HACS still reports an advisory about that missing field,
but its validation passes. No checks are disabled or ignored to hide it.

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
