"""Public product information and source provenance, without household data."""

from __future__ import annotations

from typing import Any, Mapping

from .const import PROTOTYPE_VERSION


def _source(
    source_id: str,
    name: str,
    purpose: str,
    url: str,
    status: str,
    *,
    credits: tuple[tuple[str, str], ...] = (),
) -> dict[str, Any]:
    return {
        "id": source_id,
        "name": name,
        "purpose": purpose,
        "url": url,
        "status": status,
        "credits": [{"name": name, "url": url} for name, url in credits],
    }


def about_snapshot(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Describe configuration, not live availability or a guarantee of coverage."""
    config = config or {}

    def optional(key: str, default: bool = False) -> str:
        return (
            "Enabled in settings" if config.get(key, default) is True else "Optional, currently off"
        )

    airnow = optional("airnow_enabled")
    if config.get("airnow_enabled") is True and not str(config.get("airnow_api_key", "")).strip():
        airnow = "Not configured, API key required"
    return {
        "name": "Weather Intelligence",
        "version": PROTOTYPE_VERSION,
        "stage": "Public alpha",
        "summary": "Weather awareness for Home Assistant, at home and while traveling.",
        "limitations": [
            "An independent project, not an official NOAA or National Weather Service product. "
            "Keep other warning sources available. Missing alerts or data do not mean conditions are safe.",
            "Weather Intelligence can create notifications from official data. These are separate "
            "from official warnings. The issuing agency remains the source of an official alert.",
            "Marine notifications are in an early state and need further testing. Location and "
            "water maps are estimates, not navigation advice or proof that someone is boating.",
        ],
        "privacy": (
            "Settings and location comparisons stay in Home Assistant. Weather requests use the "
            "location needed by each provider. Regional map requests use coarse areas. Phone delivery "
            "uses Home Assistant and the phone platform's push services. Optional MQTT diagnostics "
            "go to the configured broker, not automatically to the project maintainer. Optional "
            "maintainer reports need separate consent for a configured destination. They contain "
            "only fixed diagnostic fields and no installation ID. The project destination "
            "uses Cloudflare to reach a private maintainer inbox with 30 day report retention. "
            "Cloudflare can see the connection IP. Separate outage contributions with a random "
            "installation ID require their own consent. They include only a source label, "
            "failure, significant delay or recovery, approximate time and schema version. Five "
            "minutes from issue time to first receipt during continuous monitoring is significant. "
            "Phone arrival time is not measured. They are pseudonymous, "
            "not anonymous. Turning participation off deletes the active local ID. Received "
            "observations and local sending history expire within 30 days. Shared status can "
            "be received without contributing. Opening a "
            "source link contacts that website."
        ),
        "development": "Developed under maintainer direction with AI assistance.",
        "testing": (
            "Automated checks and maintainer phone testing have been completed. iPhone behavior "
            "still needs community testing. Phone permissions and delivery can vary."
        ),
        "license": {
            "name": "GNU Affero General Public License v3 only",
            "url": "https://www.gnu.org/licenses/agpl-3.0.html",
            "note": (
                "The license text is included with the source. Commercial use is allowed. "
                "Modified network versions must offer corresponding source as required by the license. "
                "Provided without warranty. Third party notices remain in their files."
            ),
        },
        "support": (
            "Check source availability and the local Home Assistant log when troubleshooting. "
            "For support, use the GitHub issue tracker or Give feedback. "
            "Do not share credentials, exact locations or raw logs in public reports."
        ),
        "source_note": (
            "This directory describes the sources used by this build. Enabled does not mean "
            "currently available. Optional and conditional sources are not used for every alert. "
            "Credit does not imply endorsement."
        ),
        "groups": [
            {
                "name": "Alerts and weather information",
                "sources": [
                    _source(
                        "nws",
                        "NOAA National Weather Service",
                        "Official alerts, forecasts and source reports.",
                        "https://www.weather.gov/documentation/services-web-api",
                        "Core source",
                    ),
                    _source(
                        "spc",
                        "NWS Storm Prediction Center",
                        "Storm and fire outlooks and mesoscale discussions.",
                        "https://www.spc.noaa.gov/",
                        optional("spc_outlooks_enabled"),
                    ),
                    _source(
                        "wssi",
                        "NWS Weather Prediction Center",
                        "Winter Storm Severity Index information.",
                        "https://www.wpc.ncep.noaa.gov/wwd/wssi/wssi.php",
                        optional("wssi_enabled"),
                    ),
                    _source(
                        "mrms",
                        "NOAA MRMS",
                        "Radar hail estimates used in derived hail notifications.",
                        "https://mrms.ncep.noaa.gov/",
                        optional("mrms_hail_tracking_enabled", True),
                    ),
                    _source(
                        "airnow",
                        "EPA AirNow and participating agencies",
                        "Air quality observations for optional briefings.",
                        "https://docs.airnowapi.org/",
                        airnow,
                    ),
                    _source(
                        "uv",
                        "UV information",
                        "No UV provider is connected in this build.",
                        "",
                        "Not connected",
                    ),
                ],
            },
            {
                "name": "Maps and regional context",
                "sources": [
                    _source(
                        "noaa_maps",
                        "NOAA and NWS map services",
                        "Radar images, warning boundaries and reference maps.",
                        "https://mapservices.weather.noaa.gov/",
                        "Used when viewing the map",
                    ),
                    _source(
                        "usgs",
                        "USGS 3D Hydrography Program",
                        "Regional water outlines for selected marine features.",
                        "https://www.usgs.gov/3d-hydrography-program/access-3dhp-data-products",
                        "Used when needed",
                    ),
                    _source(
                        "usace",
                        "U.S. Army Corps of Engineers",
                        "Charted channel areas for nearby water context, not current lock status.",
                        "https://spatial.usace.army.mil/opjarcgis/rest/services/ehydro/ChannelReach/FeatureServer/0",
                        "Used when needed",
                    ),
                    _source(
                        "avalanche",
                        "Avalanche.org and regional forecast centers",
                        "Forecast region boundaries for avalanche defaults, not property risk or daily danger ratings.",
                        "https://avalanche.org/",
                        "Used when reviewing relevant defaults",
                    ),
                    _source(
                        "basemap",
                        "OpenFreeMap",
                        "Map display, with OpenMapTiles and OpenStreetMap data.",
                        "https://openfreemap.org/",
                        "Used when viewing the map",
                        credits=(
                            ("OpenMapTiles", "https://www.openmaptiles.org/"),
                            (
                                "© OpenStreetMap contributors",
                                "https://www.openstreetmap.org/copyright",
                            ),
                        ),
                    ),
                    _source(
                        "census",
                        "U.S. Census Bureau TIGERweb",
                        "Road map fallback when the main map renderer is unavailable.",
                        "https://tigerweb.geo.census.gov/",
                        "Fallback only",
                    ),
                ],
            },
            {
                "name": "Application and delivery",
                "sources": [
                    _source(
                        "ha",
                        "Home Assistant and Companion apps",
                        "Local device context and configured phone delivery.",
                        "https://companion.home-assistant.io/docs/notifications/notifications-basic/",
                        "Host platform",
                    ),
                    _source(
                        "maplibre",
                        "MapLibre GL JS",
                        "Map rendering software served by your Home Assistant.",
                        "https://maplibre.org/",
                        "Local renderer",
                    ),
                ],
            },
        ],
    }
