"""Constants for the Wolink ESL integration."""

import json
from pathlib import Path
from typing import Final

DOMAIN: Final[str] = "wolink_esl"

_MANIFEST_PATH = Path(__file__).parent / "manifest.json"
with open(_MANIFEST_PATH, encoding="utf-8") as _f:
    INTEGRATION_VERSION: Final[str] = json.load(_f).get("version", "0.0.0")

URL_BASE: Final[str] = "/wolink_esl"

JSMODULES: Final[list[dict[str, str]]] = [
    {
        "name": "Wolink ESL Card",
        "filename": "wolink-esl-card.js",
        "version": INTEGRATION_VERSION,
    },
# wolink-esl-card.js imports the editor via import("./wolink-esl-card-editor.js")
    # {
    #     "name": "Wolink ESL Card Editor",
    #     "filename": "wolink-esl-card-editor.js",
    #     "version": INTEGRATION_VERSION,
    # },
]

CONF_DEVICE_MODEL = "device_model"
CONF_MAX_RETRY_COUNT = "max_retry_count"
CONF_AD_TIMEOUT = "advertisement_timeout"
CONF_CONNECT_TIMEOUT = "connect_timeout"

DEFAULT_RETRY_COUNT = 5
DEFAULT_AD_TIMEOUT = 60
DEFAULT_CONNECT_TIMEOUT = 15

CONF_COMPRESS = "compress"
DEFAULT_COMPRESS = True

CONF_MIRROR = "mirror"
DEFAULT_MIRROR = "none"

DISPLAY_STATUSES = ["idle", "sending", "success", "error"]
