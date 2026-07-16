"""Merges alert and ICP data into one ranked priority list. Reads alerts.csv
and icp_scores.csv (both cover all 18 accounts). Writes priority_accounts.csv.

The composite score weights alert_level far above ICP fit: an account about
to hit a tier wall right now outranks a great-fit account with no urgency.
data_source (real/simulated) is carried through unchanged on every row.
"""
import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALERTS_CSV = PROJECT_ROOT / "alerts.csv"
ICP_CSV = PROJECT_ROOT / "icp_scores.csv"
OUT_CSV = PROJECT_ROOT / "priority_accounts.csv"

# alert_level dominates: the gap between tiers (50) is always larger than the
# max possible ICP fit contribution (3, since icp_scoring.py now scores 0-3
# stated criteria met rather than an invented 1-5 scale), so alert_level
# alone decides ranking except as a tiebreaker within the same alert_level.
ALERT_WEIGHT = {"at_cap": 100, "approaching": 50, "none": 0}


def load_csv(path):
    with open(path, newline="") as f:
        return {row["pod_id"]: row for row in csv.DictReader(f)}


def priority_reason(alert_level, tier, icp_fit_score, assigned_segment):
    if alert_level == "at_cap":
        return (
            f"At the {tier} tier cap right now — this is the forced-decision moment; "
            "reach out before they churn from frustration or self-serve upgrade unassisted."
        )
    if alert_level == "approaching":
        return f"Approaching the {tier} tier cap — a good window to get ahead of the upgrade conversation."
    if icp_fit_score >= 3:
        return f"No urgency yet, but a full ICP criteria match ({assigned_segment}) worth keeping warm."
    return "No urgency and only a partial ICP criteria match — low priority for outreach right now."


def main():
    alerts = load_csv(ALERTS_CSV)
    icp = load_csv(ICP_CSV)

    if not alerts:
        raise SystemExit(f"STOP: {ALERTS_CSV.name} is empty -- run tier_alerts.py first.")
    if not icp:
        raise SystemExit(f"STOP: {ICP_CSV.name} is empty -- run icp_scoring.py first.")

    missing_alerts = [pod_id for pod_id in icp if pod_id not in alerts]
    if missing_alerts:
        raise SystemExit(
            f"STOP: {len(missing_alerts)} account(s) in {ICP_CSV.name} have no matching row "
            f"in {ALERTS_CSV.name} (e.g. {missing_alerts[0]}) -- re-run tier_alerts.py and "
            "icp_scoring.py together so they cover the same accounts."
        )

    rows = []
    for pod_id, icp_row in icp.items():
        alert_row = alerts.get(pod_id, {})
        alert_level = icp_row["alert_level"]
        icp_fit_score = max(int(icp_row["segment1_score"]), int(icp_row["segment2_score"]))
        composite = ALERT_WEIGHT[alert_level] + icp_fit_score

        rows.append(
            {
                "pod_id": pod_id,
                "pod_name": icp_row["pod_name"],
                "data_source": icp_row["data_source"],
                "tier": icp_row["tier"],
                "alert_level": alert_level,
                "inbox_usage_pct": icp_row["inbox_usage_pct"],
                "email_usage_pct": icp_row["email_usage_pct"],
                "daily_sent": icp_row.get("daily_sent", ""),
                "daily_usage_pct": icp_row.get("daily_usage_pct", ""),
                "daily_alert_level": icp_row.get("daily_alert_level", ""),
                "assigned_segment": icp_row["assigned_segment"],
                "icp_fit_score": icp_fit_score,
                "composite_score": composite,
                "suggested_next_tier": alert_row.get("suggested_next_tier", ""),
                "suggested_action": alert_row.get("suggested_action", ""),
                "priority_reason": priority_reason(
                    alert_level, icp_row["tier"], icp_fit_score, icp_row["assigned_segment"]
                ),
            }
        )

    rows.sort(key=lambda r: r["composite_score"], reverse=True)

    fieldnames = [
        "pod_id",
        "pod_name",
        "data_source",
        "tier",
        "alert_level",
        "inbox_usage_pct",
        "email_usage_pct",
        "daily_sent",
        "daily_usage_pct",
        "daily_alert_level",
        "assigned_segment",
        "icp_fit_score",
        "composite_score",
        "suggested_next_tier",
        "suggested_action",
        "priority_reason",
    ]
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("=== Priority Accounts (ranked, alert urgency > ICP fit) ===")
    for r in rows:
        print(
            f"{r['composite_score']:>4}  [{r['alert_level']:>10}] {r['pod_name']:<18} "
            f"[{r['data_source']:<9}] fit={r['icp_fit_score']} ({r['assigned_segment']})"
        )
    print(f"\nWrote {OUT_CSV.name} ({len(rows)} accounts)")


if __name__ == "__main__":
    main()
