"""Create a free instance, wait until it is running, then delete it.

Usage: python examples/create_delete_instance.py
Needs AURA_CLIENT_ID, AURA_CLIENT_SECRET and AURA_TENANT_ID.

Only one free instance can exist per tenant, so the script stops if one already exists.
"""

import logging
import os
import sys

import aura_python_sdk as aura


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    tenant_id = os.environ.get("AURA_TENANT_ID", "")
    if not tenant_id:
        print("AURA_TENANT_ID must be set", file=sys.stderr)
        return 2

    config = aura.InstanceConfig(
        name="auraPythonSdkExample",
        tenant_id=tenant_id,
        cloud_provider=aura.CloudProvider.GCP,
        region="europe-west1",
        type=aura.InstanceType.FREE_DB,
        version="5",
        memory="1GB",
    )

    try:
        with aura.AuraClient.from_env() as client:
            for summary in client.instances.list(tenant_id=tenant_id):
                if client.instances.get(summary.id).type == aura.InstanceType.FREE_DB:
                    print(
                        f"{summary.name} ({summary.id}) already uses the free tier", file=sys.stderr
                    )
                    return 1

            created = client.instances.create(config)
            print(f"Created {created.name} ({created.id}) at {created.connection_url}")
            print(f"  username={created.username}; store the password now, it is shown only once")

            print("Waiting for it to be running (this usually takes a few minutes)...")
            client.instances.wait_for_status(created.id, timeout=10 * 60, interval=5)
            print(f"Instance {created.id} is running; deleting it")

            deleted = client.instances.delete(created.id)
            print(f"Instance {deleted.id} is {deleted.status}")
    except aura.AuraError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
