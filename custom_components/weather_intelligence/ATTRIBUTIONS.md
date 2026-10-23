# Sources and credits

Weather Intelligence uses official information alongside its own derived notices.
Credit does not imply endorsement. Source availability and optional features vary.
The About screen and the source list at the end of onboarding provide the same
source directory inside the app.

## Weather information

- [NOAA National Weather Service](https://www.weather.gov/documentation/services-web-api)
  provides official alerts, forecasts and source reports.
- [NWS Storm Prediction Center](https://www.spc.noaa.gov/) provides storm and fire
  outlooks and mesoscale discussions for optional context.
- [NWS Weather Prediction Center](https://www.wpc.ncep.noaa.gov/wwd/wssi/wssi.php)
  provides Winter Storm Severity Index information.
- [NOAA MRMS](https://mrms.ncep.noaa.gov/) provides radar estimates used by derived
  hail notifications. A radar estimate is not a measurement at a person's property.
- [EPA AirNow and participating agencies](https://docs.airnowapi.org/) provide
  optional air quality observations. The installation supplies an API key.
- No UV provider is connected in this build.

## Maps and context

- [NOAA and NWS map services](https://mapservices.weather.noaa.gov/) provide radar
  images, warning boundaries and reference maps.
- [USGS 3D Hydrography Program](https://www.usgs.gov/3d-hydrography-program/access-3dhp-data-products)
  provides regional water outlines.
- [U.S. Army Corps of Engineers](https://spatial.usace.army.mil/opjarcgis/rest/services/ehydro/ChannelReach/FeatureServer/0)
  provides charted channel areas. These are not live lock status or passage advice.
- [Avalanche.org and regional forecast centers](https://avalanche.org/) provide
  forecast region boundaries for relevant defaults, not property risk assessments.
- [OpenFreeMap](https://openfreemap.org/) provides the map display, with
  [OpenMapTiles](https://www.openmaptiles.org/) and
  [OpenStreetMap contributors](https://www.openstreetmap.org/copyright).
  OpenStreetMap data is available under the Open Database License.
- [U.S. Census Bureau TIGERweb](https://tigerweb.geo.census.gov/) supplies a road map
  fallback when the primary map renderer is unavailable.

## Application software

[Home Assistant and Companion apps](https://companion.home-assistant.io/docs/notifications/notifications-basic/)
host the integration and provide configured device context and notification
delivery. [MapLibre GL JS](https://maplibre.org/) provides the locally served map
renderer. Its bundled notices are preserved in
`custom_components/weather_intelligence/frontend/vendor/MAPLIBRE-LICENSE.txt`,
including the upstream notices carried there. Shapely is installed by Home
Assistant according to the integration manifest and retains its own license.

Android critical sirens use Companion's documented
[`alarm_stream` route](https://companion.home-assistant.io/docs/notifications/critical-notifications/#alarm-stream).
That literal category name enables alarm audio; a custom Weather Siren label
does not. Phone sound and DND settings still govern playback.

The selected core license is AGPL v3 only, included in LICENSE. External services and
data retain their own terms. No blanket license is asserted for their content.
