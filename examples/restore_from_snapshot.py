"""Restore an instance from one of its snapshots, replacing its current data.

Usage: python examples/restore_from_snapshot.py INSTANCE_ID SNAPSHOT_ID
Needs AURA_CLIENT_ID and AURA_CLIENT_SECRET.

Run examples/list_snapshots.py first to find a snapshot ID.
"""

import sys

import aura_python_sdk as aura


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    instance_id, snapshot_id = sys.argv[1], sys.argv[2]

    answer = input(f"This replaces all data in {instance_id}. Type the instance ID to confirm: ")
    if answer.strip() != instance_id:
        print("not confirmed; nothing was changed")
        return 1

    try:
        with aura.AuraClient.from_env() as client:
            instance = client.snapshots.restore(instance_id, snapshot_id)
    except aura.AuraError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    print(f"Restore started: {instance.id} is {instance.status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
