import pytest
from sandbox_sdk import CurrentWorkingDirectoryDoesntExistException, Sandbox
from .utils import asyncio_run


@asyncio_run
async def test_process_cwd():
    sandbox = await Sandbox.create(cwd="/code/app")

    proc = await sandbox.process.start("pwd")
    output = await proc.wait()
    assert output.stdout == "/code/app"
    await sandbox.close()


@asyncio_run
async def test_filesystem_cwd():
    sandbox = await Sandbox.create(cwd="/code/app")

    await sandbox.filesystem.write("hello.txt", "Hello VM!")
    proc = await sandbox.process.start("cat /code/app/hello.txt")
    output = await proc.wait()
    assert output.stdout == "Hello VM!"

    await sandbox.close()


@asyncio_run
async def test_change_cwd():
    sandbox = await Sandbox.create(cwd="/code/app")
    # change dir to /home/user
    sandbox.cwd = "/home/user"

    # process respects cwd
    proc = await sandbox.process.start("pwd")
    output = await proc.wait()
    assert output.stdout == "/home/user"

    # filesystem respects cwd
    await sandbox.filesystem.write("hello.txt", "Hello VM!")
    proc = await sandbox.process.start("cat /home/user/hello.txt")
    output = await proc.wait()
    assert output.stdout == "Hello VM!"

    await sandbox.close()


@asyncio_run
async def test_initial_cwd_with_tilde():
    sandbox = await Sandbox.create(cwd="~/code/")

    proc = await sandbox.process.start("pwd")
    output = await proc.wait()
    assert output.stdout == "/home/user/code"

    await sandbox.close()


@asyncio_run
async def test_relative_paths():
    sandbox = await Sandbox.create(cwd="/home/user")

    await sandbox.filesystem.make_dir("./code")
    await sandbox.filesystem.write("./code/hello.txt", "Hello Vasek!")
    proc = await sandbox.process.start("cat /home/user/code/hello.txt")
    output = await proc.wait()
    assert output.stdout == "Hello Vasek!"

    await sandbox.filesystem.write("../../hello.txt", "Hello Tom!")
    proc = await sandbox.process.start("cat /hello.txt")
    output = await proc.wait()
    assert output.stdout == "Hello Tom!"

    await sandbox.close()


@asyncio_run
async def test_warnings():
    sandbox = await Sandbox.create()

    with pytest.warns(Warning):
        await sandbox.filesystem.write("./hello.txt", "Hello Vasek!")

    with pytest.warns(Warning):
        await sandbox.filesystem.write("../hello.txt", "Hello Vasek!")

    with pytest.warns(Warning):
        await sandbox.filesystem.write("~/hello.txt", "Hello Vasek!")

    await sandbox.close()


@asyncio_run
async def test_doesnt_exists():
    sandbox = await Sandbox.create()

    with pytest.raises(CurrentWorkingDirectoryDoesntExistException):
        await sandbox.process.start("ls", cwd="/this/doesnt/exist")

    await sandbox.close()
