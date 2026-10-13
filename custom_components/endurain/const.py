"""Constants for the Endurain integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "endurain"

CONF_AUTH_TYPE: Final = "auth_type"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_MFA_CODE: Final = "mfa_code"

AUTH_TYPE_API_KEY: Final = "api_key"
AUTH_TYPE_PASSWORD: Final = "password"

DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=15)

SUMMARY_PERIODS: Final = ("week", "month", "year", "lifetime")

# Mirrors ACTIVITY_ID_TO_NAME in the Endurain backend
# (backend/app/activities/activity/utils.py).
ACTIVITY_TYPES: Final[dict[int, str]] = {
    1: "Run",
    2: "Trail run",
    3: "Virtual run",
    4: "Ride",
    5: "Gravel ride",
    6: "MTB ride",
    7: "Virtual ride",
    8: "Lap swimming",
    9: "Open water swimming",
    10: "Workout",
    11: "Walk",
    12: "Hike",
    13: "Rowing",
    14: "Yoga",
    15: "Alpine ski",
    16: "Nordic ski",
    17: "Snowboard",
    18: "Transition",
    19: "Strength training",
    20: "Crossfit",
    21: "Tennis",
    22: "Table tennis",
    23: "Badminton",
    24: "Squash",
    25: "Racquetball",
    26: "Pickleball",
    27: "Commuting ride",
    28: "Indoor ride",
    29: "Mixed surface ride",
    30: "Windsurf",
    31: "Indoor walking",
    32: "Stand up paddling",
    33: "Surf",
    34: "Track run",
    35: "E-Bike ride",
    36: "E-Mountain Bike ride",
    37: "Ice skate",
    38: "Soccer",
    39: "Padel",
    40: "Treadmill",
    41: "Cardio training",
    42: "Kayaking",
    43: "Sailing",
    44: "Snow shoeing",
    45: "Inline skating",
    46: "HIIT",
    47: "Jump rope",
}
