import aiohttp
from pydantic import BaseModel
from typing import Dict, Optional

from sandbox_sdk.sandbox.sandbox_connection import SandboxConnection
from sandbox_sdk.constants import ENVD_PORT, SIMPLE_PROCESS_ROUTE


class SimpleProcessResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int


class SimpleProcess:
    def __init__(self, pid: int, manager: "SimpleProcessManager"):
        self.pid = pid
        self._manager = manager

    def get_wait_url(self):
        hostname = self._manager._sandbox.get_sbx_url(ENVD_PORT)
        protocol = self._manager._sandbox.get_protocol(secure=False)

        return f"{protocol}://{hostname}{SIMPLE_PROCESS_ROUTE}/wait"

    def get_kill_url(self):
        hostname = self._manager._sandbox.get_sbx_url(ENVD_PORT)
        protocol = self._manager._sandbox.get_protocol(secure=False)

        return f"{protocol}://{hostname}{SIMPLE_PROCESS_ROUTE}/kill"

    async def wait(self, timeout: Optional[float] = None) -> SimpleProcessResult:
        wait_url = self.get_wait_url()
        request = {"pid": self.pid}
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        async with self._manager._http_client.post(
            wait_url, json=request, timeout=client_timeout
        ) as response:
            if not response.ok:
                text = await response.text()
                raise Exception(f"wait process failed: {response.reason} {text}")
            result = await response.json()
        return SimpleProcessResult.model_validate(result)

    async def kill(self, timeout: Optional[float] = None):
        wait_url = self.get_kill_url()
        request = {"pid": self.pid}
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        async with self._manager._http_client.post(
            wait_url, json=request, timeout=client_timeout
        ) as response:
            if not response.ok:
                text = await response.text()
                raise Exception(f"wait process failed: {response.reason} {text}")


class SimpleProcessManager:
    def __init__(self, sandbox: SandboxConnection):
        self._sandbox = sandbox
        self._http_client = aiohttp.ClientSession()

    def get_start_url(self):
        hostname = self._sandbox.get_sbx_url(ENVD_PORT)
        protocol = self._sandbox.get_protocol(secure=False)

        return f"{protocol}://{hostname}{SIMPLE_PROCESS_ROUTE}/create"

    async def start(
        self,
        cmd: str,
        *,
        env_vars: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        user: Optional[str] = None,
    ):
        request: Dict = {"cmd": cmd}
        if env_vars is not None:
            request["envs"] = env_vars
        if cwd is not None:
            request["cwd"] = cwd
        if user is not None:
            request["user"] = user
        start_url = self.get_start_url()
        async with self._http_client.post(start_url, json=request) as response:
            if not response.ok:
                text = await response.text()
                raise Exception(f"start process failed: {response.reason} {text}")
            result = await response.json()
            pid = result["pid"]
        return SimpleProcess(pid=pid, manager=self)

    async def close(self):
        await self._http_client.close()
