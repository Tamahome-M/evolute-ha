"""Constants for the Evolute integration."""

DOMAIN = "evolute"

CONF_CAR_ID = "car_id"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 120

DATA_COORDINATOR = "coordinator"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/144.0.0.0 Safari/537.36"
)

BASE_URL = "https://app.evassist.ru"
REFRESH_URL = f"{BASE_URL}/id-service/auth/refresh-token"

INTELLIGENT_ACTIONS = {
    "lock_close": ("centralLockingToggle", "centralLockingStatus", 1),
    "lock_open":  ("centralLockingToggle", "centralLockingStatus", 0),
    "heating_on":  ("heating",  "climateStatus", 1),
    "heating_off": ("heating",  "climateStatus", 0),
    "cooling_on":  ("cooling",  "climateStatus", 1),
    "cooling_off": ("cooling",  "climateStatus", 0),
    "trunk_open":  ("trunkOpen", "trunkStatus", 1),
    "trunk_close": ("trunkOpen", "trunkStatus", 0),
    "prepare_on":  ("PREPARE",  "ignitionStatus", 1),
    "prepare_off": ("CANCEL",   "ignitionStatus", 0),
    "blink":       ("blink",    "ready", 1),
}
