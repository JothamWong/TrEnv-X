from sandbox_sdk import Sandbox
from .utils import asyncio_run


@asyncio_run
async def test_list_running_sandboxes():
    sandboxes = []
    for i in range(3):
        sandboxes.append(await Sandbox.create(metadata={"n": f"py{i}"}))

    running_sandboxes = list(
        filter(
            lambda s: s.metadata and s.metadata.get("n", "").startswith("py"),
            await Sandbox.list(),
        )
    )
    assert len(running_sandboxes) == 3
    assert set(map(lambda x: x.metadata["n"], running_sandboxes)) == {
        "py0",
        "py1",
        "py2",
    }

    for sandbox in sandboxes:
        await sandbox.close()
