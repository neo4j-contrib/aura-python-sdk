"""Fetch every instance's details concurrently with AsyncAuraClient.

Usage: python examples/async_instance_details.py
Needs AURA_CLIENT_ID and AURA_CLIENT_SECRET.
"""

import asyncio
import sys

import aura_python_sdk as aura


async def main() -> int:
    try:
        async with aura.AsyncAuraClient.from_env() as client:
            summaries = await client.instances.list()
            # All the GET requests run concurrently and share one OAuth token.
            instances = await asyncio.gather(*(client.instances.get(s.id) for s in summaries))
    except aura.AuraError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    for instance in instances:
        print(f"- {instance.name} ({instance.id}): {instance.status}, {instance.type}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
