"""Constants for the Evolute integration."""

DOMAIN = "evolute"

CONF_CAR_ID = "car_id"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_PHONE_NUMBER = "phone_number"
CONF_SMS_CODE = "sms_code"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_TIMEOUT = "timeout"
CONF_TOKEN_REFRESH_INTERVAL = "token_refresh_interval"
# Tbox device id (IMEI) — required by the new client-bff telemetry API.
# Discovered automatically from API responses and persisted here.
CONF_DEVICE_ID = "device_id"

DEFAULT_SCAN_INTERVAL = 120
DEFAULT_TIMEOUT = 20
DEFAULT_TOKEN_REFRESH_INTERVAL = 600

DATA_COORDINATOR = "coordinator"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/144.0.0.0 Safari/537.36"
)

BASE_URL = "https://app.evassist.ru"
LOGIN_PAGE_URL = f"{BASE_URL}/login"
LOGIN_URL = f"{BASE_URL}/id-service/auth/sign-in"
REFRESH_URL = f"{BASE_URL}/id-service/auth/refresh-token"

# The web app polls the last command by IMEI every 1.5 seconds. The backend
# reports an error if the vehicle has not confirmed execution within 45 s.
COMMAND_POLL_INTERVAL = 1.5
COMMAND_CONFIRM_TIMEOUT = 50
COMMAND_STATES = [
    "idle", "sending", "pending", "delivered", "success", "error", "timeout",
    "unconfirmed",
]

# Explicit commands from client-bff telemetry.buttons. These set a desired
# state and do not depend on a potentially stale local toggle state.
TELEMETRY_ACTIONS = {
    "lock_close": "centralLockingOn",
    "lock_open": "centralLockingOff",
    "heating_on": "heatingOn",
    "heating_off": "heatingOff",
    "cooling_on": "coolingOn",
    "cooling_off": "coolingOff",
    "trunk_open": "trunkOpen",
    "trunk_close": "trunkClose",
    "blink": "search",
    "trip_prepare_on": "tripPreparationOn",
    "trip_prepare_off": "tripPreparationOff",
}
