from __future__ import annotations

import json
import logging

import asyncio
from asyncio import Future

from typing import Any, Callable, Dict, Iterator, List, Union, Optional
from jsonrpcclient import Error, Ok, request_json
from jsonrpcclient.id_generators import decimal as decimal_id_generator
from jsonrpcclient.responses import Response
from pydantic import BaseModel, PrivateAttr, ConfigDict
from websockets.typing import Data

from sandbox_sdk.constants import TIMEOUT
from sandbox_sdk.sandbox.exception import (
    RpcException,
    TimeoutException,
    SandboxException,
)
from sandbox_sdk.sandbox.websocket_client import WebSocket

logger = logging.getLogger(__name__)


class Notification(BaseModel):
    """Nofification."""

    method: str
    params: Dict


Message = Union[Response, Notification]


def to_response_or_notification(response: Dict[str, Any]) -> Message:
    """Create a Response namedtuple from a dict."""
    if "error" in response:
        return Error(
            response["error"]["code"],
            response["error"]["message"],
            response["error"].get("data"),
            response["id"],
        )
    elif "result" in response and "id" in response:
        return Ok(response["result"], response["id"])

    elif "params" in response:
        return Notification(method=response["method"], params=response["params"])

    raise ValueError("Invalid response", response)


class SandboxRpc(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    url: str
    on_message: Callable[[Notification], None]

    _id_generator: Iterator[int] = PrivateAttr(default_factory=decimal_id_generator)
    _waiting_for_replies: Dict[int, Future] = PrivateAttr(default_factory=dict)
    _websocket: Optional[WebSocket] = None
    _bg_tasks: List[asyncio.Task] = []

    async def process_messages(self):
        if not self._websocket:
            raise SandboxException(f"WebSocket has not been started")
        async for msg in self._websocket:
            logger.debug(f"WebSocket received message: {msg[:1000]}".strip())
            self._handle_recv_message(msg)

    async def connect(self, timeout: Optional[float] = TIMEOUT):
        try:
            await asyncio.wait_for(self._connect(), timeout)
        except asyncio.TimeoutError as e:
            raise TimeoutException(f"sandbox rpc connect timeout: {e}") from e

    async def _connect(self):
        self._websocket = WebSocket(self.url)
        try:
            await self._websocket.connect()
        except Exception as e:
            raise SandboxException(f"WebSocket failed to start: {e}") from e
        # spawn a task in the background to handle the received messages
        t = asyncio.create_task(
            self.process_messages(), name="sandbox rpc process message"
        )
        self._bg_tasks.append(t)

    async def _send_rpc(self, method: str, params: List[Any]) -> Any:
        """Send rpc through websocket:
        1. send the request
        2. wait until the response has arrived
        """
        if not self._websocket:
            raise SandboxException(f"WebSocket has not been started")
        id = next(self._id_generator)
        request = request_json(method, params, id)
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._waiting_for_replies[id] = fut
        try:
            await self._websocket.send(request)
            reply = await fut
        except Exception as e:
            logger.error(f"WebSocket received error while waiting for: {request} {e}")
            raise e
        finally:
            del self._waiting_for_replies[id]
        return reply

    async def send_rpc(self, method: str, params: List[Any], timeout: Optional[float]) -> Any:
        try:
            reply = await asyncio.wait_for(self._send_rpc(method, params), timeout)
        except asyncio.TimeoutError as e:
            logger.error(f"WebSocket timed out while send rpc: {method} {e}")
            raise TimeoutException(
                f"WebSocket timed out while send rpc: {method} {e}"
            ) from e
        return reply

    def _handle_recv_message(self, data: Data):
        logger.debug(f"Processing received message: {data[:1000]}".strip())

        message = to_response_or_notification(json.loads(data))

        logger.debug(
            f"Current waiting handlers: {list(self._waiting_for_replies.keys())}"
        )
        if isinstance(message, Ok):
            if (
                message.id in self._waiting_for_replies
                and self._waiting_for_replies[message.id]
            ):
                self._waiting_for_replies[message.id].set_result(message.result)
                return
        elif isinstance(message, Error):
            if (
                message.id in self._waiting_for_replies
                and self._waiting_for_replies[message.id]
            ):
                self._waiting_for_replies[message.id].set_exception(
                    RpcException(
                        code=message.code,
                        message=message.message,
                        id=message.id,
                        data=message.data,
                    )
                )
                return
        elif isinstance(message, Notification):
            # TODO(huang-jl): on_message might trigger exception
            # which might in turn influence the process_message coroutine
            try:
                self.on_message(message)
            except BaseException:
                logger.exception(f"error when handle notification of method {message.method}")

    async def close(self):
        for id in self._waiting_for_replies:
            fut = self._waiting_for_replies[id]
            if not fut.done():
                fut.cancel()
        for t in self._bg_tasks:
            t.cancel()
        if self._websocket:
            await self._websocket.close()
