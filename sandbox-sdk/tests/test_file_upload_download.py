import filecmp

from os import path
from sandbox_sdk import Sandbox
from .utils import asyncio_run


@asyncio_run
async def test_download():
    file_name = "video.webm"
    local_dir = "tests/assets"

    local_path = path.join(local_dir, file_name)

    sandbox = await Sandbox.create()

    # Upload the file first (it's uploaded to /home/user)
    with open(local_path, "rb") as f:
        uploaded_file_path = await sandbox.upload_file(file=f)

    # Download the file back and save it in the local filesystem
    file_content = await sandbox.download_file(uploaded_file_path)
    with open(path.join(local_dir, "video-downloaded.webm"), "wb") as f:
        f.write(file_content)

    # Compare the downloaded file with the original
    assert filecmp.cmp(local_path, path.join(local_dir, "video-downloaded.webm"))

    await sandbox.close()
