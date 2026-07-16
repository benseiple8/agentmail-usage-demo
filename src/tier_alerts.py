"""Flags accounts approaching or at their AgentMail tier limits. Reads
real_accounts_usage.csv (real, all Free tier) and simulated_accounts.csv
(synthetic, spans all three tiers). Writes alerts.csv, covering all 18
accounts.

Inbox count and email volume are scored differently. Inbox count is a
one-time provisioning choice, not a trend, so it's a binary at-cap /
not-at-cap flag with no "approaching" state. Email volume is a running
monthly total that can actually trend toward a cap, so it keeps graduated
approaching (70%) / at_cap (100%) thresholds.
"""
import csv
from pathlib import Path

# AgentMail published pricing tiers (source: https://agentmail.to/pricing,
# retrieved 2026-07-15). Hardcoded because these are marketing/billing figures,
# not exposed by any AgentMail API endpoint.
TIERS = {
    "Free": {"inbox_limit": 3, "email_limit": 3000},
    "Developer": {"inbox_limit": 10, "email_limit": 10000},
    "Startup": {"inbox_limit": 150, "email_limit": 150000},
}
TIER_ORDER = ["Free", "Developer", "Startup"]

EMAIL_APPROACHING_PCT = 70
EMAIL_AT_CAP_PCT = 100
SEVERITY_ORDER = {"at_cap": 0, "approaching": 1, "none": 2}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REAL_CSV = PROJECT_ROOT / "real_accounts_usage.csv"
SIM_CSV = PROJECT_ROOT / "simulated_accounts.csv"
CSV_OUT = PROJECT_ROOT / "alerts.csv"


def next_tier(tier):
    idx = TIER_ORDER.index(tier)
    return TIER_ORDER[idx + 1] if idx + 1 < len(TIER_ORDER) else None


def classify(inbox_at_cap, email_pct):
    if inbox_at_cap or email_pct >= EMAIL_AT_CAP_PCT:
        return "at_cap"
    if email_pct >= EMAIL_APPROACHING_PCT:
        return "approaching"
    return "none"


def suggest_action(tier, alert_level, inbox_at_cap, email_pct):
    upgrade = next_tier(tier)
    drivers = []
    if inbox_at_cap:
        drivers.append("inbox count")
    if email_pct >= EMAIL_APPROACHING_PCT:
        drivers.append("email volume")
    driver_text = " and ".join(drivers) if drivers else "usage"

    if alert_level == "none":
        return f"Comfortably within {tier} tier limits; no action needed."
    if upgrade is None:
        return (
            f"Already on the highest published AgentMail tier ({tier}) and "
            f"{driver_text} is high; contact AgentMail for custom/enterprise limits."
        )
    if alert_level == "at_cap":
        return f"At or over the {tier} tier {driver_text} limit; upgrade to {upgrade} now to avoid service interruption."
    return f"Approaching the {tier} tier {driver_text} limit; consider upgrading to {upgrade} soon."


def load_accounts():
    accounts = []
    with open(REAL_CSV, newline="") as f:
        for row in csv.DictReader(f):
            row = dict(row)
            row["tier"] = "Free"  # all real demo accounts are on Free tier
            accounts.append(row)
    if SIM_CSV.exists():
        with open(SIM_CSV, newline="") as f:
            accounts.extend(csv.DictReader(f))
    return accounts


def main():
    accounts = load_accounts()

    if not accounts:
        raise SystemExit(
            f"STOP: no accounts loaded from {REAL_CSV.name} / {SIM_CSV.name} -- "
            "both appear empty or missing. Run pull_metrics.py and simulated_accounts.py first."
        )

    results = []
    for row in accounts:
        tier = row["tier"]
        caps = TIERS[tier]

        inbox_count = int(row["inbox_count"])
        emails_used = int(row["messages_sent"]) + int(row["messages_received"])

        # No zero-guard needed here: both denominators come from the hardcoded
        # TIERS config above, never from per-account data, so they're always
        # one of 3/10/150 or 3000/10000/150000 -- never zero.
        inbox_pct = round(inbox_count / caps["inbox_limit"] * 100, 1)
        inbox_at_cap = inbox_count >= caps["inbox_limit"]
        email_pct = round(emails_used / caps["email_limit"] * 100, 1)

        alert_level = classify(inbox_at_cap, email_pct)
        upgrade = next_tier(tier)
        suggested_next_tier = tier if (alert_level == "none" or upgrade is None) else upgrade
        action = suggest_action(tier, alert_level, inbox_at_cap, email_pct)

        results.append(
            {
                "pod_id": row["pod_id"],
                "pod_name": row.get("pod_name", ""),
                "tier": tier,
                "inbox_usage_pct": inbox_pct,
                "inbox_at_cap": inbox_at_cap,
                "email_usage_pct": email_pct,
                "alert_level": alert_level,
                "suggested_next_tier": suggested_next_tier,
                "suggested_action": action,
                "data_source": row.get("data_source", ""),
                "_email_pct": email_pct,
            }
        )

    # sort by severity, then by email_pct (the one graduated/trend-bearing metric) within a tier
    results.sort(key=lambda r: (SEVERITY_ORDER[r["alert_level"]], -r["_email_pct"]))

    fieldnames = [
        "pod_id",
        "pod_name",
        "tier",
        "inbox_usage_pct",
        "inbox_at_cap",
        "email_usage_pct",
        "alert_level",
        "suggested_next_tier",
        "suggested_action",
        "data_source",
    ]
    with open(CSV_OUT, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({k: r[k] for k in fieldnames})

    print("=== Tier Usage Alerts ===")
    for r in results:
        print(
            f"[{r['alert_level'].upper():>10}] {r['pod_name'] or r['pod_id']:<18} "
            f"[{r['data_source']:<9}] tier={r['tier']:<9} inbox={r['inbox_usage_pct']:>5.1f}%"
            f"{'(AT CAP)' if r['inbox_at_cap'] else '':<9} email={r['email_usage_pct']:>5.1f}% "
            f"-> {r['suggested_action']}"
        )
    print(f"\nWrote {CSV_OUT.name} ({len(results)} accounts)")


if __name__ == "__main__":
    main()
