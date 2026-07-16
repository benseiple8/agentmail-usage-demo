"""Pulls real per-pod usage from AgentMail's own Metrics API
(GET /v0/pods/{pod_id}/metrics/events and .../metrics/usage). Reads
state.json for pod IDs. Writes real_accounts_usage.csv. Every value in the
CSV comes straight from these API responses; nothing here is estimated.
"""
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from client import get

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_JSON = PROJECT_ROOT / "state.json"
OUT_CSV = PROJECT_ROOT / "real_accounts_usage.csv"


def sum_event_count(pod_id, event_type, start_iso, end_iso):
    resp = get(
        f"/v0/pods/{pod_id}/metrics/events",
        params={"event_types": [event_type], "start": start_iso, "end": end_iso},
    )
    buckets = resp.get(event_type, [])
    return sum(b["count"] for b in buckets)


def latest_usage_value(pod_id, usage_type, start_iso, end_iso):
    resp = get(
        f"/v0/pods/{pod_id}/metrics/usage",
        params={"usage_types": [usage_type], "start": start_iso, "end": end_iso},
    )
    points = resp.get(usage_type, [])
    return points[-1]["value"] if points else 0


def main():
    with open(STATE_JSON) as f:
        state = json.load(f)

    if not state.get("pods"):
        raise SystemExit(f"STOP: {STATE_JSON.name} has no pods -- run create_resources.py first.")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=1)
    # API requires strict ISO datetime ending in literal "Z" (no +00:00 offset).
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    start_iso, end_iso = start.strftime(fmt), end.strftime(fmt)

    rows = []
    for pod in state["pods"]:
        pod_id = pod["pod_id"]
        sent = sum_event_count(pod_id, "message.sent", start_iso, end_iso)
        received = sum_event_count(pod_id, "message.received", start_iso, end_iso)
        threads = latest_usage_value(pod_id, "thread_count", start_iso, end_iso)
        inboxes = latest_usage_value(pod_id, "inbox_count", start_iso, end_iso)

        row = {
            "pod_id": pod_id,
            "pod_name": pod["pod_name"],
            "inbox_count": inboxes,
            "messages_sent": sent,
            "messages_received": received,
            "thread_count": threads,
            "data_source": "real",
        }
        rows.append(row)
        print(row)

    fieldnames = [
        "pod_id",
        "pod_name",
        "inbox_count",
        "messages_sent",
        "messages_received",
        "thread_count",
        "data_source",
    ]
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {OUT_CSV.name}")


if __name__ == "__main__":
    main()
