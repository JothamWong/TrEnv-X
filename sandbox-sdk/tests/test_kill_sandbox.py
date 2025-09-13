from sandbox_sdk import Sandbox
from .utils import asyncio_run


@asyncio_run
async def test_kill_sandbox():
    s = await Sandbox.create()
    await Sandbox.kill(s.id)

    sandboxes = await Sandbox.list()
    assert s.id not in [sandbox.sandbox_id for sandbox in sandboxes]

    await s.close()
