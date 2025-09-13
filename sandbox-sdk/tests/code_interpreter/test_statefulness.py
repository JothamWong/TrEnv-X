from sandbox_sdk.code_interpreter import CodeInterpreter
from ..utils import asyncio_run


@asyncio_run
async def test_stateful():
    async with await CodeInterpreter.create() as sandbox:
        await sandbox.notebook.exec_cell("x = 1")

        result = await sandbox.notebook.exec_cell("x+=1; x")
        assert result.text == "2"
