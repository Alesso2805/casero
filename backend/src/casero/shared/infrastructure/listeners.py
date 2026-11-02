import asyncio
import contextlib
import signal
from collections.abc import Iterator, Sequence
from types import FrameType

import uvicorn

STOP_SIGNALS = (signal.SIGINT, signal.SIGTERM)


class Listener(uvicorn.Server):
    """A Uvicorn server that leaves the signals to `serve`.

    Uvicorn's own handling would stop only the last server to start, and it re-raises the signal
    as soon as a server finishes, which kills the process before the other one has shut down.
    """

    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


async def serve(listeners: Sequence[Listener]) -> None:
    """Runs the listeners in one event loop (ADR-0008) and stops them all together."""

    def stop(_signal: int | None = None, _frame: FrameType | None = None) -> None:
        for listener in listeners:
            listener.should_exit = True

    previous = {stop_signal: signal.signal(stop_signal, stop) for stop_signal in STOP_SIGNALS}
    try:
        running = [asyncio.create_task(listener.serve()) for listener in listeners]
        await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
        stop()
        await asyncio.gather(*running)
    finally:
        for stop_signal, handler in previous.items():
            signal.signal(stop_signal, handler)
