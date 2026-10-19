# Installation and setup

Weather Intelligence is an alpha custom integration for Home Assistant. Install
it through HACS using the public repository. Being available as a custom repository
does not mean it has been accepted into the default HACS catalog.

## HACS installation

1. Open HACS in Home Assistant. If it is not installed, follow the
   [official HACS instructions](https://www.hacs.xyz/docs/use/download/download/).
2. Open the menu, choose Custom repositories, and add
   `https://github.com/GrandNagusQuark/weather-intelligence` as type Integration.
3. Find Weather Intelligence and download it. If selecting a tagged alpha release,
   enable experimental versions when HACS offers that option.
4. Restart Home Assistant when it is safe to do so.
5. Open Settings, then Devices & services, choose Add integration, and search for
   Weather Intelligence. Complete the initial configuration and then open the
   Weather Intelligence sidebar to start onboarding.

HACS handles downloads and update notices. Its repository address is on GitHub,
but installation takes place inside Home Assistant. On Home Assistant versions
that include Marketplace, use its matching repository installation controls.

## Before installation

You need a working Home Assistant installation, internet access to the selected
weather providers, and a Home zone with usable coordinates. Official alert coverage
in this build comes from the U.S. National Weather Service.

For personal phone alerts, install the Home Assistant Companion app, connect it to
your Home Assistant, and make sure the intended account owns the registered device.
Travel alerts need current location permission and remote connectivity. A generic
notification target does not offer all of the phone specific sound, replacement
and DND features.

The integration needs an installation contact for identifying its NWS API requests.
That contact is not a public support address or a maintainer reporting opt in.

The initial alpha requires Home Assistant 2026.9.2 or newer. That is the
maintainer's running version, not a claim of testing every newer release or
installation type. This is a custom integration, not a Supervisor app. No fresh
install test or compatibility matrix is claimed. iPhone behavior needs community
testing. The maintainer's available phone testing was on Android.

## Manual installation

1. Create a full Home Assistant backup before installing custom code.
2. Inspect the release and its SHA256 inventory. Copy only the
   `custom_components/weather_intelligence` folder into the matching
   `custom_components` directory under your Home Assistant configuration directory.
3. Check the Home Assistant configuration. Restart only when it is safe to
   interrupt current work.
4. Open Settings, then Devices & services, and add Weather Intelligence.
   Supply the required contact and initial Person information.
5. Open Weather Intelligence from the sidebar and start onboarding. Follow device
   selection, the alert explanation, alert choices, DND review, daily outlooks and
   notification setup. Do not assume delivery is enabled merely because the panel
   opens.
6. Follow the phone permission guidance and perform the offered test deliberately.
   Confirm the result on the intended phone before relying on it.

The entry supports one installation. Normal users edit their own settings through
the authenticated panel. An administrator can select another account. Saving an
enrollment or change to another account queues a notice to that person, including
the administrator's name. Opening a screen or canceling a draft does not send it.

## Multiple devices and saved settings

Choose whether selected devices should share settings or be configured individually.
Each device has its own notification setup. Saved settings can be copied where
offered and managed in the app. They are settings copies, not full Home Assistant
backups.

Review alert receipt and DND choices separately. The DND review explains which
conditions may interrupt the phone. The integration cannot prove that operating
system permissions still work just because a test was confirmed earlier.

## Updating

Keep a full backup and note the installed version. Stop if the candidate's source
or provenance is unclear. Replace the complete integration folder with the matching
candidate, validate configuration, restart safely and refresh open panel tabs.

Review About for the running version. Confirm existing device choices, source
status and notification permission guidance after the update. Do not delete the
entry, reset onboarding or copy another installation's storage files as an update
step. If a regression occurs, restore a matching full Home Assistant backup rather
than mixing code and saved state from different versions.

## Optional data and diagnostics

Some forecast, outlook, map and air quality features use separate providers.
AirNow needs an API key. No UV provider is connected in this build.

MQTT error forwarding is optional and sends to your configured broker. It does
not deliver reports to the maintainer. Optional maintainer reporting uses
https://reports.weatherintelligence.app/v1/errors after destination review and
explicit consent. Outage contributions have their own choice and random ID.
Receiving service notices does not require sharing reports. Outage DND bypass is
a separate device choice with local severe weather conditions. Do not paste
credentials into issue reports.

See [Privacy](PRIVACY.md) and [Sources and credits](ATTRIBUTIONS.md).

## Removing the integration

Use Home Assistant Settings, Devices & services, to remove the integration entry.
After removal, restart safely before removing the custom component folder if you
no longer need it. Home Assistant backups can still contain old configuration and
history. The current build does not promise a complete purge of every stored copy
when the entry is removed. Treat storage cleanup as a separate, reviewed operation.

Removing Weather Intelligence does not remove Home Assistant users, Companion apps,
phone permissions, provider accounts or MQTT infrastructure.
