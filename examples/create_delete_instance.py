"""Create a free instance, wait until it is running, then delete it.

Usage: python examples/create_delete_instance.py
Needs AURA_CLIENT_ID, AURA_CLIENT_SECRET and AURA_TENANT_ID.

Only one free instance can exist per tenant, so the script stops if one already exists.
"""

import logging
import os
import sys
import time

import aura_python_sdk as aura

POLL_INTERVAL = 5.0
CREATE_TIMEOUT = 10 * 60.0


def wait_for_status(
    client: aura.AuraClient,
    instance_id: str,
    status: aura.InstanceStatus,
    timeout: float = CREATE_TIMEOUT,
) -> aura.Instance:
    """Poll until the instance reaches ``status``, or raise TimeoutError."""
    deadline = time.monotonic() + timeout
    poll = 1
    while True:
        try:
            instance = client.instances.get(instance_id)
        except aura.NotFoundError:
            # A brand-new instance can take a moment to appear in the API.
            instance = None
        if instance is not None and instance.status == status:
            return instance
        if time.monotonic() > deadline:
            raise TimeoutError(f"instance {instance_id} did not reach {status} in {timeout:.0f}s")
        current = instance.status if instance else "not visible yet"
        print(f"  status is {current} (poll {poll})")
        poll += 1
        time.sleep(POLL_INTERVAL)


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
            for summary in client.instances.list(tenant_id):
                if client.instances.get(summary.id).type == aura.InstanceType.FREE_DB:
                    print(
                        f"{summary.name} ({summary.id}) already uses the free tier", file=sys.stderr
                    )
                    return 1

            created = client.instances.create(config)
            print(f"Created {created.name} ({created.id}) at {created.connection_url}")
            print(f"  username={created.username}; store the password now, it is shown only once")

            wait_for_status(client, created.id, aura.InstanceStatus.RUNNING)
            print(f"Instance {created.id} is running; deleting it")

            deleted = client.instances.delete(created.id)
            print(f"Instance {deleted.id} is {deleted.status}")
    except (aura.AuraError, TimeoutError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
