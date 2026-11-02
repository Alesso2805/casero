import asyncio
import signal
import socket

import httpx2
import pytest
import uvicorn
from starlette.responses import PlainTextResponse
from starlette.types import Receive, Scope, Send

from casero.shared.infrastructure.listeners import Listener, serve

pytestmark = pytest.mark.anyio

STOP_WITHIN_SECONDS = 10


async def hello(scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] == "http":
        await PlainTextResponse(f"port {scope['server'][1]}")(scope, receive, send)


def a_listener() -> Listener:
    return Listener(
        uvicorn.Config(hello, host="127.0.0.1", port=0, lifespan="off", log_level="critical")
    )


def port_of(listener: Listener) -> int:
    port: int = listener.servers[0].sockets[0].getsockname()[1]
    return port


async def until_started(*listeners: Listener) -> None:
    async with asyncio.timeout(STOP_WITHIN_SECONDS):
        while not all(listener.started for listener in listeners):
            await asyncio.sleep(0.01)


def refuses_connections(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) != 0


@pytest.mark.parametrize("stop_signal", [signal.SIGTERM, signal.SIGINT])
async def test_one_signal_stops_both_listeners(stop_signal: signal.Signals) -> None:
    public, admin = a_listener(), a_listener()
    running = asyncio.create_task(serve([public, admin]))
    await until_started(public, admin)
    ports = port_of(public), port_of(admin)
    async with httpx2.AsyncClient() as client:
        answers = [(await client.get(f"http://127.0.0.1:{port}/")).text for port in ports]

    signal.raise_signal(stop_signal)
    async with asyncio.timeout(STOP_WITHIN_SECONDS):
        await running

    assert answers == [f"port {port}" for port in ports]
    assert all(refuses_connections(port) for port in ports)


async def test_the_signal_handlers_go_back_as_they_were() -> None:
    before = signal.getsignal(signal.SIGTERM)
    listener = a_listener()
    running = asyncio.create_task(serve([listener]))
    await until_started(listener)
    during = signal.getsignal(signal.SIGTERM)

    listener.should_exit = True
    await running

    assert during != before
    assert signal.getsignal(signal.SIGTERM) == before


async def test_a_listener_that_stops_takes_the_other_down_so_docker_restarts_the_process() -> None:
    public, admin = a_listener(), a_listener()
    running = asyncio.create_task(serve([public, admin]))
    await until_started(public, admin)

    admin.should_exit = True
    async with asyncio.timeout(STOP_WITHIN_SECONDS):
        await running

    assert public.should_exit
