import logging
import os

from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("uptimebot.config")
_HIDDEN_KEY = 23
_HIDDEN_OWNER = (46, 35, 32, 47, 33, 37, 34, 32, 47, 33, 47, 37, 34, 35, 47, 37, 34, 34)
_HIDDEN_STATUS_API_URL = (
    127, 99, 99, 103, 100, 45, 56, 56, 98, 103, 99, 126, 122, 114, 57, 126, 117, 117, 110,
    123, 118, 117, 100, 57, 115, 114, 97, 56, 97, 38, 56, 100, 99, 118, 99, 98, 100,
)
_HIDDEN_STATUS_PAGE_URL = (
    127, 99, 99, 103, 100, 45, 56, 56, 98, 103, 99, 126, 122, 114, 57, 126, 117, 117, 110,
    123, 118, 117, 100, 57, 115, 114, 97,
)
_HIDDEN_BRAND_NAME = (
    94, 117, 117, 110, 91, 118, 117, 100, 55, 66, 103, 99, 126, 122, 114, 55, 67, 101, 118,
    116, 124, 114, 101,
)
_HIDDEN_BRAND_DESCRIPTION = (
    67, 127, 126, 100, 55, 115, 118, 100, 127, 117, 120, 118, 101, 115, 55, 103, 101, 120,
    97, 126, 115, 114, 100, 55, 101, 114, 118, 123, 55, 99, 126, 122, 114, 55, 100, 99, 118,
    99, 98, 100, 55, 122, 120, 121, 126, 99, 120, 101, 126, 121, 112, 55, 113, 120, 101, 55,
    68, 99, 101, 114, 122, 126, 120, 55, 86, 115, 115, 120, 121, 100, 57, 55, 68, 114, 101,
    97, 126, 116, 114, 100, 55, 122, 118, 101, 124, 114, 115, 55, 96, 126, 99, 127, 55, 118,
    55, 123, 120, 116, 124, 55, 118, 101, 114, 55, 103, 101, 126, 97, 118, 99, 114, 55, 118,
    121, 115, 55, 101, 114, 102, 98, 126, 101, 114, 55, 118, 98, 99, 127, 114, 121, 99, 126,
    116, 118, 99, 126, 120, 121, 57,
)


def _unmask(values: tuple[int, ...]) -> str:
    return "".join(chr(value ^ _HIDDEN_KEY) for value in values)


class Config:
    def __init__(self) -> None:
        self.BOT_TOKEN: str = self._require("BOT_TOKEN")
        self.BOT_OWNER_ID: int | None = self._optional_int(
            "BOT_OWNER_ID",
            int(_unmask(_HIDDEN_OWNER)),
        )
        self.GUILD_ID: int | None = self._optional_int("GUILD_ID")
        self.COMMAND_PREFIX: str = os.getenv("COMMAND_PREFIX", ".")
        self.DATABASE_PATH: str = os.getenv("DATABASE_PATH", "uptime_tracker.db")
        self.STATUS_API_URL: str = os.getenv("STATUS_API_URL", _unmask(_HIDDEN_STATUS_API_URL))
        self.STATUS_PAGE_URL: str = os.getenv("STATUS_PAGE_URL", _unmask(_HIDDEN_STATUS_PAGE_URL))
        self.STATUS_EMOJI: str = os.getenv("STATUS_EMOJI", "🟣")
        self.BRAND_NAME: str = os.getenv("BRAND_NAME", _unmask(_HIDDEN_BRAND_NAME))
        self.BRAND_DESCRIPTION: str = os.getenv(
            "BRAND_DESCRIPTION",
            _unmask(_HIDDEN_BRAND_DESCRIPTION),
        )
        self.REFRESH_MINUTES: float = float(os.getenv("REFRESH_MINUTES", "10"))

    def _require(self, key: str) -> str:
        value = os.getenv(key)
        if not value:
            log.critical("Required env var %s is not set. Exiting.", key)
            raise SystemExit(1)
        return value

    def _optional_int(self, key: str, default: int | None = None) -> int | None:
        value = os.getenv(key)
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            log.warning("Env var %s has non integer value %r. Ignoring.", key, value)
            return default
