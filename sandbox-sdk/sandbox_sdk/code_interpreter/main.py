from __future__ import annotations

import logging
import uuid
import aiohttp

import asyncio
from asyncio import Future

from typing import Any, Callable, List, Optional, Dict

from sandbox_sdk import EnvVars, ProcessMessage, Sandbox
from sandbox_sdk.constants import TIMEOUT

from .messaging import JupyterKernelWebSocket
from .models import KernelException, Execution, Result

logger = logging.getLogger(__name__)


class CodeInterpreter(Sandbox):
    """
    E2B code interpreter sandbox extension.
    """

    template = "default-code-interpreter"

    @classmethod
    async def create(
        cls,
        template: Optional[str] = None,
        cwd: Optional[str] = None,
        env_vars: Optional[EnvVars] = None,
        timeout: Optional[float] = TIMEOUT,
        on_stdout: Optional[Callable[[ProcessMessage], Any]] = None,
        on_stderr: Optional[Callable[[ProcessMessage], Any]] = None,
        on_exit: Optional[Callable[[int], Any]] = None,
        **kwargs,
    ):
        obj = await super().create(
            template=template or cls.template,
            cwd=cwd,
            env_vars=env_vars,
            timeout=timeout,
            on_stdout=on_stdout,
            on_stderr=on_stderr,
            on_exit=on_exit,
            **kwargs,
        )
        await obj.notebook._start_connecting_to_default_kernel(timeout=timeout)
        return obj

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.notebook: JupyterExtension = JupyterExtension(self)

    async def close(self):
        await super().close()
        if self.notebook:
            await self.notebook.close()


class JupyterExtension:
    def __init__(self, sandbox: CodeInterpreter):
        self._sandbox = sandbox
        self._connected_kernels: Dict[str, Future[JupyterKernelWebSocket]] = {}
        self._default_kernel_id: Optional[str] = None
        self._http_client = aiohttp.ClientSession()

    async def exec_cell(
        self,
        code: str,
        kernel_id: Optional[str] = None,
        on_stdout: Optional[Callable[[ProcessMessage], Any]] = None,
        on_stderr: Optional[Callable[[ProcessMessage], Any]] = None,
        on_result: Optional[Callable[[Result], Any]] = None,
        timeout: Optional[float] = TIMEOUT,
    ) -> Execution:
        """
        Execute code in a notebook cell.

        :param code: Code to execute
        :param kernel_id: The ID of the kernel to execute the code on. If not provided, the default kernel is used.
        :param on_stdout: A callback function to handle standard output messages from the code execution.
        :param on_stderr: A callback function to handle standard error messages from the code execution.
        :param on_result: A callback function to handle the result and display calls of the code execution.
        :param timeout: Timeout for the call

        :return: Result of the execution
        """
        kernel_id = kernel_id or self.default_kernel_id
        ws_future = self._connected_kernels.get(kernel_id)

        logger.debug(f"Executing code in kernel {kernel_id}")

        if ws_future:
            logger.debug(f"Using existing websocket connection to kernel {kernel_id}")
            ws = await asyncio.wait_for(ws_future, timeout=timeout)
        else:
            logger.debug(f"Creating new websocket connection to kernel {kernel_id}")
            ws = await self._connect_to_kernel_ws(kernel_id, None, timeout=timeout)

        message_id = await ws.send_execution_message(
            code, on_stdout, on_stderr, on_result
        )
        logger.debug(
            f"Sent execution message to kernel {kernel_id}, message_id: {message_id}"
        )

        result = await ws.get_result(message_id, timeout=timeout)
        logger.debug(
            f"Received result from kernel {kernel_id}, message_id: {message_id}, result: {result}"
        )

        return result

    @property
    def default_kernel_id(self) -> str:
        """
        Get the default kernel id

        :return: Default kernel id
        """
        if not self._default_kernel_id:
            raise KernelException("jupter default kernel has not been connected")

        return self._default_kernel_id

    async def create_kernel(
        self,
        cwd: str = "/home/user",
        kernel_name: Optional[str] = None,
        timeout: Optional[float] = TIMEOUT,
    ) -> str:
        """
        Creates a new kernel, this can be useful if you want to have multiple independent code execution environments.

        The kernel can be optionally configured to start in a specific working directory and/or
        with a specific kernel name. If no kernel name is provided, the default kernel will be used.
        Once the kernel is created, this method establishes a WebSocket connection to the new kernel for
        real-time communication.

        :param cwd: Sets the current working directory for the kernel. Defaults to "/home/user".
        :param kernel_name:
            Specifies which kernel should be used, useful if you have multiple kernel types.
            If not provided, the default kernel will be used.
        :param timeout: Timeout for the kernel creation request.
        :return: Kernel id of the created kernel
        """
        kernel_name = kernel_name or "python3"

        data = {
            "path": str(uuid.uuid4()),
            "kernel": {"name": kernel_name},
            "type": "notebook",
            "name": str(uuid.uuid4()),
        }
        logger.debug(f"Creating kernel with data: {data}")

        async with self._http_client.post(
            f"{self._sandbox.get_protocol()}://{self._sandbox.get_sbx_url(8888)}/api/sessions",
            json=data,
            timeout=timeout,
        ) as response:
            if not response.ok:
                text = await response.text()
                raise KernelException(f"Failed to create kernel: {text}")

            session_data = await response.json()
            session_id = session_data["id"]
            kernel_id = session_data["kernel"]["id"]
        async with self._http_client.patch(
            f"{self._sandbox.get_protocol()}://{self._sandbox.get_sbx_url(8888)}/api/sessions/{session_id}",
            json={"path": cwd},
            timeout=timeout,
        ) as response:
            if not response.ok:
                raise KernelException(f"Failed to create kernel: {response.text}")
        logger.debug(f"Created kernel {kernel_id}")
        return kernel_id

    async def restart_kernel(
        self, kernel_id: Optional[str] = None, timeout: Optional[float] = TIMEOUT
    ) -> None:
        """
        Restarts an existing Jupyter kernel. This can be useful to reset the kernel's state or to recover from errors.

        :param kernel_id: The unique identifier of the kernel to restart. If not provided, the default kernel is restarted.
        :param timeout: The timeout in milliseconds for the kernel restart request.
        """
        kernel_id = kernel_id or self.default_kernel_id
        logger.debug(f"Restarting kernel {kernel_id}")

        # the kernel_id must in self._connected_kernels
        ws = await self._connected_kernels[kernel_id]
        await ws.close()
        del self._connected_kernels[kernel_id]
        logger.debug(f"Closed websocket connection to kernel {kernel_id}")

        async with self._http_client.post(
            f"{self._sandbox.get_protocol()}://{self._sandbox.get_sbx_url(8888)}/api/kernels/{kernel_id}/restart",
            timeout=timeout,
        ) as response:
            if not response.ok:
                raise KernelException(f"Failed to restart kernel {kernel_id}")
        logger.debug(f"Restarted kernel {kernel_id}")

    async def shutdown_kernel(
        self, kernel_id: Optional[str] = None, timeout: Optional[float] = TIMEOUT
    ) -> None:
        """
        Shuts down an existing Jupyter kernel. This method is used to gracefully terminate a kernel's process.

        :param kernel_id: The unique identifier of the kernel to shutdown. If not provided, the default kernel is shutdown.
        :param timeout: The timeout for the kernel shutdown request.
        """
        kernel_id = kernel_id or self.default_kernel_id
        logger.debug(f"Shutting down kernel {kernel_id}")

        ws = await self._connected_kernels[kernel_id]
        await ws.close()
        del self._connected_kernels[kernel_id]
        logger.debug(f"Closed websocket connection to kernel {kernel_id}")

        async with self._http_client.delete(
            f"{self._sandbox.get_protocol()}://{self._sandbox.get_sbx_url(8888)}/api/kernels/{kernel_id}",
            timeout=timeout,
        ) as response:
            if not response.ok:
                raise KernelException(f"Failed to shutdown kernel {kernel_id}")
        logger.debug(f"Shutdown kernel {kernel_id}")

    async def list_kernels(self, timeout: Optional[float] = TIMEOUT) -> List[str]:
        """
        Lists all available Jupyter kernels.

        This method fetches a list of all currently available Jupyter kernels from the server. It can be used
        to retrieve the IDs of all kernels that are currently running or available for connection.

        :param timeout: The timeout for the kernel list request.
        :return: List of kernel ids
        """
        async with self._http_client.get(
            f"{self._sandbox.get_protocol()}://{self._sandbox.get_sbx_url(8888)}/api/kernels",
            timeout=timeout,
        ) as response:
            if not response.ok:
                raise KernelException(f"Failed to list kernels: {response.text}")
            return [kernel["id"] for kernel in await response.json()]

    async def interrupt_kernel(
        self, kernel_id: Optional[str] = None, timeout: float = TIMEOUT
    ):
        kernel_id = kernel_id or self._default_kernel_id
        logger.debug(f"interrupt kernel {kernel_id}")
        async with self._http_client.post(
            f"{self._sandbox.get_protocol()}://{self._sandbox.get_sbx_url(8888)}/api/kernels/{kernel_id}/interrupt",
            timeout=timeout,
        ) as response:
            if not response.ok:
                raise KernelException(f"Failed to interrupt kernel {kernel_id}")
        logger.debug(f"Interrupted kernel {kernel_id}")

    async def close(self):
        """
        Close all the websocket connections to the kernels. It doesn't shutdown the kernels.
        """
        logger.debug("Closing all websocket connections")
        for ws_fut in self._connected_kernels.values():
            ws = await ws_fut
            await ws.close()
        await self._http_client.close()

    async def _connect_to_kernel_ws(
        self,
        kernel_id: str,
        session_id: Optional[str],
        timeout: Optional[float] = TIMEOUT,
    ) -> JupyterKernelWebSocket:
        """
        Establishes a WebSocket connection to a specified Jupyter kernel.

        :param kernel_id: Kernel id
        :param timeout: The timeout for the kernel connection request.

        :return: Websocket connection
        """
        logger.debug(f"Connecting to kernel's ({kernel_id}) websocket")
        fut = asyncio.get_running_loop().create_future()
        self._connected_kernels[kernel_id] = fut

        session_id = session_id or str(uuid.uuid4())
        ws = JupyterKernelWebSocket(
            url=f"{self._sandbox.get_protocol('ws')}://{self._sandbox.get_sbx_url(8888)}/api/kernels/{kernel_id}/channels",
            session_id=session_id,
        )
        await ws.connect(timeout=timeout)
        logger.debug(f"Connected to kernel's ({kernel_id}) websocket.")

        fut.set_result(ws)
        return ws

    async def _start_connecting_to_default_kernel(
        self, timeout: Optional[float] = TIMEOUT
    ) -> None:
        """
        Start connecting to the default kernel in a separate thread to avoid blocking the main thread.
        :param timeout: Timeout for the call
        """
        logger.debug("Starting to connect to the default kernel")
        kernel_id = await self._sandbox.filesystem.read(
            "/home/user/.jupyter/kernel_id", timeout=timeout
        )
        kernel_id = kernel_id.strip()

        logger.debug(f"Default kernel id: {kernel_id}")
        await self._connect_to_kernel_ws(kernel_id, None, timeout=timeout)
        self._default_kernel_id = kernel_id
