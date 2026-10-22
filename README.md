# Weather Intelligence for Home Assistant

Current version: 0.1.25-alpha.

![Weather Intelligence](https://raw.githubusercontent.com/GrandNagusQuark/weather-intelligence/main/custom_components/weather_intelligence/brand/icon.png)

Weather alerts that make sense for where you are and what you want to hear about.
Weather Intelligence brings official National Weather Service alerts, radar and
optional daily outlooks into Home Assistant. Use it at home, while traveling or
near the water.

This is an early public alpha. It supplements official warnings. Keep other
warning sources available. Missing alerts do not mean conditions are safe.

## Install through HACS

[Open Weather Intelligence in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=GrandNagusQuark&repository=weather-intelligence&category=integration)

You need HACS installed in Home Assistant. Open HACS, choose Custom repositories
from its menu, and add this address with type Integration:

`https://github.com/GrandNagusQuark/weather-intelligence`

Download Weather Intelligence, restart Home Assistant, then go to Settings,
Devices & services, Add integration and search for Weather Intelligence.
Complete the initial configuration, then open Weather Intelligence from the
sidebar to begin guided setup. If selecting an alpha release, enable experimental
versions when HACS offers that option.

This repository can be added manually to HACS. Default catalog inclusion is a
separate review and is not claimed. See [Installation and setup](INSTALL.md).

## What it does

- Official weather warnings, watches and advisories, with radar and warning areas.
- Home and travel alerts based on your Home Assistant home zone and enrolled devices.
- Guided setup, saved device choices and an alert editor grouped by hazard.
- Separate Do Not Disturb choices, explicit review and phone setup guidance.
- Optional daily outlooks and context from additional weather sources.
- Marine alerts and adjustable nearby notices using available regional water maps.
- Optional shared NWS outage awareness, including significant alert feed delays.
- A notice naming the administrator when they set up or change another account.
- A Give feedback form with a review before sending.

Outage observations consider delays of at least five minutes from official issue
time to first receipt during continuous monitoring. Restarts, travel, polling gaps
and uncertain clocks are excluded. This does not measure arrival on a phone.
A shared incident needs independent corroboration. It is not an official NWS
outage declaration or a promise that every delay will be detected.

## Your data and optional reports

Optional reports help me fix bugs and spot problems with weather feeds. They
provide useful software details without sending names, locations or hardware
identifiers in the report. This is about explaining what the project uses and
why, not claiming that other weather integrations are less private.

Settings and location comparisons stay in Home Assistant. Weather and map
providers receive the location or area needed for their services. Phone delivery
uses Home Assistant and the phone platform's notification services.

Automatic error reporting is off until an administrator agrees. Reports use
fixed diagnostic fields, without names, coordinates, IP addresses, hardware
identifiers, credentials or raw logs. Administrators can view the exact prepared
reports and delivery results in a local history kept for 30 days. Cloudflare
processes connection IP addresses while handling submissions.

Outage contributions have their own consent and random installation number.
That makes them pseudonymous, not fully anonymous. The number is used for source
failures, delays and recoveries, not ordinary error reports. You can receive
outage notices without contributing reports. Outage Do Not Disturb bypass has a
separate choice and requires qualifying local severe weather evidence.

Manual feedback does not enable automatic reporting. It sends the reviewed
message and approved software context, with a limit of two submissions per
installation per rolling hour. Please do not include personal information.

The private maintainer inbox is a separate integration. It is not included in
this repository or installed on users' Home Assistant systems.
See [Privacy](PRIVACY.md) and [Sources and credits](ATTRIBUTIONS.md).

## Requirements and limits

The initial alpha requires Home Assistant 2026.9.2 or newer. That is the
maintainer's running version, not a claim of testing every installation or later
release. You need internet access, a configured Home zone and a contact for NWS
requests. Personal phone alerts need the Home Assistant Companion app and the
appropriate permissions. AirNow is optional and needs an API key.

The maintainer reports testing on the available Android phone. iPhone behavior
needs community testing. Do Not Disturb bypass depends on phone permissions.
Marine notifications are in an early state. GPS and water maps are estimates,
not navigation advice, proof of boating or dependable bridge detection.

## Help and feedback

Use [GitHub issues](https://github.com/GrandNagusQuark/weather-intelligence/issues)
for bugs and feature requests, or Give feedback in the app. Please include the
version and a small example without household details or raw logs.

Report security problems through
[private vulnerability reporting](https://github.com/GrandNagusQuark/weather-intelligence/security/advisories/new),
not a public issue. See [Security](SECURITY.md).

The project is maintained by [GrandNagusQuark](https://github.com/GrandNagusQuark).
Development uses AI assistance under maintainer direction.

## Support development

<a href="https://www.buymeacoffee.com/Weatherintelligence" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer"><img src="https://raw.githubusercontent.com/GrandNagusQuark/weather-intelligence/main/custom_components/weather_intelligence/frontend/buy-me-a-coffee-blue.png" alt="Buy Me a Coffee" width="217" height="60"></a>

Support is optional and does not change the alerts or features you receive.

## License

Project owned code is licensed under the GNU Affero General Public License
version 3 only (AGPL-3.0-only). Commercial use is allowed under those terms.
Modified network versions must offer corresponding source as required by the
license. Third party software, artwork and data retain their own terms.

See [LICENSE](LICENSE), [Ownership and branding](COPYRIGHT.md) and
[Contributing](CONTRIBUTING.md).

Weather Intelligence is independent of Home Assistant, NOAA and the National
Weather Service. Source credits do not imply endorsement.
