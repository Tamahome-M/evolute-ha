"""Constants for the Evolute integration."""

DOMAIN = "evolute"

CONF_CAR_ID = "car_id"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_TIMEOUT = "timeout"
CONF_TOKEN_REFRESH_INTERVAL = "token_refresh_interval"

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
REFRESH_URL = f"{BASE_URL}/id-service/auth/refresh-token"

# Per-request timeouts (seconds) — matches the official app: 20s for normal
# commands, 60s for the longer-running preparation flow.
COMMAND_TIMEOUT = 20
PREPARE_TIMEOUT = 60

# Toggle/push commands. These hit POST /car-service/tbox/v1/{car_id}/{command}
# with an empty body — the server flips the state based on the command name,
# so the "skip if already in target state" value guards against an accidental
# double-toggle. The command names below are the real ones returned in the
# `buttons` array of the /info response.
#
#   tuple = (command_name, status_key_in_sensorsData, skip_if_value)
#
# status_key None  → never skip (push commands like blink).
INTELLIGENT_ACTIONS = {
    "lock_close": ("centralLockingToggle", "centralLockingStatus", 1),  # пропустить если уже закрыт
    "lock_open":  ("centralLockingToggle", "centralLockingStatus", 0),  # пропустить если уже открыт
    "heating_on":  ("heating",  "climateStatus", 1),
    "heating_off": ("heating",  "climateStatus", 0),
    "cooling_on":  ("cooling",  "climateStatus", 1),
    "cooling_off": ("cooling",  "climateStatus", 0),
    "trunk_open":  ("trunkToggle", "trunkStatus", 1),   # было trunkOpen — несуществующая команда
    "trunk_close": ("trunkToggle", "trunkStatus", 0),
    "blink":       ("blink", None, None),   # push — сигнал клаксоном + мигание фар («Поиск»)
}

# --- Preparation (предпрогрев) -------------------------------------------------
# Sent as POST /car-service/tbox/v1/{car_id}/PREPARE with a JSON body
#   {"value": {flSeatHeating, frSeatHeating, rlSeatHeating, rrSeatHeating,
#              wheelHeating, time, temp}}
# CANCEL stops a running preparation (empty body).
PREPARE_COMMAND = "PREPARE"
CANCEL_COMMAND = "CANCEL"

# Picker ranges / defaults taken from the app.
PREPARE_TEMP_MIN = 16
PREPARE_TEMP_MAX = 30
PREPARE_TEMP_DEFAULT = 22

PREPARE_DURATION_MIN = 1
PREPARE_DURATION_MAX = 30
PREPARE_DURATION_DEFAULT = 10

PREPARE_SEAT_MIN = 0
PREPARE_SEAT_MAX = 3       # 0 = выкл
PREPARE_WHEEL_MAX = 1      # руль: 0/1

# Keys used for the in-memory prepare parameter store on the coordinator.
PREPARE_PARAM_KEYS = ("temp", "time", "fl", "fr", "rl", "rr", "wheel")
PREPARE_DEFAULTS = {
    "temp": PREPARE_TEMP_DEFAULT,
    "time": PREPARE_DURATION_DEFAULT,
    "fl": 0,
    "fr": 0,
    "rl": 0,
    "rr": 0,
    "wheel": 0,
}
