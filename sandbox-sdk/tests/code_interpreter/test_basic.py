from sandbox_sdk.code_interpreter import CodeInterpreter
from ..utils import asyncio_run



@asyncio_run
async def test_basic():
    async with await CodeInterpreter.create() as sandbox:
        result = await sandbox.notebook.exec_cell("x =1; x")
        assert result.text == "1"
