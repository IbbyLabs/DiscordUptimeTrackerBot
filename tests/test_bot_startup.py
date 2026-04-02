import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bot


class DummyServerError(Exception):
    pass


class DummyHTTPError(Exception):
    pass


SyncEffect = BaseException | list[object]


class DummyTree:
    def __init__(self, side_effects: list[SyncEffect]) -> None:
        self._side_effects = list(side_effects)
        self.copy_calls: list[int] = []
        self.sync_calls: list[int | None] = []

    def copy_global_to(self, *, guild: object) -> None:
        self.copy_calls.append(getattr(guild, "id"))

    async def sync(self, *, guild: object | None = None) -> list[object]:
        self.sync_calls.append(getattr(guild, "id", None))
        effect = self._side_effects.pop(0)
        if isinstance(effect, BaseException):
            raise effect
        return effect


def test_sync_app_commands_retries_discord_server_errors() -> None:
    async def run() -> None:
        tree = DummyTree(
            [
                DummyServerError("503"),
                DummyServerError("503"),
                [object(), object()],
            ]
        )
        sleep_mock = AsyncMock()

        with patch.object(bot.discord, "DiscordServerError", DummyServerError), patch.object(
            bot.asyncio, "sleep", sleep_mock
        ):
            synced = await bot.sync_app_commands(tree, 123)

        assert synced is True
        assert tree.copy_calls == [123]
        assert tree.sync_calls == [123, 123, 123]
        assert sleep_mock.await_args_list[0].args == (2.0,)
        assert sleep_mock.await_args_list[1].args == (5.0,)

    asyncio.run(run())


def test_sync_app_commands_allows_startup_after_http_exception() -> None:
    async def run() -> None:
        tree = DummyTree([DummyHTTPError("400")])
        sleep_mock = AsyncMock()

        with patch.object(bot.discord, "HTTPException", DummyHTTPError), patch.object(
            bot.asyncio, "sleep", sleep_mock
        ):
            synced = await bot.sync_app_commands(tree, None)

        assert synced is False
        assert tree.copy_calls == []
        assert tree.sync_calls == [None]
        sleep_mock.assert_not_awaited()

    asyncio.run(run())
