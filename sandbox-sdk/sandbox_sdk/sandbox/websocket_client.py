from __future__ import annotations
import asyncio

import logging

from typing import Optional

from websockets.client import connect, WebSocketClientProtocol
from websockets.typing import Data

logger = logging.getLogger(__name__)


class WebSocket:
    def __init__(
        self,
        url: str,
    ):
        self._ws: Optional[WebSocketClientProtocol] = None
        self.url = url

    def __aiter__(self):
        if not self._ws:
            raise Exception("No WebSocket connection")
        return self._ws.__aiter__()

    async def send(self, message: str):
        if not self._ws:
            raise Exception("No WebSocket connection")
        await self._ws.send(message)

    async def recv(self) -> Data:
        if not self._ws:
            raise Exception("No WebSocket connection")
        return await self._ws.recv()

    async def connect(self, retry: int = 3):
        logger.debug(f"WebSocket connecting to {self.url}")

        ws_logger = logger.getChild("websockets.client")
        ws_logger.setLevel(logging.ERROR)

        websocket_connector = connect(
            self.url,
            max_size=None,
            max_queue=None,
            logger=ws_logger,
            ping_timeout=None,
            close_timeout=5,
        )

        websocket_connector.BACKOFF_MIN = 1
        websocket_connector.BACKOFF_FACTOR = 1
        websocket_connector.BACKOFF_INITIAL = 0.2  # type: ignore

        tried = 0
        retry_sleep_time = [2, 5, 10]
        while True:
            try:
                self._ws = await websocket_connector
            except Exception as e:
                tried += 1
                logger.warning(f"connect websocket failed (try {tried} times): {e}")
                if tried > retry:
                    raise e
                await asyncio.sleep(retry_sleep_time[tried - 1])
            else:
                break

        logger.debug(f"WebSocket connected to {self.url}, totally tried {tried} times")

    async def close(self):
        if self._ws:
            await self._ws.close()
            logger.debug(f"websocket (url: {self.url}) closed")
