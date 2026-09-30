"""Take an on-demand snapshot of an instance and show its details.

Usage: python examples/take_snapshot.py INSTANCE_ID
Needs AURA_CLIENT_ID and AURA_CLIENT_SECRET.
"""

import sys

import aura_python_sdk as aura


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    instance_id = sys.argv[1]
    try:
        with aura.AuraClient.from_env() as client:
            started = client.snapshots.create(instance_id)
            print(f"Snapshot started: {started.snapshot_id}")
            snapshot = client.snapshots.get(instance_id, started.snapshot_id)
    except aura.AuraError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    print(f"  instance: {snapshot.instance_id}")
    print(f"  status:   {snapshot.status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
