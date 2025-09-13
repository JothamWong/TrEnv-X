import asyncio
import logging
import urllib.parse
import aiohttp

from os import path
from typing import Any, Callable, Dict, List, Optional, IO, TypeVar, Union
from typing_extensions import Self

from sandbox_sdk.constants import TIMEOUT, ENVD_PORT, FILE_ROUTE, BACKEND_ADDR
from sandbox_sdk.sandbox.code_snippet import CodeSnippetManager, OpenPort
from sandbox_sdk.sandbox.env_vars import EnvVars
from sandbox_sdk.sandbox.filesystem import FilesystemManager
from sandbox_sdk.sandbox.process import ProcessManager, ProcessMessage
from sandbox_sdk.sandbox.sandbox_connection import SandboxConnection
from sandbox_sdk.sandbox.terminal import TerminalManager
from sandbox_sdk.sandbox.simple_process import SimpleProcessManager

logger = logging.getLogger(__name__)


S = TypeVar(
    "S",
    bound="Sandbox",
)

Action = Callable[[S, Dict[str, Any]], str]


class Sandbox(SandboxConnection):
    """
    Sandbox gives your agent a full cloud development environment that's sandboxed.

    That means:
    - Access to Linux OS
    - Using filesystem (create, list, and delete files and dirs)
    - Run processes
    - Sandboxed - you can run any code
    - Access to the internet

    Check usage docs - https://e2b.dev/docs/sandbox/overview

    These cloud sandboxes are meant to be used for agents. Like a sandboxed playgrounds, where the agent can do whatever it wants.
    """

    template = "default-sandbox"

    @property
    def process(self) -> ProcessManager:
        """
        Process manager used to run commands.
        """
        return self._process

    @property
    def terminal(self) -> TerminalManager:
        """
        Terminal manager used to create interactive terminals.
        """
        return self._terminal

    @property
    def filesystem(self) -> FilesystemManager:
        """
        Filesystem manager used to manage files.
        """
        return self._filesystem

    @property
    def simple_process(self) -> SimpleProcessManager:
        """
        Simple process manager used to run command and involve minimal overhead for sandbox.
        """
        return self._simple_process

    @classmethod
    async def create(
        cls,
        template: Optional[str] = None,
        cwd: Optional[str] = None,
        env_vars: Optional[EnvVars] = None,
        on_scan_ports: Optional[Callable[[List[OpenPort]], Any]] = None,
        on_stdout: Optional[Callable[[ProcessMessage], Any]] = None,
        on_stderr: Optional[Callable[[ProcessMessage], Any]] = None,
        on_exit: Optional[Union[Callable[[int], Any], Callable[[], Any]]] = None,
        metadata: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = TIMEOUT,
        target_addr: str = BACKEND_ADDR,
        connect_rpc: bool = True,
        enable_diff_snapshot: bool = False,
    ):
        """
        Create a new cloud sandbox.

        :param template: ID of the sandbox template or the name of prepared template. If not specified a 'default-sandbox' template will be used.
        Can be one of the following premade sandbox templates or a custom sandbox template ID:
        - `default-sandbox` - A basic sandbox with a Linux environment
        - `default-code-interpreter` - A Python3 sandbox with data analysis tools


        :param api_key: The API key to use, if not provided, the `E2B_API_KEY` environment variable is used
        :param cwd: The current working directory to use
        :param env_vars: A dictionary of environment variables to be used for all processes
        :param on_scan_ports: A callback to handle opened ports
        :param on_stdout: A default callback that is called when stdout with a newline is received from the process
        :param on_stderr: A default callback that is called when stderr with a newline is received from the process
        :param on_exit: A default callback that is called when the process exits
        :param metadata: A dictionary of strings that is stored alongside the running sandbox. You can see this metadata when you list running sandboxes.
        :param timeout: Timeout for sandbox to initialize in seconds, default is 60 seconds
        :param target_addr: The address to use for the API
        :param connect_rpc: Whether connect rpc(SandboxRpc) or not
        :param enable_diff_snapshot: Whether enable diff snapshot on sandbox
        """
        template = template or cls.template
        logger.info(
            f"Creating sandbox {template if isinstance(template, str) else type(template)}"
        )
        obj = cls(
            template=template,
            cwd=cwd,
            env_vars=env_vars,
            on_scan_ports=on_scan_ports,
            on_stdout=on_stdout,
            on_stderr=on_stderr,
            on_exit=on_exit,
            target_addr=target_addr,
        )
        await obj._open(
            metadata=metadata,
            timeout=timeout,
            connect_rpc=connect_rpc,
            enable_diff_snapshot=enable_diff_snapshot,
        )
        assert obj._sandbox is not None
        logger.info(f"sandbox {obj._sandbox.sandbox_id} created")
        return obj

    def __init__(
        self,
        template: str,
        cwd: Optional[str] = None,
        env_vars: Optional[EnvVars] = None,
        on_scan_ports: Optional[Callable[[List[OpenPort]], Any]] = None,
        on_stdout: Optional[Callable[[ProcessMessage], Any]] = None,
        on_stderr: Optional[Callable[[ProcessMessage], Any]] = None,
        on_exit: Optional[Union[Callable[[int], Any], Callable[[], Any]]] = None,
        target_addr: str = BACKEND_ADDR,
    ):
        if cwd and cwd.startswith("~"):
            cwd = cwd.replace("~", "/home/user")

        self._code_snippet = CodeSnippetManager(
            sandbox=self,
            on_scan_ports=on_scan_ports,
        )

        self._on_stdout = on_stdout
        self._on_stderr = on_stderr

        default_env_vars = {"PYTHONUNBUFFERED": "1"}

        self._terminal = TerminalManager(sandbox=self)
        self._filesystem = FilesystemManager(sandbox=self)
        self._process = ProcessManager(
            sandbox=self,
            on_stdout=on_stdout,
            on_stderr=on_stderr,
            on_exit=on_exit,
        )
        self._simple_process = SimpleProcessManager(sandbox=self)
        super().__init__(
            template=template,
            cwd=cwd,
            env_vars={
                **default_env_vars,
                **(env_vars or {}),
            },
            target_addr=target_addr,
            secure=False,
        )
        self._actions: Dict[str, Action[Self]] = {}
        self._http_client = aiohttp.ClientSession()

    def add_action(self, action: Action[Self], name: Optional[str] = None) -> "Sandbox":
        """
        Add a new action. If the name is not specified, it is automatically extracted from the function name.
        An action is a function that takes a sandbox and a dictionary of arguments and returns a string.

        You can use this action with specific integrations like OpenAI to interact with the sandbox and get output for the action.
        :param action: The action to add
        :param name: The name of the action, if not provided, the name of the function will be used

        Example:

            ```python
            from e2b import Sandbox

            def read_file(sandbox, args):
                with open(args["path"], "r") as f:
                    return sandbox.filesystem.read(args.path)

            s = Sandbox()
            s.add_action(read_file)
            s.add_action(name="hello", action=lambda s, args: f"Hello {args['name']}!")
            ```
        """

        if not name:
            name = action.__name__

        self._actions[name] = action

        return self

    def remove_action(self, name: str) -> "Sandbox":
        """
        Remove an action.

        :param name: The name of the action
        """
        del self._actions[name]

        return self

    @property
    def actions(self) -> Dict[str, Action[Self]]:
        """
        Return a dict of added actions.
        """

        return self._actions.copy()

    def action(self, name: Optional[str] = None):
        """
        Decorator to add an action.

        :param name: The name of the action, if not provided, the name of the function will be used
        """

        def _action(action: Action[Self]):
            self.add_action(action=action, name=name or action.__name__)

            return action

        return _action

    # @property
    # def openai(self):
    #     """
    #     OpenAI integration that can be used to get output for the actions added in the sandbox.

    #     Example:

    #         ```python
    #         from e2b import Sandbox

    #         s = Sandbox()
    #         s.openai.actions.run(run)
    #         ```
    #     """

    #     from e2b.templates.openai import OpenAI, Actions

    #     return OpenAI[Self](Actions[Self](self))

    def _handle_start_cmd_logs(self):
        async def start_cmd_monitor():
            cmd = "sudo journalctl --follow --lines=all -o cat _SYSTEMD_UNIT=start_cmd.service"
            p = await self.process.start(
                cmd,
                cwd="/",
                env_vars={},
            )
            await p.wait()

        t = asyncio.create_task(start_cmd_monitor())
        self._bg_tasks.append(t)

    # @classmethod
    # def reconnect(
    #     cls,
    #     sandbox_id: str,
    #     cwd: Optional[str] = None,
    #     env_vars: Optional[EnvVars] = None,
    #     on_scan_ports: Optional[Callable[[List[OpenPort]], Any]] = None,
    #     on_stdout: Optional[Callable[[ProcessMessage], Any]] = None,
    #     on_stderr: Optional[Callable[[ProcessMessage], Any]] = None,
    #     on_exit: Optional[Union[Callable[[int], Any], Callable[[], Any]]] = None,
    #     timeout: Optional[float] = TIMEOUT,
    #     api_key: Optional[str] = None,
    #     domain: str = DOMAIN,
    #     _debug_hostname: Optional[str] = None,
    #     _debug_port: Optional[int] = None,
    #     _debug_dev_env: Optional[Literal["remote", "local"]] = None,
    # ):
    #     """
    #     Reconnects to a previously created sandbox.

    #     :param sandbox_id: ID of the sandbox to reconnect to
    #     :param cwd: The current working directory to use
    #     :param env_vars: A dictionary of environment variables to be used for all processes
    #     :param on_scan_ports: A callback to handle opened ports
    #     :param on_stdout: A default callback that is called when stdout with a newline is received from the process
    #     :param on_stderr: A default callback that is called when stderr with a newline is received from the process
    #     :param on_exit: A default callback that is called when the process exits
    #     :param timeout: Timeout for sandbox to initialize in seconds, default is 60 seconds
    #     :param api_key: The API key to use, if not provided, the `E2B_API_KEY` environment variable is used
    #     :param domain: The domain to use for the API

    #     ```py
    #     sandbox = Sandbox()
    #     id = sandbox.id
    #     sandbox.keep_alive(300)
    #     sandbox.close()

    #     # Reconnect to the sandbox
    #     reconnected_sandbox = Sandbox.reconnect(id)
    #     ```

    #     """

    #     logger.info(f"Reconnecting to sandbox {sandbox_id}")
    #     sandbox_id, client_id = sandbox_id.split("-")
    #     return cls(
    #         cwd=cwd,
    #         env_vars=env_vars,
    #         on_scan_ports=on_scan_ports,
    #         on_stdout=on_stdout,
    #         on_stderr=on_stderr,
    #         on_exit=on_exit,
    #         timeout=timeout,
    #         api_key=api_key,
    #         domain=domain,
    #         _sandbox=models.Sandbox(
    #             sandbox_id=sandbox_id,
    #             client_id=client_id,
    #             template_id=getattr(cls, "sandbox_template_id", "unknown"),
    #         ),
    #     )

    async def _open(
        self,
        metadata: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = TIMEOUT,
        connect_rpc: bool = True,
        enable_diff_snapshot: bool = False,
    ) -> None:
        """
        Open the sandbox.

        :param timeout: Specify the duration, in seconds to give the method to finish its execution before it times out (default is 60 seconds). If set to None, the method will continue to wait until it completes, regardless of time
        """
        logger.info(f"Opening sandbox {self._template}")
        await super()._open(
            metadata=metadata,
            timeout=timeout,
            connect_rpc=connect_rpc,
            enable_diff_snapshot=enable_diff_snapshot,
        )
        assert self._sandbox is not None  # for pyright
        logger.info(f"Sandbox {self._template} ({self._sandbox.sandbox_id}) opened")
        await self._code_snippet._subscribe()

        if self.cwd:
            await self.filesystem.make_dir(self.cwd)

        if self._on_stderr or self._on_stdout:
            self._handle_start_cmd_logs()

    def file_url(self) -> str:
        """
        Return a URL that can be used to upload files to the sandbox via a multipart/form-data POST request.
        This is useful if you're uploading files directly from the browser.
        The file will be uploaded to the user's home directory with the same name.
        If a file with the same name already exists, it will be overwritten.
        """
        hostname = self.get_sbx_url(ENVD_PORT)
        protocol = self.get_protocol(secure=False)

        file_url = f"{protocol}://{hostname}{FILE_ROUTE}"

        return file_url

    async def upload_file(self, file: IO, timeout: Optional[float] = TIMEOUT) -> str:
        """
        Upload a file to the sandbox.
        The file will be uploaded to the user's home (`/home/user`) directory with the same name.
        If a file with the same name already exists, it will be overwritten.

        :param file: The file to upload
        :param timeout: Specify the duration, in seconds to give the method to finish its execution before it times out (default is 60 seconds). If set to None, the method will continue to wait until it completes, regardless of time
        """
        files = {"file": file}
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        async with self._http_client.post(
            self.file_url(), data=files, timeout=client_timeout
        ) as r:
            if r.status != 200:
                text = await r.text()
                raise Exception(f"Failed to upload file: {r.reason} {text}")

        filename = path.basename(file.name)
        return f"/home/user/{filename}"

    async def download_file(
        self, remote_path: str, timeout: Optional[float] = TIMEOUT
    ) -> bytes:
        """
        Download a file from the sandbox and returns it's content as bytes.

        :param remote_path: The path of the file to download
        :param timeout: Specify the duration, in seconds to give the method to finish its execution before it times out (default is 60 seconds). If set to None, the method will continue to wait until it completes, regardless of time
        """
        encoded_path = urllib.parse.quote(remote_path)
        url = f"{self.file_url()}?path={encoded_path}"
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        async with self._http_client.get(url, timeout=client_timeout) as r:
            if r.status != 200:
                raise Exception(
                    f"Failed to download file '{remote_path}'. {r.reason} {r.text}"
                )
            return await r.read()

    async def __aenter__(self):
        return self

    async def close(self):
        await super().close()
        await self._http_client.close()
        await self.simple_process.close()

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.close()
        return False
