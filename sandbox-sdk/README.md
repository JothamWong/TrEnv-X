# Sandbox SDK

This is a Python SDK for TrEnv-X, which can be used to create secure sandboxes and interact with it.

The implementation is partialy ported from [e2b](https://github.com/e2b-dev/E2B/tree/main/packages/python-sdk), which is the SOTA of the open source sandbox project. With addtional improvement by using async/coroutine, it becomes more efficient.


## Example

Do not forget to call `close`:

```python
from sandbox_sdk import Sandbox

sandbox = await Sandbox.create(cwd="/code/app")

proc = await sandbox.process.start("pwd")
output = await proc.wait()
assert output.stdout == "/code/app"
await sandbox.close()
```

We also support `with` statement:

```python
from sandbox_sdk.code_interpreter import CodeInterpreter

async with await CodeInterpreter.create() as sandbox:
    await sandbox.notebook.exec_cell("x = 1")

    result = await sandbox.notebook.exec_cell("x+=1; x")
    assert result.text == "2"
```


## Backend

Note that this SDK should not be used directly, it has to be used after depolyment of [TrEnv-X backend](..).

## Claude-code

This package add support for a special sandbox template that running claude code. It will start a vscode server and already install claude code.

```bash
# After install the sandbox_sdk:
# Set the SANDBOX_BACKEND_ADDR to your TrEnv-X backend's ip
# Set the ANTHROPIC_API_KEY
# If you want to use KIMI, then set --kimi. By default, use anthropic.
SANDBOX_BACKEND_ADDR=127.0.0.1 claude-coder --kimi --api-key $ANTHROPIC_API_KEY
```
