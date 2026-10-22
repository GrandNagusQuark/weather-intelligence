# Privacy

Weather Intelligence runs in your Home Assistant. Core weather alert processing
does not need a project account or a maintainer reporting service.

Optional reports help the maintainer fix bugs and spot problems with weather
feeds. The report fields are limited to what those tasks need, rather than names,
locations or hardware identifiers. The sections below explain what stays local,
what each service receives and the separate choices for sharing reports.

## Settings and local state

Home Assistant stores device preferences, onboarding progress, saved settings
copies, notification continuity and limited runtime state. Location context comes
from Home Assistant People, device trackers and the Home zone. Runtime state and
Home Assistant backups may contain private household information.

Regional water and channel caches contain public map geometry for recently needed
areas. They are bounded and expire. They are not a downloaded world map or a trip
history, although a cached region can reveal an area that the installation used.

Home Assistant administrators can read or alter installed code and local storage.
Notices about changes to another account are workflow safeguards, not protection
against someone controlling the server. The settings comparison cannot identify
the person behind an unverified backend edit.

## Requests to providers

Weather requests can include the home or current location needed by the provider.
The installation contact identifies NWS requests. Optional AirNow requests use the
configured API key. Providers can see the requesting connection IP and handle
requests under their own policies.

USGS water and USACE channel requests identify coarse map regions. MRMS hail data
is downloaded as a national grid and analyzed locally. Viewing the map contacts
map and radar providers and can reveal the viewed area. Opening an external source
link contacts that website.

Phone delivery uses Home Assistant and the phone platform's push services. Remote
access, reverse proxies and other Home Assistant integrations have their own data
handling. This policy does not describe all traffic from the phone or server.

## Optional diagnostics

MQTT diagnostics are off unless enabled. They go to the broker and topic configured
by the installation, not automatically to the maintainer. The integration builds
fixed diagnostic summaries instead of forwarding arbitrary log messages or raw
tracebacks. Broker access and retention depend on the installation.

The separate maintainer reporting service is also off by default. The project
destination is https://reports.weatherintelligence.app/v1/errors. It sends reports
through Cloudflare to the maintainer's private Home Assistant inbox. The inbox is
a separate integration and is not installed with public copies of Weather
Intelligence. Received reports are grouped and retained for 30 days. Enabling it requires reviewing
the exact destination and approving a fixed set of fields: schema version,
integration version, Home Assistant version, rounded time, error category,
component, severity and exception category. For a phone related error, the platform,
OS release and Companion app release are included when known. Build numbers and
app flavor are removed. Missing device context stays unknown rather than guessing
from other household phones. The application payload excludes names, coordinates,
credentials, entity and device identifiers, phone serial numbers, MAC and IP
addresses, custom device names and raw logs.

Cloudflare can still see network metadata,
including the connection IP. Reports are not anonymous merely because that IP is
absent from the application payload. The destination's operator, retention policy
and service terms must be reviewed before agreeing to share reports. Changing
the configured destination disables reporting until consent is reviewed again.

## Separate outage contributions

Shared outage detection has its own choice so an installation can share ordinary error reports
without contributing to outage detection. Receiving service status does not
require contributing reports.

Only after separate consent, outage reports use a random identifier generated locally for the
installation, not a Home Assistant account ID or a phone identifier. That number
is used only to group the limited information needed to detect service outages.
It is not attached to ordinary error reports or used to track other activity.
Because it links outage reports from the same installation, it is pseudonymous,
not completely anonymous. The five fields are schema version, random installation
ID, the fixed NWS alert source label, unavailable, delayed or recovered, and a UTC time
rounded to the minute. Contributions use the project destination at
https://reports.weatherintelligence.app/v1/outages. They do not contain locations,
phone information, names or raw errors.

Received observations and exact local sending history are kept for 30 days.
Turning outage participation off deletes the active local ID. Existing received
observations stop counting after 15 minutes and expire within 30 days. Enabling
participation again creates a new ID. Turning error reporting off also turns off
outage contributions. Existing error reporting consent never authorizes them.

Status checks use https://reports.weatherintelligence.app/v1/status without an
installation ID. Cloudflare still processes the connection IP under its own
policies. The status response contains only the source, status, aggregate count,
threshold and expiry. Fifty distinct IDs in 15 minutes and three failed
maintainer checks corroborate an access problem. These are not proof of distinct
people, a complete measure of alert delays or an official NWS outage declaration.
Delay observations require at least five minutes from the official message issue
time to first receipt by the integration during continuous monitoring of the same
area. Restarts, entering a new area, gaps in polling, incomplete responses and
uncertain clock comparisons are excluded. This measures feed receipt, not when a
phone displays a notification. Only the fixed delayed state is reported. Alert
identifiers, issue times and query locations stay in bounded transient memory.
Shared delay corroboration requires fifty distinct delayed IDs in 15 minutes and
an independent five minute delay observed by the maintainer probe. A successful
HTTP request alone does not establish that alerts are timely. A national response
at its result limit cannot establish a complete baseline, so delay confirmation
may be unavailable during large events. Recent delay evidence expires after
15 minutes. Absence of a corroborated incident does not prove every alert arrived.
Missing or expired status is unknown. Outage notices use normal delivery unless a
separate device choice allows bypass and recent official severe weather evidence
qualifies. A fresh current location must overlap an active NWS Tornado or Severe
Thunderstorm watch or warning that applies now or starts within two hours. Broad
daily outlooks alone do not qualify. The last official confirmation may be up to
two hours old, but the alert must remain within its stated validity period. The
notice explains that newer changes may be unavailable. The phone must also permit bypass. All hazard
and location checks stay local. They are never included in outage contributions.

## Review and removal

### Manual feedback

Give feedback is a separate deliberate submission, not automatic telemetry.
The form asks people not to include personal information. Known private patterns
such as IP addresses, email addresses, coordinates and credentials are rejected,
but those checks cannot identify every private detail someone might type.
Review the exact message and diagnostic fields before choosing Send feedback.
Nothing is sent merely by opening, editing or reviewing the form.

Feedback has ten fields: schema version, a random submission number, category,
message, integration version, Home Assistant version, UTC minute, phone platform,
OS version and Companion app version. Phone context comes only from a selected
registration owned by the signed in account. Device names and registration IDs
stay local and are not sent. Hardware model, serial numbers, MAC addresses,
locations, account names, installation identifiers and IP addresses are not added.
Unknown software context stays unknown. No household inventory is attached.

The project route is https://reports.weatherintelligence.app/v1/feedback.
Cloudflare processes connection IPs under its own policies. The maintainer stores
feedback separately from automatic errors, for 30 days. The submitting account
has its own exact local sending history for 30 days. No contact details are
requested and a reply is not guaranteed. This is not an emergency channel.

A durable installation budget permits two new feedback submissions in a rolling
hour across all accounts. Retrying the same submission does not consume another
slot, change the saved content or extend receiver retention. The budget stores
only submission numbers and reservation times, with no user identity. A failed
or uncertain send can reserve a slot so restarting cannot evade the limit.
This client budget does not prove that public requests are genuine installations.
The relay and private receiver retain independent abuse and storage limits.

The local reporting history shows the exact sanitized fields prepared for sending,
the destination, approximate attempt time and whether the receiver confirmed
acceptance. It is retained for 30 days and remains available when reporting is off.
If the audit cannot be saved, reporting pauses. A receipt does not mean the
developer has read the report. Household administrators can view this local history.
It does not contain the original log message. Home Assistant backups may retain
earlier copies under the installation's backup policy.

Review preferences, optional sources, saved settings and diagnostic choices in the
app. A broader network destination audit and reviewed parser diagnostic export
remain planned and are not claimed to exist yet.

Removing the integration does not erase Home Assistant backups, recorder history,
MQTT receiver files or data already accepted by an external provider. The current
build does not provide one action that purges every copy. Review those systems
separately before sharing or disposing of a Home Assistant backup.
