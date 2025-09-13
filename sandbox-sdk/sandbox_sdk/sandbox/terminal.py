from __future__ import annotations


import logging
import asyncio
from asyncio import Event, Task
from typing import Any, Callable, Optional, List

from pydantic import BaseModel

from sandbox_sdk.constants import TIMEOUT
from sandbox_sdk.sandbox.env_vars import EnvVars
from sandbox_sdk.sandbox.exception import (
    MultipleExceptions,
    RpcException,
    TerminalException,
)
from sandbox_sdk.sandbox.sandbox_connection import SandboxConnection, SubscriptionArgs
from sandbox_sdk.utils.id import create_id

logger = logging.getLogger(__file__)


class TerminalOutput(BaseModel):
    data: str = ""

    def _add_data(self, data: str) -> None:
        self.data += data


class Terminal:
    """
    Terminal session.
    """

    @property
    def data(self) -> str:
        """
        Terminal output data.
        """
        return self._output.data

    @property
    def output(self) -> TerminalOutput:
        """
        Terminal output.
        """
        return self._output

    @property
    def finished(self):
        """
        A future that is resolved when the terminal session exits.
        """
        return self._finished

    @property
    def terminal_id(self) -> str:
        """
        The terminal id used to identify the terminal in the session.
        """
        return self._terminal_id

    async def wait(self) -> TerminalOutput:
        """
        Wait till the terminal session exits.
        """
        await self.finished.wait()
        return self._output

    def __init__(
        self,
        terminal_id: str,
        sandbox: SandboxConnection,
        finished: Event,
        output: TerminalOutput,
    ):
        self._terminal_id = terminal_id
        self._sandbox = sandbox
        self._finished = finished
        self._output = output

    async def send_data(self, data: str, timeout: Optional[float] = TIMEOUT) -> None:
        """
        Send data to the terminal standard input.

        :param data: Data to send
        :param timeout: Specify the duration, in seconds to give the method to finish its execution before it times out (default is 60 seconds). If set to None, the method will continue to wait until it completes, regardless of time
        """
        try:
            await self._sandbox._call(
                TerminalManager._service_name,
                "data",
                [self.terminal_id, data],
                timeout=timeout,
            )
        except RpcException as e:
            raise TerminalException(e.message) from e

    async def resize(self, cols: int, rows: int, timeout: Optional[float] = TIMEOUT) -> None:
        """
        Resizes the terminal tty.

        :param cols: Number of columns
        :param rows: Number of rows
        :param timeout: Specify the duration, in seconds to give the method to finish its execution before it times out (default is 60 seconds). If set to None, the method will continue to wait until it completes, regardless of time
        """
        try:
            await self._sandbox._call(
                TerminalManager._service_name,
                "resize",
                [self.terminal_id, cols, rows],
                timeout=timeout,
            )
        except RpcException as e:
            raise TerminalException(e.message) from e

    async def kill(self, timeout: Optional[float] = TIMEOUT) -> None:
        """
        Kill the terminal session.

        :param timeout: Specify the duration, in seconds to give the method to finish its execution before it times out (default is 60 seconds). If set to None, the method will continue to wait until it completes, regardless of time
        """
        try:
            await self._sandbox._call(
                TerminalManager._service_name,
                "destroy",
                [self.terminal_id],
                timeout=timeout,
            )
        except RpcException as e:
            raise TerminalException(e.message) from e
        finally:
            self.finished.set()


class TerminalManager:
    """
    Manager for starting and interacting with terminal sessions in the sandbox.
    """

    _service_name = "terminal"

    def __init__(self, sandbox: SandboxConnection):
        self._sandbox = sandbox

    async def start(
        self,
        on_data: Callable[[str], Any],
        cols: int,
        rows: int,
        cwd: str = "",
        terminal_id: Optional[str] = None,
        on_exit: Optional[Callable[[], Any]] = None,
        cmd: Optional[str] = None,
        env_vars: Optional[EnvVars] = None,
        timeout: Optional[float] = TIMEOUT,
    ) -> Terminal:
        """
        Start a new terminal session.

        :param on_data: Callback that will be called when the terminal sends data
        :param cwd: Working directory where will the terminal start
        :param terminal_id: Unique identifier of the terminal session
        :param on_exit: Callback that will be called when the terminal exits
        :param cols: Number of columns the terminal will have. This affects rendering
        :param rows: Number of rows the terminal will have. This affects rendering
        :param cmd: If the `cmd` parameter is defined it will be executed as a command
        and this terminal session will exit when the command exits
        :param env_vars: Environment variables that will be accessible inside of the terminal
        :param timeout: Specify the duration, in seconds to give the method to finish its execution before it times out (default is 60 seconds). If set to None, the method will continue to wait until it completes, regardless of time

        :return: Terminal session
        """
        env_vars = self._sandbox.env_vars.update(env_vars or {})

        future_exit = asyncio.Event()
        terminal_id = terminal_id or create_id(12)

        output = TerminalOutput()

        def handle_data(data: str):
            output._add_data(data)
            on_data(data)

        try:
            unsub_all = await self._sandbox._handle_subscriptions(
                SubscriptionArgs(
                    service=self._service_name,
                    handler=handle_data,
                    method="onData",
                    params=[terminal_id],
                ),
                SubscriptionArgs(
                    service=self._service_name,
                    handler=lambda _: future_exit.set(),
                    method="onExit",
                    params=[terminal_id],
                ),
            )
        except MultipleExceptions as e:
            raise TerminalException(
                "Failed to subscribe to RPC services necessary for starting terminal"
            ) from e
        except RpcException as e:
            raise TerminalException(e.message) from e

        async def bg_exit_handler():
            await future_exit.wait()

            if unsub_all:
                await unsub_all

            if on_exit:
                on_exit()

        t = asyncio.create_task(bg_exit_handler(), name="terminal-bg-exit-handler")
        self._sandbox._bg_tasks.append(t)

        try:
            if not cwd and self._sandbox.cwd:
                cwd = self._sandbox.cwd

            await self._sandbox._call(
                self._service_name,
                "start",
                [
                    terminal_id,
                    cols,
                    rows,
                    env_vars if env_vars else {},
                    cmd,
                    cwd,
                ],
                timeout=timeout,
            )
            return Terminal(
                terminal_id=terminal_id,
                sandbox=self._sandbox,
                finished=future_exit,
                output=output,
            )
        except RpcException as e:
            future_exit.set()
            raise TerminalException(e.message) from e
        except Exception as e:
            future_exit.set()
            raise e
