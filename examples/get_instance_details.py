"""Show the details of one instance.

Usage: python examples/get_instance_details.py INSTANCE_ID
Needs AURA_CLIENT_ID and AURA_CLIENT_SECRET.
"""

import sys

import aura_python_sdk as aura


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        with aura.AuraClient.from_env() as client:
            instance = client.instances.get(sys.argv[1])
    except aura.NotFoundError:
        print(f"instance {sys.argv[1]} not found", file=sys.stderr)
        return 1
    except aura.AuraError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    print(f"Name:           {instance.name}")
    print(f"Id:             {instance.id}")
    print(f"Status:         {instance.status}")
    print(f"Cloud provider: {instance.cloud_provider} ({instance.region})")
    print(f"Tier:           {instance.type}")
    print(f"Memory:         {instance.memory or 'n/a'}")
    print(f"Storage:        {instance.storage or 'n/a'}")
    print(f"Connection URL: {instance.connection_url or 'n/a'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
