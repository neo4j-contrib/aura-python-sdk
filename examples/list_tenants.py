"""List every tenant and the instance configurations it supports.

Usage: python examples/list_tenants.py
Needs AURA_CLIENT_ID and AURA_CLIENT_SECRET.
"""

import sys

import aura_python_sdk as aura


def main() -> int:
    try:
        with aura.AuraClient.from_env() as client:
            for summary in client.tenants.list():
                tenant = client.tenants.get(summary.id)
                print(f"{tenant.name} ({tenant.id})")
                for config in tenant.instance_configurations:
                    print(
                        f"  - {config.type} {config.cloud_provider} {config.region} "
                        f"memory={config.memory} storage={config.storage} version={config.version}"
                    )
    except aura.AuraError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
