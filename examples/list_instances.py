"""List every instance the credentials can access.

Usage: python examples/list_instances.py [TENANT_ID]
Needs AURA_CLIENT_ID and AURA_CLIENT_SECRET.
"""

import sys

import aura_python_sdk as aura


def main() -> int:
    tenant_id = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        with aura.AuraClient.from_env() as client:
            instances = client.instances.list(tenant_id)
    except aura.AuraError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    print(f"{len(instances)} instance(s)")
    for instance in instances:
        created = instance.created_at.isoformat() if instance.created_at else "unknown"
        print(f"- {instance.name}: {instance.id} {instance.cloud_provider} created {created}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
