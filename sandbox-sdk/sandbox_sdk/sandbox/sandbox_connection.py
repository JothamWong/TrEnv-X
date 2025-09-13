import logging
import traceback
import uuid

import asyncio
from typing import Any, Callable, Coroutine, List, Optional, Union, Dict
from datetime import datetime
from pydantic import BaseModel
import grpc
from google.protobuf import empty_pb2 as google_dot_protobuf_dot_empty__pb2

from sandbox_sdk.api import (
    AsyncOrchestratorClient,
    SandboxCreateRequest,
    SandboxListResponse,
    SandboxDeactivateRequest,
    SandboxDeleteRequest,
    SandboxCreateResponse,
    SandboxSnapshotRequest,
    SandboxSnapshotResponse,
)
from sandbox_sdk.constants import (
    BACKEND_ADDR,
    SANDBOX_PORT,
    TIMEOUT,
    ENVD_PORT,
    WS_ROUTE,
    SECURE,
    ORCHESTRATOR_PORT,
)
from sandbox_sdk.sandbox.env_vars import EnvVars
from sandbox_sdk.sandbox.exception import (
    MultipleExceptions,
    SandboxException,
    SandboxNotOpenException,
)
from sandbox_sdk.sandbox.sandbox_rpc import Notification, SandboxRpc
from sandbox_sdk.utils.str import camel_case_to_snake_case

logger = logging.getLogger(__name__)


class SandboxMeta(BaseModel):
    sandbox_id: str
    template_id: str
    kernel_version: str
    max_instance_length: int
    metadata: dict[str, str]
    private_ip: str
    enable_diff_snapshot: bool


class Subscription(BaseModel):
    service: str
    id: str
    handler: Callable[[Any], None]


class SubscriptionArgs(BaseModel):
    service: str
    handler: Callable[[Any], None]
    method: str
    params: List[Any] = []


class RunningSandbox(BaseModel):
    sandbox_id: str
    template_id: str
    # alias: Optional[str]
    metadata: Optional[Dict[str, str]]
    # cpu_count: int
    # memory_mb: int
    started_at: datetime


class SandboxConnection:
    _on_close_child: Optional[Callable[[], Any]] = None

    @property
    def id(self) -> str:
        """
        The sandbox ID.

        You can use this ID to reconnect to the sandbox later.
        """
        if not self._sandbox:
            raise SandboxException("Sandbox is not running.")
        return self._sandbox.sandbox_id

    @property
    def is_open(self) -> bool:
        """
        Whether the sandbox is open.
        """
        return self._is_open

    @property
    def orchestrator_client(self) -> AsyncOrchestratorClient:
        if self._orchestrator_client is None:
            self._orchestrator_client = AsyncOrchestratorClient(
                f"{self._target_addr}:{ORCHESTRATOR_PORT}"
            )
        return self._orchestrator_client

    def __init__(
        self,
        template: str,
        cwd: Optional[str] = None,
        env_vars: Optional[EnvVars] = None,
        target_addr: Optional[str] = None,
        sandbox_port: Optional[str] = None,
        secure: bool = False,  # whether enable SSL
    ):
        self.cwd = cwd
        """
        Default working directory used in the sandbox.

        You can change the working directory by setting the `cwd` property.
        """
        self.env_vars = env_vars or {}
        """
        Default environment variables used in the sandbox.

        You can change the environment variables by setting the `env_vars` property.
        """
        self._template = template
        self._target_addr = target_addr or BACKEND_ADDR
        self._sandbox_port = sandbox_port or SANDBOX_PORT

        self._is_open = False
        self._process_cleanup: List[Callable[[], Any]] = []
        self._subscribers: Dict[str, Subscription] = {}
        self._rpc: Optional[SandboxRpc] = None
        self._secure = secure
        self._sandbox: Optional[SandboxMeta] = None
        self._bg_tasks: List[asyncio.Task] = []
        self._orchestrator_client: Optional[AsyncOrchestratorClient] = None

    def get_sbx_url(self, port: Optional[int] = None) -> str:
        """
        Get the url for the sandbox or for the specified sandbox's port.

        :param port: Specify if you want to connect to a specific port within the sandbox

        :return: Hostname of the sandbox or sandbox's port
        """

        if not self._sandbox:
            raise SandboxException("Sandbox is not running.")

        # url = f"{self._target_addr}:{self._sandbox_port}/{self._sandbox.sandbox_id}"
        # NOTE(huang-jl): although use sandbox_id is an elegant method
        # but there is distinct latency for name server to update the ip of the VM.
        # So I decide to use private ip address directly.
        url = f"{self._target_addr}:{self._sandbox_port}/{self._sandbox.private_ip}"

        if port:
            url += f"/{port}"

        return url

    @staticmethod
    def get_protocol(base_protocol: str = "http", secure: bool = SECURE) -> str:
        """
        The function decides whether to use the secure or insecure protocol.

        :param base_protocol: Specify the specific protocol you want to use. Do not include the `s` in `https` or `wss`.
        :param secure: Specify whether you want to use the secure protocol or not.

        :return: Protocol for the connection to the sandbox
        """
        return f"{base_protocol}s" if secure else base_protocol

    async def close(self) -> None:
        """
        Close the sandbox and unsubscribe from all the subscriptions.
        """
        await self._close()
        if self._sandbox:
            logger.info(f"Sandbox {self._sandbox.template_id} (id: {self.id}) closed")

    async def _close(self):
        for t in self._bg_tasks:
            t.cancel()

        if self._orchestrator_client:
            await self._orchestrator_client.close()
        if self._is_open and self._sandbox:
            logger.debug(f"Closing sandbox {self._sandbox.template_id} (id: {self.id})")
            self._is_open = False
            if self._rpc:
                await self._rpc.close()

        if self._on_close_child:
            self._on_close_child()
        # TODO(huang-jl): kill sandbox when close?

    async def _open(
        self,
        metadata: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = TIMEOUT,
        connect_rpc: bool = True,
        enable_diff_snapshot: bool = False,
    ) -> None:
        """
        Open a connection to a new sandbox.

        You must call this method before using the sandbox.
        """
        if self._is_open:
            raise SandboxException("Sandbox connect was already called")
        else:
            self._is_open = True

        sandbox_id = str(uuid.uuid4())
        req = SandboxCreateRequest(
            templateID=self._template,
            # TODO(huang-jl): Utilize this option
            maxInstanceLength=3,
            sandboxID=sandbox_id,
            enableDiffSnapshots=enable_diff_snapshot,
            metadata=metadata,
        )
        try:
            res: SandboxCreateResponse = await self.orchestrator_client.Create(
                req, timeout=timeout
            )
        except grpc.RpcError as e:
            logger.error(f"failed to create a sandbox: {e}")
            await self._close()
            raise e
        except Exception as e:
            logger.error(f"Failed to acquire sandbox")
            await self._close()
            raise e
        self._sandbox = SandboxMeta(
            sandbox_id=sandbox_id,
            template_id=res.info.templateID,
            kernel_version=res.info.kernelVersion,
            metadata=metadata if metadata else {},
            max_instance_length=req.maxInstanceLength,
            private_ip=res.info.privateIP,
            enable_diff_snapshot=res.info.enableDiffSnapshots,
        )
        # TODO(huang-jl): add something like refresh as e2b?
        logger.debug(f"Sandbox {self._template} created in the backend")

        if not connect_rpc:
            return

        try:
            await self._connect_rpc(timeout)
        except Exception as e:
            logger.error(f"connect rpc to sandbox {self.id} failed: {e}")
            await self._close()
            raise SandboxException(
                f"connect rpc to sandbox {self.id} failed: {e}"
            ) from e
        else:
            logger.debug(f"Sandbox {self._template} connected to envd websocket")

    async def _connect_rpc(self, timeout: Optional[float] = TIMEOUT):
        if not self._sandbox:
            raise SandboxException("Sandbox is not running.")
        protocol = self.get_protocol("ws", self._secure)
        sbx_main_url = self.get_sbx_url(ENVD_PORT)
        sandbox_url = f"{protocol}://{sbx_main_url}{WS_ROUTE}"

        logger.debug(f"connect rpc with url {sandbox_url}")

        self._rpc = SandboxRpc(
            url=sandbox_url,
            on_message=self._handle_notification,
        )
        await self._rpc.connect(timeout=timeout)

    async def _call(
        self,
        service: str,
        method: str,
        params: Optional[List[Any]] = None,
        timeout: Optional[float] = TIMEOUT,
    ) -> Any:
        if not params:
            params = []
        if not self.is_open:
            raise SandboxNotOpenException("Sandbox is not open")
        if not self._rpc:
            raise SandboxException("Sandbox is not connected")

        return await self._rpc.send_rpc(f"{service}_{method}", params, timeout)

    async def _handle_subscriptions(
        self,
        *subscription_args: SubscriptionArgs,
    ) -> Coroutine[Any, Any, None]:
        """
        The returned coroutine need to be await in order to unsubscribe
        """
        results: List[Union[Coroutine[Any, Any, None], Exception]] = []
        tasks = []
        for args in subscription_args:
            fut = self._subscribe(args.service, args.handler, args.method, *args.params)
            tasks.append(fut)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        process_exceptions = [e for e in results if isinstance(e, Exception)]

        async def unsub_all():
            for unsub in results:
                # unsub() will return a coroutine,
                # in which will call _unsubscribe()
                if not isinstance(unsub, Exception):
                    await unsub()

        unsub_coro = unsub_all()

        if len(process_exceptions) > 0:
            await unsub_coro

            if len(process_exceptions) == 1:
                raise process_exceptions[0]

            error_message = "\n"

            for i, s in enumerate(process_exceptions):
                tb = s.__traceback__  # Get the traceback object
                stack_trace = "\n".join(traceback.extract_tb(tb).format())
                error_message += f'\n[{i}]: {type(s).__name__}("{s}"):\n{stack_trace}\n'

            raise MultipleExceptions(
                message=error_message,
                exceptions=process_exceptions,
            )

        return unsub_coro

    async def _unsubscribe(self, sub_id: str, timeout: Optional[float] = TIMEOUT):
        sub = self._subscribers[sub_id]
        await self._call(sub.service, "unsubscribe", [sub.id], timeout=timeout)
        del self._subscribers[sub_id]
        logger.debug(f"Unsubscribed (sub_id: {sub_id})")

    async def _subscribe(
        self,
        service: str,
        handler: Callable[[Any], Any],
        method: str,
        *params,
        timeout: Optional[float] = TIMEOUT,
    ) -> Callable[[], Coroutine[Any, Any, None]]:
        sub_id = await self._call(
            service, "subscribe", [method, *params], timeout=timeout
        )
        if not isinstance(sub_id, str):
            raise SandboxException(
                f"Failed to subscribe: {camel_case_to_snake_case(method)}"
            )

        self._subscribers[sub_id] = Subscription(
            service=service, id=sub_id, handler=handler
        )
        logger.debug(
            f"Subscribed to {service} {camel_case_to_snake_case(method)} (sub id: {sub_id})"
        )

        async def unsub():
            await self._unsubscribe(sub_id, timeout=timeout)

        return unsub

    def _handle_notification(self, data: Notification):
        logger.debug(f"Notification {data}")

        id = data.params["subscription"]
        sub = self._subscribers.get(id, None)
        if sub is None:
            logger.error(f"recv notification for invalid subid {id}")
            return
        else:
            sub.handler(data.params["result"])

    async def deactive(self, timeout: Optional[float] = TIMEOUT):
        """
        Demote the memory of the sandbox to lower level (e.g., swap).
        This can increase the density of sandboxes on the server.

        :param timeout: Specify the duration, in seconds to give the method to finish its execution before it times out (default is 60 seconds). If set to None, the method will continue to wait until it completes, regardless of time
        """
        if not self._is_open or self._sandbox is None:
            raise SandboxNotOpenException("Sandbox is not open")
        try:
            req = SandboxDeactivateRequest(sandboxID=self.id)
            _ = await self.orchestrator_client.Deactive(req, timeout=timeout)
        except grpc.RpcError as e:
            logger.error(f"failed to deactive a sandbox: {e}")
            await self._close()
            raise e
        except Exception as e:
            logger.error(f"Non Rpc Error while deactive: {e}")
            await self._close()
            raise e
        logger.info(f"Sandbox {self.id} deactivated")

    @staticmethod
    async def list(target_addr: str = BACKEND_ADDR) -> List[RunningSandbox]:
        """
        List all running sandboxes.

        :param api_key: API key to use for authentication.
        :param domain: Domain to use for the API.
        If not provided, the `E2B_API_KEY` environment variable will be used.
        """
        async with AsyncOrchestratorClient(
            f"{target_addr}:{ORCHESTRATOR_PORT}"
        ) as orchestrator_client:
            req = google_dot_protobuf_dot_empty__pb2.Empty()
            res: SandboxListResponse = await orchestrator_client.List(req)
            return [
                RunningSandbox(
                    sandbox_id=sbx.sandboxID,
                    template_id=sbx.templateID,
                    started_at=sbx.startTime.ToDatetime(),
                    metadata=dict(sbx.metadata),
                )
                for sbx in res.sandboxes
            ]

    @staticmethod
    async def kill(sandbox_id: str, target_addr: str = BACKEND_ADDR) -> None:
        """
        Kill the running sandbox specified by the sandbox ID.

        :param sandbox_id: ID of the sandbox to kill.
        :param api_key: API key to use for authentication.
        :param domain: Domain to use for the API.
        If not provided, the `E2B_API_KEY` environment variable will be used.
        """
        async with AsyncOrchestratorClient(
            f"{target_addr}:{ORCHESTRATOR_PORT}"
        ) as orchestrator_client:
            reqpc = SandboxDeleteRequest(sandboxID=sandbox_id)
            _ = await orchestrator_client.Delete(reqpc)

    async def snapshot(
        self, delete: bool = False, timeout: Optional[float] = TIMEOUT
    ) -> SandboxSnapshotResponse:
        """
        Take the snapshot of the running vm.

        :param delete: Whether delete the sandbox after generating snapshot, if set to True, the sandbox will be delete and close afterwards.
        :param timeout: Specify the duration, in seconds to give the method to finish its execution before it times out (default is 60 seconds). If set to None, the method will continue to wait until it completes, regardless of time
        """
        if not self._is_open or self._sandbox is None:
            raise SandboxNotOpenException("Sandbox is not open")
        try:
            req = SandboxSnapshotRequest(sandboxID=self.id, delete=delete)
            response: SandboxSnapshotResponse = await self.orchestrator_client.Snapshot(
                req, timeout=timeout
            )
        except grpc.RpcError as e:
            logger.error(f"failed to snapshot a sandbox: {e}")
            await self._close()
            raise e
        except Exception as e:
            logger.error(f"Non Rpc Error while snapshot: {e}")
            await self._close()
            raise e
        logger.info(f"Sandbox {self.id} snapshotted: {response.path}")
        if delete:
            await self.close()
        return response
