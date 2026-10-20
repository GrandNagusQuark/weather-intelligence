"""Constants owned by the provisional integration."""

from datetime import timedelta

DOMAIN = "weather_intelligence"
PROTOTYPE_VERSION = "0.1.24-alpha"

CONF_CONTACT = "contact"
CONF_MONITOR_HOME = "monitor_designated_home"
CONF_CRITICAL_NOTIFICATIONS = "critical_notifications_enabled"
CONF_PERSON_ENTITY = "person_entity"
CONF_NOTIFY_ENTITY = "notify_entity"
CONF_LEGACY_NOTIFY_SERVICE = "legacy_notify_service"
CONF_MOBILE_PLATFORM = "mobile_platform"
CONF_SHOW_LOCATION_ON_MAP = "show_location_on_map"
CONF_PROFILES = "profiles"
CONF_PROFILE_ID = "profile_id"
CONF_PROFILE_NAME = "name"
CONF_PROFILE_ENABLED = "enabled"
CONF_RECEIVE_PERSONAL = "receive_personal_location_alerts"
CONF_RECEIVE_HOME_AWAY = "receive_designated_home_alerts_while_away"
CONF_AUTOMATIC_NOTIFICATIONS = "automatic_official_warning_notifications"
CONF_HAZARD_FAMILIES = "hazard_families"
CONF_ALERT_EVENTS = "alert_events"
CONF_MARINE_WARNING_MODE = "marine_warning_mode"
CONF_BRIEFING_ENABLED = "daily_briefing_enabled"
CONF_BRIEFING_LOCATION = "daily_briefing_location"
CONF_BRIEFING_TIME = "daily_briefing_time"
CONF_AIRNOW_API_KEY = "airnow_api_key"
CONF_SPC_ENABLED = "spc_outlooks_enabled"
CONF_MRMS_HAIL_ENABLED = "mrms_hail_tracking_enabled"
CONF_WSSI_ENABLED = "wssi_enabled"
CONF_AIRNOW_ENABLED = "airnow_enabled"
CONF_UV_ENABLED = "uv_enabled"
DEFAULT_BRIEFING_TIME = "07:00"
BRIEFING_LOCATION_HOME = "designated_home"
BRIEFING_LOCATION_PERSON = "person"
BRIEFING_LOCATION_BOTH = "both"
BRIEFING_LOCATIONS = (
    BRIEFING_LOCATION_HOME,
    BRIEFING_LOCATION_PERSON,
    BRIEFING_LOCATION_BOTH,
)
CONF_MQTT_ERROR_LOGGING = "mqtt_error_logging_enabled"
CONF_MQTT_ERROR_TOPIC = "mqtt_error_topic"
DEFAULT_MQTT_ERROR_TOPIC = "weather_intelligence/developer/errors"
ALL_CLEAR_RETENTION = timedelta(hours=1)
WEATHER_NOTIFICATION_ICON = "mdi:weather-lightning"

MOBILE_PLATFORM_AUTO = "auto"
MOBILE_PLATFORM_ANDROID = "android"
MOBILE_PLATFORM_IOS = "ios"
MOBILE_PLATFORMS = (
    MOBILE_PLATFORM_AUTO,
    MOBILE_PLATFORM_ANDROID,
    MOBILE_PLATFORM_IOS,
)

SERVICE_TEST_NOTIFICATION = "test_notification"
SERVICE_TEST_MOBILE_NOTIFICATION = "test_mobile_notification"
SERVICE_TEST_MOBILE_SCENARIO = "test_mobile_scenario"
CONF_TEST_SCENARIO = "scenario"
TEST_SCENARIO_NEW = "new_warning"
TEST_SCENARIO_UPDATE = "meaningful_update"
TEST_SCENARIO_CANCEL = "cancellation"
TEST_SCENARIOS = (
    TEST_SCENARIO_NEW,
    TEST_SCENARIO_UPDATE,
    TEST_SCENARIO_CANCEL,
)
SAFE_TEST_NOTIFICATION_ID = "weather_intelligence_safe_test"
SAFE_TEST_TITLE = "Weather Intelligence test"
SAFE_TEST_MESSAGE = (
    "TEST ONLY — This is not a weather alert. "
    "Weather Intelligence can create a local Home Assistant notification."
)
SAFE_MOBILE_TEST_TITLE = "TEST ONLY — Weather Intelligence"
SAFE_MOBILE_TEST_MESSAGE = (
    "TEST ONLY — This is not a weather alert. "
    "Weather Intelligence sent this only because you manually ran the mobile test."
)

NWS_API_BASE_URL = "https://api.weather.gov"
NWS_REQUEST_TIMEOUT_SECONDS = 10.0
# NWS asks alert API consumers not to refresh more often than every 30 seconds.
# Keep a one-second safety margin so timer jitter or boundary rounding cannot
# place requests inside the provider's rate-limit window.
NWS_POLL_INTERVAL = timedelta(seconds=31)

LOCATION_GRACE_PERIOD = timedelta(minutes=15)
LAST_KNOWN_CRITICAL_ELIGIBILITY = timedelta(hours=1)
