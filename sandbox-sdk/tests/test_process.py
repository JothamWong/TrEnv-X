import asyncio
from unittest.mock import MagicMock

from sandbox_sdk import Sandbox
from .utils import asyncio_run


@asyncio_run
async def test_process_expected_stdout():
    # TODO: Implement this once we fix envd stdout/stderr race condition
    pass


@asyncio_run
async def test_process_expected_stderr():
    # TODO: Implement this once we fix envd stdout/stderr race condition
    pass


@asyncio_run
async def test_process_on_stdout_stderr():
    sandbox = await Sandbox.create()

    stdout = []
    stderr = []

    proc = await sandbox.process.start(
        "pwd",
        on_stdout=lambda data: stdout.append(data),
        on_stderr=lambda data: stderr.append(data),
        cwd="/tmp",
    )

    output = await proc.wait()

    assert not output.error
    assert output.stdout == "/tmp"
    assert output.stderr == ""
    assert list(map(lambda message: message.line, stdout)) == ["/tmp"]
    assert stderr == []
    assert proc.exit_code == 0

    await sandbox.close()


@asyncio_run
async def test_process_on_exit():
    sandbox = await Sandbox.create()

    on_exit = MagicMock()

    proc = await sandbox.process.start(
        "pwd",
        on_exit=lambda exit_code: on_exit(exit_code),
    )

    await proc.wait()
    on_exit.assert_called_once()

    await sandbox.close()


@asyncio_run
async def test_process_send_stdin():
    sandbox = await Sandbox.create()

    proc = await sandbox.process.start(
        'read -r line; echo "$line"',
        cwd="/code",
    )
    await proc.send_stdin("ping\n")
    await proc.wait()

    assert proc.output.stdout == "ping"

    assert len(proc.output_messages) == 1
    message = proc.output_messages[0]
    assert message.line == "ping"
    assert not message.error

    await sandbox.close()


@asyncio_run
async def test_default_on_exit():
    on_exit = MagicMock()

    sandbox = await Sandbox.create(on_exit=lambda exit_code: on_exit(exit_code))
    proc = await sandbox.process.start(
        "pwd",
        on_exit=lambda: print("EXIT"),
    )
    await proc.wait()
    on_exit.assert_not_called()

    proc = await sandbox.process.start(
        "pwd",
    )
    await proc.wait()
    on_exit.assert_called_once()

    await sandbox.close()


@asyncio_run
async def test_process_default_on_stdout_stderr():
    on_stdout = MagicMock()
    on_stderr = MagicMock()

    sandbox = await Sandbox.create(
        on_stdout=lambda data: on_stdout(data),
        on_stderr=lambda data: on_stderr(data),
    )
    code = "python -c \"print('Hello world'); raise Exception('Error!')\""

    stdout = []
    stderr = []

    proc = await sandbox.process.start(
        code,
        on_stdout=lambda data: stdout.append(data),
        on_stderr=lambda data: stderr.append(data),
    )

    await proc.wait()
    # it depends on the template used, as start_cmd might send
    # output to journalctl
    # if define the start_cmd in the template, the on_stdout and on_stderr will be called.
    on_stdout.assert_not_called()
    on_stderr.assert_not_called()

    proc = await sandbox.process.start(code)
    await proc.wait()

    on_stdout.assert_called()
    on_stderr.assert_called()
    assert proc.exit_code == 1

    await sandbox.close()


@asyncio_run
async def test_process_start_and_wait():
    sandbox = await Sandbox.create()
    code = "python -c \"print('Hello world')\""

    output = await sandbox.process.start_and_wait(code)

    proc = await sandbox.process.start(code)
    await proc.wait()

    assert output.exit_code == 0

    await sandbox.close()
