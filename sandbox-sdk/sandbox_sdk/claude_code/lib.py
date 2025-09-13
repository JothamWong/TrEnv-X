import logging
from typing import Any, Callable, Optional, Union

from sandbox_sdk import EnvVars, ProcessMessage, Sandbox
from sandbox_sdk.constants import SANDBOX_PORT, TIMEOUT, OPENVSCODE_SERVER_PORT, BACKEND_ADDR
from sandbox_sdk.sandbox.exception import SandboxException
from sandbox_sdk.sandbox.process import Process

logger = logging.getLogger(__name__)


class ClaudeCoder(Sandbox):
    """
    CaludeCode Extension of Sandbox.
    """

    template = "claude-code"

    @classmethod
    async def create(
        cls,
        template: Optional[str] = None,
        cwd: Optional[str] = None,
        env_vars: Optional[EnvVars] = None,
        timeout: Optional[float] = TIMEOUT,
        on_stdout: Optional[Callable[[ProcessMessage], Any]] = None,
        on_stderr: Optional[Callable[[ProcessMessage], Any]] = None,
        on_exit: Optional[Union[Callable[[int], Any], Callable[[], Any]]] = None,
        target_addr: str = BACKEND_ADDR,
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
            target_addr=target_addr,
            **kwargs,
        )
        envs = dict(
            LANG="C.UTF-8",
            LC_ALL="C.UTF-8",
            EDITOR="code",
            VISUAL="code",
            GIT_EDITOR="code --wait",
            OPENVSCODE_SERVER_ROOT="/home/user/.openvscode-server",
        )
        if obj._sandbox is None:
            raise SandboxException("Sandbox is not running.")
        vm_ip = obj._sandbox.private_ip
        # the envd process start will use $(SHELL) -c -l
        # so we can use environment variables here.
        cmd = [
            "${OPENVSCODE_SERVER_ROOT}/bin/openvscode-server",
            "--host 0.0.0.0",
            f"--port {OPENVSCODE_SERVER_PORT}",
            "--without-connection-token",
            f"--server-base-path /{vm_ip}/{OPENVSCODE_SERVER_PORT}",
        ]
        obj._ide = await obj.process.start(" ".join(cmd), env_vars=envs, cwd="/home/user/")
        return obj

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ide: Process

    async def close(self):
        await super().close()

    def get_ide_url(self)->str:
        return self.get_protocol() + "://" + self.get_sbx_url(OPENVSCODE_SERVER_PORT) + "/"
