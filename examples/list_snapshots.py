"""List an instance's snapshots for a day (default: today).

Usage: python examples/list_snapshots.py INSTANCE_ID [YYYY-MM-DD]
Needs AURA_CLIENT_ID and AURA_CLIENT_SECRET.
"""

import datetime
import sys

import aura_python_sdk as aura


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print(__doc__, file=sys.stderr)
        return 2
    instance_id = sys.argv[1]
    try:
        day = datetime.date.fromisoformat(sys.argv[2]) if len(sys.argv) == 3 else None
    except ValueError:
        print("the date must be in the format YYYY-MM-DD", file=sys.stderr)
        return 2

    try:
        with aura.AuraClient.from_env() as client:
            snapshots = client.snapshots.list(instance_id, day)
    except aura.AuraError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    for snapshot in snapshots:
        taken = snapshot.timestamp.isoformat() if snapshot.timestamp else "unknown"
        print(
            f"- {snapshot.snapshot_id} {snapshot.status} {snapshot.profile} {taken} "
            f"exportable={snapshot.exportable}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
