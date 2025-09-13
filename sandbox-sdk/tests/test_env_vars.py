from sandbox_sdk import Sandbox
from .utils import asyncio_run


@asyncio_run
async def test_env_vars():
    sandbox = await Sandbox.create()

    process = await sandbox.process.start("echo $FOO", env_vars={"FOO": "BAR"})
    await process.wait()
    output = process.stdout
    assert output == "BAR"

    await sandbox.close()


@asyncio_run
async def test_profile_env_vars():
    sandbox = await Sandbox.create()

    await sandbox.filesystem.write("/home/user/.profile", "export FOO=BAR")
    process = await sandbox.process.start("echo $FOO")
    await process.wait()
    output = process.stdout
    assert output == "BAR"

    await sandbox.close()


@asyncio_run
async def test_default_env_vars():
    sandbox = await Sandbox.create(env_vars={"FOO": "BAR"})
    process = await sandbox.process.start("echo $FOO")
    await process.wait()
    output = process.stdout
    assert output == "BAR"

    await sandbox.close()


@asyncio_run
async def test_overriding_env_vars():
    sandbox = await Sandbox.create(env_vars={"FOO": "BAR"})

    process = await sandbox.process.start("echo $FOO", env_vars={"FOO": "QUX"})
    await process.wait()
    output = process.stdout
    assert output == "QUX"

    await sandbox.close()
