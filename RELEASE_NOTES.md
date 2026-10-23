# Weather Intelligence 0.1.33-alpha

This update fixes hail monitoring, makes error reports useful for diagnosing problems, and smooths out setup and everyday settings.

## Fixes

- **Hail monitoring:** Fixed a problem reading NOAA's current hail feed and corrected hail-size calculations. Failed downloads or unreadable data no longer get treated as a successful refresh.
- **Useful error reports:** Optional reports now show what failed, the exception and known cause, where it happened in the code, and any available HTTP or system error code. Different problems stay in separate groups. Old reports remain available, but missing details cannot be recovered from them.
- **Save without losing your place:** Saving settings keeps Weather Intelligence open instead of sending you back to the Home Assistant dashboard.
- **Dismiss admin notices:** The ADMIN ACTION banner has a Dismiss button. It stays dismissed after refreshing or restarting; a new change can create a new notice.
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
