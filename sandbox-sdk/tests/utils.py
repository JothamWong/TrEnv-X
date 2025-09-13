import asyncio
import inspect


def asyncio_run(async_func):
    if not inspect.iscoroutinefunction(async_func):
        raise Exception(f"{async_func.__name__} is not async function")

    def wrapper(*args, **kwargs):
        return asyncio.run(async_func(*args, **kwargs))

    wrapper.__signature__ = inspect.signature(
        async_func
    )  # without this, fixtures are not injected

    return wrapper
