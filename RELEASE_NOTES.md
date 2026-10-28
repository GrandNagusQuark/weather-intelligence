# Weather Intelligence 0.1.35-alpha

Clearer radar, a simple opacity slider, and daily outlook fixes.

## Radar

- Zoom in for NOAA's super-resolution reflectivity when a nearby radar covers the map. Wider views use the regional mosaic, which also stays available if the detailed feed is missing or delayed.
- Both radar products are cached. The current image stays visible until its replacement has finished loading, so switching does not blank the map.
- The map checks NOAA's published scan times instead of downloading the same image over and over. It shows the displayed scan's age and warns when imagery is delayed.
- A small slider below the map adjusts radar opacity. It starts at 65%, remembers your choice in that browser, and leaves warnings and household markers alone.
- Radar images render more clearly on high-density screens. Zooming cannot add detail beyond what the radar source provides.

Detailed reflectivity can show echoes from things other than rain, including
ground clutter. Use official alerts for warning decisions.

## Daily outlooks and setup

- Fixed daily outlooks losing the forecast when severe-weather awareness was turned off. That setting now controls the extra weather notices, not your daily forecast.
- Outlooks include the high, low and rain chance when those details are available from NWS.
- If the forecast is unavailable, the outlook waits and tries again instead of sending only an incomplete-weather message. Once accepted, it is not sent again that day; yesterday's outlook is never sent after midnight.
- A busy weather day no longer pushes the forecast out of the briefing's short list of concerns.
- You can edit an enrolled device's current alerts even if its onboarding is unfinished, without restarting setup.

## After updating

Restart Home Assistant, then refresh the Weather Intelligence page. Your saved
settings and reporting choices stay the same. This remains an early release;
keep official warning sources available alongside it.

## Previous release: 0.1.34-alpha

This update fixes hail monitoring, makes error reports useful for diagnosing problems, and smooths out setup and everyday settings.

## Fixes

- **Hail monitoring:** Fixed a problem reading NOAA's current hail feed and corrected hail-size calculations. Failed downloads or unreadable data no longer get treated as a successful refresh.
- **Useful error reports:** Optional reports now show what failed, the exception and known cause, where it happened in the code, and any available HTTP or system error code. Different problems stay in separate groups. Old reports remain available, but missing details cannot be recovered from them.
- **Save without losing your place:** Saving settings keeps Weather Intelligence open instead of sending you back to the Home Assistant dashboard.
- **Dismiss admin notices:** The ADMIN ACTION banner has a Dismiss button. It stays dismissed after refreshing or restarting; a new change can create a new notice.
- **Review messages clear straight away:** After you accept or decline the updated reporting choice, its review message disappears without refreshing the page. A failed save keeps the message visible.
- **Android sirens:** Restored the alarm audio route used for urgent sirens. Routine weather notifications keep their normal categories. Setup no longer creates a new numbered category each time.
- **Setup and editing:** One setup menu brings together quick setup, guided setup, custom setup and editing an existing device. Unfinished setup resumes where it stopped, and administrators can help another household member finish.
- **Map:** Restored the household markers and legend, improved warning alignment while moving the map, and fixed continuous scrolling east and west.
- **Daily outlooks:** Missed sends can retry after the scheduled time until midnight. Accepted sends are not repeated. Android phone receipts are shown as received by the phone, which does not mean the notification was displayed or read.
- Fixed a cleanup error that could appear after changing settings.

## After updating

Restart Home Assistant after installing.

Android users with an existing siren setup will see a notice to review their phone permissions and test the sound. The urgent category is **alarm_stream**. Allow alarms through Do Not Disturb and complete the tests in mobile alert setup. The update does not play a loud test automatically.

Optional error reporting pauses until an administrator reviews the expanded diagnostic details and chooses **Accept** or **Decline**. Reports still exclude raw logs, personal information, locations, filesystem paths and local variables. The exact report and delivery result are available through the admin audit button on the main page. Outage contributions remain a separate choice.

This is still an alpha release. Marine features and iPhone notification behavior need more community testing.
