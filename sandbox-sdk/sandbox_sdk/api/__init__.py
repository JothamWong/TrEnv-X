import grpc
from sandbox_sdk.api.orchestrator_pb2_grpc import SandboxStub
from sandbox_sdk.api.orchestrator_pb2 import *


class OrchestratorClient(SandboxStub):
    def __init__(self, url: str):
        channel = grpc.insecure_channel(url)
        self._channel = channel
        super().__init__(channel)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
    
    def close(self):
        self._channel.close()

class AsyncOrchestratorClient(SandboxStub):
    def __init__(self, url: str):
        channel = grpc.aio.insecure_channel(url)
        self._channel = channel
        super().__init__(channel)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def close(self):
        await self._channel.close()
