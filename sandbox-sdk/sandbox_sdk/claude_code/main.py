import argparse
import logging
import asyncio
# from sandbox_sdk.cluade_code import ClaudeCoder
from . import ClaudeCoder, SANDBOX_PORT


async def run():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Run the Claude Code Sandbox.")
    parser.add_argument("--template", type=str, help="Sandbox template to use")
    parser.add_argument("--kimi", action="store_true", help="Use kimi api")
    parser.add_argument("--api-key", type=str, help="API key")
    args = parser.parse_args()

    envs = {}

    if args.kimi:
        envs["ANTHROPIC_BASE_URL"] = "https://api.moonshot.cn/anthropic/"
    if args.api_key:
        envs["ANTHROPIC_API_KEY"] = args.api_key
    coder = await ClaudeCoder.create(template=args.template, env_vars=envs)
    logging.info(f"ClaudeCoder with template: {coder.template} started at {coder.get_ide_url()}")
    await coder.close()

def main():
    asyncio.run(run())

