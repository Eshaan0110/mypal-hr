"""The chat concurrency limit: extra questions wait without a thread, then get a clean 503."""

from types import SimpleNamespace

import anyio
import pytest

from mypal.api.chat import chat_slot
from mypal.config import Settings
from mypal.errors import AppError


def _request(settings: Settings) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))


def test_a_question_waits_for_a_free_slot_then_proceeds(settings: Settings) -> None:
    request = _request(settings.model_copy(update={"chat_max_concurrent": 1}))
    order: list[str] = []

    async def ask(name: str, hold: float) -> None:
        async with _slot(request):
            order.append(f"{name} in")
            await anyio.sleep(hold)
            order.append(f"{name} out")

    async def main() -> None:
        async with anyio.create_task_group() as tg:
            tg.start_soon(ask, "first", 0.2)
            await anyio.sleep(0.05)
            tg.start_soon(ask, "second", 0)

    anyio.run(main)
    assert order == ["first in", "first out", "second in", "second out"]


def test_a_question_that_cannot_start_in_time_gets_busy(settings: Settings) -> None:
    request = _request(
        settings.model_copy(update={"chat_max_concurrent": 1, "chat_queue_timeout_seconds": 0.1})
    )

    async def main() -> None:
        async with _slot(request):  # the only slot is taken
            with pytest.raises(AppError) as busy:
                async with _slot(request):
                    pass
            assert (busy.value.status_code, busy.value.code) == (503, "server_busy")
        async with _slot(request):  # released again afterwards
            pass

    anyio.run(main)


class _slot:
    """Drive the FastAPI generator dependency like FastAPI does."""

    def __init__(self, request: SimpleNamespace) -> None:
        self._gen = chat_slot(request)

    async def __aenter__(self) -> None:
        await anext(self._gen)

    async def __aexit__(self, *exc: object) -> None:
        await self._gen.aclose()
