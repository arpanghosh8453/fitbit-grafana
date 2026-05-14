#!/usr/bin/env python3
"""
One-off migration: re-anchor existing "Sleep Summary" timestamps in InfluxDB.

For each row, the new timestamp is 12:00 UTC of the "sleep date" — the day the
user conceptually went to bed in their local timezone. If the original local
start time is before noon, the session belongs to the previous local day.

Sleep Levels stage rows are NOT migrated: they hold real stage timestamps used
for the hypnogram timeline.

Run inside the fitbit-fetch-data container so influxdb-python is available:

  docker compose run --rm \
    -e DRY_RUN=True -e LOCAL_TIMEZONE=Europe/Paris \
    -v "$PWD/migrate_sleep_anchor.py:/app/migrate_sleep_anchor.py" \
    --entrypoint python fitbit-fetch-data /app/migrate_sleep_anchor.py
"""
import os
import sys
from datetime import datetime, timedelta

import pytz
from influxdb import InfluxDBClient

INFLUXDB_HOST = os.environ.get("INFLUXDB_HOST", "influxdb")
INFLUXDB_PORT = int(os.environ.get("INFLUXDB_PORT", "8086"))
INFLUXDB_USERNAME = os.environ["INFLUXDB_USERNAME"]
INFLUXDB_PASSWORD = os.environ["INFLUXDB_PASSWORD"]
INFLUXDB_DATABASE = os.environ.get("INFLUXDB_DATABASE", "FitbitHealthStats")
LOCAL_TIMEZONE = pytz.timezone(os.environ.get("LOCAL_TIMEZONE", "Europe/Paris"))
DRY_RUN = os.environ.get("DRY_RUN", "False").strip().lower() in ("true", "1", "yes", "y")

INT_FIELDS = (
    "efficiency", "minutesAfterWakeup", "minutesAsleep", "minutesToFallAsleep",
    "minutesInBed", "minutesAwake", "minutesLight", "minutesREM", "minutesDeep",
)


def anchor(start_dt_utc, local_tz):
    local_dt = start_dt_utc.astimezone(local_tz)
    sleep_date = local_dt.date() - timedelta(days=1) if local_dt.hour < 12 else local_dt.date()
    return datetime(sleep_date.year, sleep_date.month, sleep_date.day, 12, 0, 0, tzinfo=pytz.utc)


def main():
    client = InfluxDBClient(
        host=INFLUXDB_HOST, port=INFLUXDB_PORT,
        username=INFLUXDB_USERNAME, password=INFLUXDB_PASSWORD,
        database=INFLUXDB_DATABASE,
    )
    rows = list(client.query('SELECT * FROM "Sleep Summary"', epoch="ns").get_points())
    print(f"Found {len(rows)} Sleep Summary rows")

    migrate = []
    unchanged = 0
    for r in rows:
        old_dt = datetime.fromtimestamp(int(r["time"]) / 1e9, tz=pytz.utc)
        new_dt = anchor(old_dt, LOCAL_TIMEZONE)
        if old_dt == new_dt:
            unchanged += 1
            continue
        migrate.append((r, old_dt, new_dt))

    # Detect collisions: multiple sleeps anchoring to the same sleep_date
    by_target = {}
    for r, old, new in migrate:
        by_target.setdefault(new.isoformat(), []).append(old.isoformat())
    collisions = {k: v for k, v in by_target.items() if len(v) > 1}

    print(f"  to migrate: {len(migrate)}")
    print(f"  unchanged : {unchanged}")
    print(f"  collisions: {len(collisions)} target dates with >1 source row")

    if collisions:
        print("  sample collisions (last write wins after migration):")
        for k, v in list(collisions.items())[:5]:
            print(f"    {k} <- {v}")

    if migrate:
        print("  sample migrations:")
        for r, old, new in migrate[:5]:
            print(f"    {old.isoformat()}  ->  {new.isoformat()}   eff={r.get('efficiency')}  asleep={r.get('minutesAsleep')}")

    if DRY_RUN:
        print("\nDRY_RUN=True — no writes. Re-run with DRY_RUN=False to apply.")
        return

    # Group migrations by target sleep_date so that collisions (multiple sessions
    # mapping to the same noon-UTC anchor) get sub-second offsets — preserves all
    # data and makes the longest sleep "win" for `last`/`lastNotNull` reducers.
    from collections import defaultdict
    groups = defaultdict(list)
    for r, old, new in migrate:
        groups[new.date()].append((r, old, new))

    points = []
    delete_ts_ns = []
    for sleep_date, items in groups.items():
        items.sort(key=lambda x: int(x[0].get("minutesAsleep") or 0))  # shortest first, longest last
        for offset_idx, (r, old, new) in enumerate(items):
            new_ts = new + timedelta(seconds=offset_idx)
            fields = {}
            for k, v in r.items():
                if k in ("time", "Device", "isMainSleep"):
                    continue
                if v is None:
                    continue
                if k in INT_FIELDS:
                    fields[k] = int(v)
                else:
                    fields[k] = v
            tags = {
                "Device": r.get("Device") or "Versa4",
                "isMainSleep": str(r.get("isMainSleep", "True")),
            }
            points.append({
                "measurement": "Sleep Summary",
                "time": new_ts.isoformat(),
                "tags": tags,
                "fields": fields,
            })
            delete_ts_ns.append(int(old.timestamp() * 1e9))

    print(f"\nWriting {len(points)} new points...")
    # Batch writes
    BATCH = 500
    for i in range(0, len(points), BATCH):
        client.write_points(points[i:i + BATCH], time_precision="n")
    print("Written.")

    print(f"Deleting {len(delete_ts_ns)} old points...")
    # Group deletes by time to avoid pounding the API
    for i, ts_ns in enumerate(delete_ts_ns):
        client.query(f'DELETE FROM "Sleep Summary" WHERE time = {ts_ns}')
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(delete_ts_ns)} deleted")
    print("Deleted.")

    final = list(client.query('SELECT COUNT(efficiency) FROM "Sleep Summary"').get_points())
    print(f"Final Sleep Summary row count: {final[0]['count'] if final else 'unknown'}")


if __name__ == "__main__":
    try:
        main()
    except KeyError as e:
        sys.exit(f"Missing env var: {e}")
