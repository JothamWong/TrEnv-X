from sandbox_sdk.code_interpreter import CodeInterpreter
from ..utils import asyncio_run


@asyncio_run
async def test_bash():
    async with await CodeInterpreter.create() as sandbox:
        result = await sandbox.notebook.exec_cell("!pwd")
        assert "".join(result.logs.stdout).strip() == "/home/user"
