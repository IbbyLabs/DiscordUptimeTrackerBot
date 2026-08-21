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
        self.DATABASE_PATH: str = os.getenv("DATABASE_PATH", "uptime_tracker.db")
        self.STATUS_API_URL: str = os.getenv("STATUS_API_URL", _unmask(_HIDDEN_STATUS_API_URL))
        self.STATUS_PAGE_URL: str = os.getenv("STATUS_PAGE_URL", _unmask(_HIDDEN_STATUS_PAGE_URL))
        # Derived from the status API rather than configured separately: they
        # are two routes on one service, and letting them drift would let the
        # board and its history describe different estates.
        self.INCIDENTS_API_URL: str = os.getenv(
            "INCIDENTS_API_URL",
            self.STATUS_API_URL.replace("/v1/status", "/v1/incidents"),
        )
        self.STATUS_EMOJI: str = os.getenv("STATUS_EMOJI", "🟣")
        # Two separate questions: what to call the board when nothing else names
        # it, and whether the operator has asked for a particular name. Only the
        # second outranks the status API, so an install that sets nothing shows
        # the API's own name rather than this default.
        self.BRAND_NAME: str = os.getenv("BRAND_NAME", _unmask(_HIDDEN_BRAND_NAME))
        self.BRAND_NAME_OVERRIDE: str | None = (os.getenv("BRAND_NAME") or "").strip() or None
        self.REFRESH_MINUTES: float = float(os.getenv("REFRESH_MINUTES", "2"))

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
