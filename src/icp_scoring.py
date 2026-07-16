"""Scores every account (3 real + 15 simulated) against 2 ICP segments using
3 stated, computable criteria each. Reads real_accounts_usage.csv,
simulated_accounts.csv, and alerts.csv. Writes icp_scores.csv.

No invented company names or backstories: each score is the count of stated
criteria an account's real numbers satisfy, and every reason string shows
the actual number and threshold involved. Accounts are labeled plainly
("Real Account 1", "Simulated Account 7") rather than by persona.
pod_id/pod_name are still carried through as identifiers for joining against
the rest of the pipeline, not as company profiles.

Segment 1 is modeled on Browser Use and Composio (agent-infra / dev-tool
builders). Segment 2 is modeled on eve.legal and CarEdge (vertical AI with
email-heavy workflows). The criteria below are informed by those companies,
not derived from their actual data.

Thresholds for the two ratio-based checks (messages/inbox, messages/thread)
are the median of that ratio across all 18 accounts in the current run,
computed fresh each time, not fixed constants.
"""
import csv
import statistics
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALERTS_CSV = PROJECT_ROOT / "alerts.csv"
REAL_CSV = PROJECT_ROOT / "real_accounts_usage.csv"
SIM_CSV = PROJECT_ROOT / "simulated_accounts.csv"
OUT_CSV = PROJECT_ROOT / "icp_scores.csv"

SEGMENT_1 = "Agent infra / dev-tool builder"
SEGMENT_2 = "Vertical AI, email-heavy workflow"


def load_accounts():
    accounts = []
    for path in (REAL_CSV, SIM_CSV):
        with open(path, newline="") as f:
            accounts.extend(csv.DictReader(f))
    return accounts


def load_alerts():
    with open(ALERTS_CSV, newline="") as f:
        return {row["pod_id"]: row for row in csv.DictReader(f)}


def compute_ratios(acct):
    inbox = int(acct["inbox_count"])
    sent = int(acct["messages_sent"])
    recv = int(acct["messages_received"])
    threads = int(acct["thread_count"])
    total = sent + recv
    return {
        "inbox": inbox,
        "sent": sent,
        "recv": recv,
        "threads": threads,
        # Guard against division by zero: an inbox_count of 0 shouldn't happen
        # in practice (every account has at least 1 inbox), and thread_count
        # is 0 for an account that has sent/received nothing yet -- both fall
        # back to a ratio of 0.0 rather than crashing.
        "per_inbox": total / inbox if inbox else 0.0,
        "per_thread": total / threads if threads else 0.0,
    }


def score_segment_1(r, median_inbox, median_thread):
    checks = [
        (
            r["per_inbox"] >= median_inbox,
            f"messages/inbox = {r['per_inbox']:.1f} {'>=' if r['per_inbox'] >= median_inbox else '<'} "
            f"dataset median {median_inbox:.1f} (high per-inbox throughput = API-style dev-tool pattern)",
        ),
        (
            r["per_thread"] <= median_thread,
            f"messages/thread = {r['per_thread']:.2f} {'<=' if r['per_thread'] <= median_thread else '>'} "
            f"dataset median {median_thread:.2f} (one-shot/notification-style traffic, not sustained conversations)",
        ),
        (
            r["sent"] >= r["recv"],
            f"messages_sent {r['sent']} {'>=' if r['sent'] >= r['recv'] else '<'} messages_received {r['recv']} "
            f"(outbound/notification-driven, not inbound-driven)",
        ),
    ]
    return checks


def score_segment_2(r, median_inbox, median_thread):
    checks = [
        (
            r["per_thread"] > median_thread,
            f"messages/thread = {r['per_thread']:.2f} {'>' if r['per_thread'] > median_thread else '<='} "
            f"dataset median {median_thread:.2f} (sustained multi-turn conversations, e.g. case/dealer correspondence)",
        ),
        (
            r["recv"] >= r["sent"],
            f"messages_received {r['recv']} {'>=' if r['recv'] >= r['sent'] else '<'} messages_sent {r['sent']} "
            f"(inbound client/customer correspondence drives volume)",
        ),
        (
            r["inbox"] >= 4,
            f"inbox_count {r['inbox']} {'>=' if r['inbox'] >= 4 else '<'} 4 "
            f"(multi-mailbox, staff/case-handler-style operation)",
        ),
    ]
    return checks


def format_reason(checks):
    met = sum(1 for passed, _ in checks if passed)
    lines = [f"{'[met]' if passed else '[not met]'} {text}" for passed, text in checks]
    return f"{met}/{len(checks)} criteria met -- " + "; ".join(lines)


def main():
    accounts = load_accounts()
    alerts = load_alerts()

    if not accounts:
        raise SystemExit(
            f"STOP: no accounts loaded from {REAL_CSV.name} / {SIM_CSV.name} -- "
            "both appear empty. Run pull_metrics.py and simulated_accounts.py first."
        )
    if not alerts:
        raise SystemExit(f"STOP: {ALERTS_CSV.name} is empty -- run tier_alerts.py first.")

    missing_alerts = [a["pod_id"] for a in accounts if a["pod_id"] not in alerts]
    if missing_alerts:
        raise SystemExit(
            f"STOP: {len(missing_alerts)} account(s) have no matching row in {ALERTS_CSV.name} "
            f"(e.g. {missing_alerts[0]}) -- re-run tier_alerts.py so it covers the same accounts."
        )

    ratios = {acct["pod_id"]: compute_ratios(acct) for acct in accounts}
    median_inbox = statistics.median(r["per_inbox"] for r in ratios.values())
    median_thread = statistics.median(r["per_thread"] for r in ratios.values())

    real_counter = 0
    sim_counter = 0
    rows = []
    for acct in accounts:
        pod_id = acct["pod_id"]
        pod_name = acct["pod_name"]
        data_source = acct["data_source"]
        r = ratios[pod_id]
        alert = alerts.get(pod_id, {})

        if data_source == "real":
            real_counter += 1
            label_prefix = f"Real Account {real_counter}"
        else:
            sim_counter += 1
            label_prefix = f"Simulated Account {sim_counter}"

        s1_checks = score_segment_1(r, median_inbox, median_thread)
        s2_checks = score_segment_2(r, median_inbox, median_thread)
        s1_score = sum(1 for passed, _ in s1_checks if passed)
        s2_score = sum(1 for passed, _ in s2_checks if passed)

        if s1_score > s2_score:
            best_segment = SEGMENT_1
        elif s2_score > s1_score:
            best_segment = SEGMENT_2
        else:
            best_segment = "Mixed / inconclusive"

        rows.append(
            {
                "pod_id": pod_id,
                "pod_name": pod_name,
                "data_source": data_source,
                "tier": alert.get("tier", ""),
                "inbox_usage_pct": alert.get("inbox_usage_pct", ""),
                "email_usage_pct": alert.get("email_usage_pct", ""),
                "alert_level": alert.get("alert_level", ""),
                "profile_label": f"{label_prefix} -- {best_segment} profile",
                "assigned_segment": best_segment,
                "segment1_score": s1_score,
                "segment1_reason": format_reason(s1_checks),
                "segment2_score": s2_score,
                "segment2_reason": format_reason(s2_checks),
            }
        )

    rows.sort(key=lambda row: max(row["segment1_score"], row["segment2_score"]), reverse=True)

    fieldnames = [
        "pod_id",
        "pod_name",
        "data_source",
        "tier",
        "inbox_usage_pct",
        "email_usage_pct",
        "alert_level",
        "profile_label",
        "assigned_segment",
        "segment1_score",
        "segment1_reason",
        "segment2_score",
        "segment2_reason",
    ]
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"=== ICP Segment Scores (median msg/inbox={median_inbox:.1f}, median msg/thread={median_thread:.2f}) ===")
    for row in rows:
        print(
            f"{row['profile_label']:<45} [{row['data_source']:<9}] "
            f"seg1={row['segment1_score']}/3 seg2={row['segment2_score']}/3 alert={row['alert_level']}"
        )
    print(f"\nWrote {OUT_CSV.name} ({len(rows)} accounts)")


if __name__ == "__main__":
    main()
