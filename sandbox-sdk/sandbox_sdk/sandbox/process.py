from __future__ import annotations

import logging
import re
import inspect
from typing import Any, Callable, ClassVar, Dict, List, Optional, Union, Coroutine
from pydantic import BaseModel
from asyncio import Event
import asyncio

from sandbox_sdk.constants import TIMEOUT
from sandbox_sdk.sandbox.env_vars import EnvVars
from sandbox_sdk.sandbox.exception import (
    MultipleExceptions,
    ProcessException,
    RpcException,
    CurrentWorkingDirectoryDoesntExistException,
    TimeoutException,
)
from sandbox_sdk.sandbox.out import OutStderrResponse, OutStdoutResponse
from sandbox_sdk.sandbox.sandbox_connection import SandboxConnection, SubscriptionArgs
from sandbox_sdk.utils.id import create_id

logger = logging.getLogger(__name__)


class ProcessMessage(BaseModel):
    """
    A message from a process.
    """

    line: str
    error: bool = False
    timestamp: int
    """
    Unix epoch in nanoseconds
    """

    def __str__(self):
        return self.line


class ProcessOutput(BaseModel):
    """
    Output from a process.
    """

    delimiter: ClassVar[str] = "\n"
    messages: List[ProcessMessage] = []

    error: bool = False
    exit_code: Optional[int] = None

    @property
    def stdout(self) -> str:
        """
        The stdout from the process.
        """
        return self.delimiter.join(out.line for out in self.messages if not out.error)

    @property
    def stderr(self) -> str:
        """
        The stderr from the process.
        """
        return self.delimiter.join(out.line for out in self.messages if out.error)

    def _insert_by_timestamp(self, message: ProcessMessage):
        """Insert an out based on its timestamp using insertion sort."""
        i = len(self.messages) - 1
        while i >= 0 and self.messages[i].timestamp > message.timestamp:
            i -= 1
        self.messages.insert(i + 1, message)

    def _add_stdout(self, message: ProcessMessage):
        self._insert_by_timestamp(message)

    def _add_stderr(self, message: ProcessMessage):
        self.error = True
        self._insert_by_timestamp(message)


class Process:
    """
    A process running in the sandbox.
    """

    def __init__(
        self,
        process_id: str,
        sandbox: SandboxConnection,
        unsub_coro: Coroutine[Any, Any, None],
        finished: Event,
        output: ProcessOutput,
    ):
        self._process_id = process_id
        self._sandbox = sandbox
        self._unsub_coro = unsub_coro
        self._finished = finished
        self._output = output

    @property
    def exit_code(self) -> Optional[int]:
        """
        The exit code of the last process started by this manager.
        """
        if not self.finished.is_set():
            raise ProcessException("Process has not finished yet")
        return self.output.exit_code

    @property
    def output(self) -> ProcessOutput:
        """
        The output from the process.
        """
        return self._output

    @property
    def stdout(self) -> str:
        """
        The stdout from the process.
        """
        return self._output.stdout

    @property
    def stderr(self) -> str:
        """
        The stderr from the process.
        """
        return self._output.stderr

    @property
    def error(self) -> bool:
        """
        True if the process has written to stderr.
        """
        return self._output.error

    @property
    def output_messages(self) -> List[ProcessMessage]:
        """
        The output messages from the process.
        """
        return self._output.messages

    @property
    def finished(self):
        """
        An asyncio.Event that is resolved when the process exits.
        """
        return self._finished

    @property
    def process_id(self) -> str:
        """
        The process id used to identify the process in the sandbox.
        This is not the system process id of the process running in the sandbox.
        """
        return self._process_id

    async def wait(self, timeout: Optional[float] = TIMEOUT) -> ProcessOutput:
        """
        Wait for the process to exit.

        :param timeout: Specify the duration, in seconds to give the method to finish its execution before it times out. If set to None, the method will continue to wait until it completes, regardless of time
        """
        try:
            await asyncio.wait_for(self.finished.wait(), timeout)
        except asyncio.TimeoutError as e:
            raise TimeoutException(
                f"Process did not finish within {timeout} seconds: {e}"
            ) from e
        return self._output

    async def send_stdin(self, data: str, timeout: Optional[float] = TIMEOUT) -> None:
        """
        Send data to the process stdin.

        :param data: Data to send
        :param timeout: Specify the duration, in seconds to give the method to finish its execution before it times out (default is 60 seconds). If set to None, the method will continue to wait until it completes, regardless of time
        """
        try:
            await self._sandbox._call(
                ProcessManager._service_name,
                "stdin",
                [self.process_id, data],
                timeout=timeout,
            )
        except RpcException as e:
            raise ProcessException(e.message) from e

    async def kill(self, timeout: Optional[float] = TIMEOUT) -> None:
        """
        Kill the process.

        :param timeout: Specify the duration, in seconds to give the method to finish its execution before it times out (default is 60 seconds). If set to None, the method will continue to wait until it completes, regardless of time
        """
        try:
            await self._sandbox._call(
                ProcessManager._service_name, "kill", [self.process_id], timeout=timeout
            )
        except RpcException as e:
            raise ProcessException(e.message) from e
        finally:
            self.finished.set()


class ProcessManager:
    """
    Manager for starting and interacting with processes in the sandbox.
    """

    _service_name = "process"

    # TODO(huang-jl): remove on_exit handler?
    def __init__(
        self,
        sandbox: SandboxConnection,
        on_stdout: Optional[Callable[[ProcessMessage], Any]] = None,
        on_stderr: Optional[Callable[[ProcessMessage], Any]] = None,
        on_exit: Optional[Union[Callable[[int], Any], Callable[[], Any]]] = None,
    ):
        self._sandbox = sandbox
        self._process_cleanup: List[Callable[[], Any]] = []
        self._on_stdout = on_stdout
        self._on_stderr = on_stderr
        self._on_exit = on_exit

    async def start(
        self,
        cmd: str,
        on_stdout: Optional[Callable[[ProcessMessage], Any]] = None,
        on_stderr: Optional[Callable[[ProcessMessage], Any]] = None,
        on_exit: Optional[Union[Callable[[int], Any], Callable[[], Any]]] = None,
        env_vars: Optional[EnvVars] = None,
        cwd: str = "",
        rootdir: str = "",  # DEPRECATED
        process_id: Optional[str] = None,
        timeout: Optional[float] = TIMEOUT,
    ) -> Process:
        logger.info(f"Starting process: {cmd}")
        env_vars = env_vars or {}
        env_vars = {**self._sandbox.env_vars, **env_vars}

        on_stdout = on_stdout or self._on_stdout
        on_stderr = on_stderr or self._on_stderr
        on_exit = on_exit or self._on_exit

        future_exit = asyncio.Event()
        process_id = process_id or create_id(12)

        output = ProcessOutput()

        def handle_exit(exit_code: int):
            output.exit_code = exit_code
            logger.info(f"Process {process_id} exited with exit code {exit_code}")
            future_exit.set()

        def handle_stdout(data: Dict[Any, Any]):
            out = OutStdoutResponse(**data)

            message = ProcessMessage(
                line=out.line,
                timestamp=out.timestamp,
                error=False,
            )

            output._add_stdout(message)
            if on_stdout:
                try:
                    on_stdout(message)
                except TypeError as error:
                    logger.exception(f"Error in on_stdout callback: {error}")

        def handle_stderr(data: Dict[Any, Any]):
            out = OutStderrResponse(**data)

            message = ProcessMessage(
                line=out.line,
                timestamp=out.timestamp,
                error=True,
            )

            output._add_stderr(message)
            if on_stderr:
                try:
                    on_stderr(message)
                except TypeError as error:
                    logger.exception(f"Error in on_stdout callback: {error}")

        try:
            subscription_args = [
                SubscriptionArgs(
                    service=self._service_name,
                    handler=handle_exit,
                    method="onExit",
                    params=[process_id],
                ),
                SubscriptionArgs(
                    service=self._service_name,
                    handler=handle_stdout,
                    method="onStdout",
                    params=[process_id],
                ),
                SubscriptionArgs(
                    service=self._service_name,
                    handler=handle_stderr,
                    method="onStderr",
                    params=[process_id],
                ),
            ]
            unsub_all = await self._sandbox._handle_subscriptions(*subscription_args)

        except MultipleExceptions as e:
            raise ProcessException(
                "Failed to subscribe to RPC services necessary for starting process"
            ) from e

        logger.info(f"process subscribed (id: {process_id})")

        # create a background coroutine to unsub when exit
        async def bg_exit_handler():
            await future_exit.wait()
            if on_exit:
                sig = inspect.signature(on_exit)
                params = sig.parameters.values()
                try:
                    if len(params) == 0:
                        on_exit()
                    else:
                        on_exit(output.exit_code or 0)
                except TypeError as error:
                    logger.exception(f"Error in on_exit callback: {error}")
            if unsub_all:
                await unsub_all
            logger.info(f"unsub all (id: {process_id})")

        t = asyncio.create_task(bg_exit_handler(), name="process-bg-exit-handler")
        self._sandbox._bg_tasks.append(t)

        try:
            if not cwd and rootdir:
                cwd = rootdir
                logger.warning("The rootdir parameter is deprecated, use cwd instead.")

            if not cwd and self._sandbox.cwd:
                cwd = self._sandbox.cwd

            await self._sandbox._call(
                self._service_name,
                "start",
                [
                    process_id,
                    cmd,
                    env_vars,
                    cwd,
                ],
                timeout=timeout,
            )
            logger.info(f"Started process (id: {process_id})")
            return Process(
                output=output,
                sandbox=self._sandbox,
                process_id=process_id,
                unsub_coro=unsub_all,
                finished=future_exit,
            )
        except RpcException as e:
            future_exit.set()
            if re.match(
                r"error starting process '\w+': fork/exec /bin/bash: no such file or directory",
                e.message,
            ):
                raise CurrentWorkingDirectoryDoesntExistException(
                    "Failed to start the process. You are trying set `cwd` to a directory that does not exist."
                ) from e
            raise ProcessException(e.message) from e
        except Exception as e:
            future_exit.set()
            raise e

    async def start_and_wait(
        self,
        cmd: str,
        on_stdout: Optional[Callable[[ProcessMessage], Any]] = None,
        on_stderr: Optional[Callable[[ProcessMessage], Any]] = None,
        on_exit: Optional[Callable[[int], Any]] = None,
        env_vars: Optional[EnvVars] = None,
        cwd: str = "",
        process_id: Optional[str] = None,
        timeout: Optional[float] = TIMEOUT,
    ) -> ProcessOutput:
        p = await self.start(
            cmd,
            on_stdout=on_stdout,
            on_stderr=on_stderr,
            on_exit=on_exit,
            env_vars=env_vars,
            cwd=cwd,
            process_id=process_id,
            timeout=timeout,
        )
        return await p.wait(timeout=timeout)
