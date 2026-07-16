"""Flags accounts approaching or at their AgentMail tier limits. Reads
real_accounts_usage.csv (real, all Free tier) and simulated_accounts.csv
(synthetic, spans all three tiers). Writes alerts.csv, covering all 18
accounts.

Three usage signals are scored, not two, because they behave differently:

- Inbox count is a one-time provisioning choice, not a trend, so it's a
  binary at-cap / not-at-cap flag with no "approaching" state.
- Monthly email volume is a running total that can trend toward a cap, so
  it keeps graduated approaching (70%) / at_cap (100%) thresholds.
- Daily send volume is a second, independent running total against
  AgentMail's Free-tier-only 100/day send cap (see TIERS below), scored with
  the same 70%/100% thresholds. An account can be fine on the month and
  still blocked today, or vice versa -- the two are not the same number.

alert_level (the column combine.py ranks on) is whichever of the monthly
combination (inbox + email) and the daily figure is more severe, since
either one blocks the account from sending.
"""
import csv
from pathlib import Path

# AgentMail published pricing tiers (source: https://agentmail.to/pricing,
# retrieved 2026-07-15). Hardcoded because these are marketing/billing figures,
# not exposed by any AgentMail API endpoint.
#
# daily_send_limit: AgentMail's Free tier caps sending at 100 emails/day,
# published on AgentMail's pricing and rate-limits pages. This cap is
# removed entirely on Developer and above (None here means "not applicable").
TIERS = {
    "Free": {"inbox_limit": 3, "email_limit": 3000, "daily_send_limit": 100},
    "Developer": {"inbox_limit": 10, "email_limit": 10000, "daily_send_limit": None},
    "Startup": {"inbox_limit": 150, "email_limit": 150000, "daily_send_limit": None},
}
TIER_ORDER = ["Free", "Developer", "Startup"]

EMAIL_APPROACHING_PCT = 70
EMAIL_AT_CAP_PCT = 100
DAILY_APPROACHING_PCT = 70
DAILY_AT_CAP_PCT = 100
SEVERITY_ORDER = {"at_cap": 0, "approaching": 1, "none": 2, "n/a": 3}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REAL_CSV = PROJECT_ROOT / "real_accounts_usage.csv"
SIM_CSV = PROJECT_ROOT / "simulated_accounts.csv"
CSV_OUT = PROJECT_ROOT / "alerts.csv"


def next_tier(tier):
    idx = TIER_ORDER.index(tier)
    return TIER_ORDER[idx + 1] if idx + 1 < len(TIER_ORDER) else None


def classify_monthly(inbox_at_cap, email_pct):
    if inbox_at_cap or email_pct >= EMAIL_AT_CAP_PCT:
        return "at_cap"
    if email_pct >= EMAIL_APPROACHING_PCT:
        return "approaching"
    return "none"


def classify_daily(daily_pct, daily_limit):
    if daily_limit is None:
        return "n/a"
    if daily_pct >= DAILY_AT_CAP_PCT:
        return "at_cap"
    if daily_pct >= DAILY_APPROACHING_PCT:
        return "approaching"
    return "none"


def worse(level_a, level_b):
    return level_a if SEVERITY_ORDER[level_a] <= SEVERITY_ORDER[level_b] else level_b


def suggest_action(tier, alert_level, inbox_at_cap, email_pct, emails_used, email_limit, daily_level, daily_sent, daily_limit):
    upgrade = next_tier(tier)

    if alert_level == "none":
        return f"Comfortably within {tier} tier limits; no action needed."

    has_daily = daily_level != "n/a"
    monthly_elevated = inbox_at_cap or email_pct >= EMAIL_APPROACHING_PCT
    daily_elevated = has_daily and daily_level in ("approaching", "at_cap")

    drivers = []
    if inbox_at_cap:
        drivers.append("inbox count")
    if email_pct >= EMAIL_APPROACHING_PCT:
        drivers.append("monthly email volume")
    if daily_elevated:
        drivers.append("daily email volume")
    driver_text = " and ".join(drivers) if drivers else "usage"

    if daily_elevated and not monthly_elevated:
        detail = (
            f" ({daily_sent} of {daily_limit} daily emails sent, monthly usage is still low "
            f"at {emails_used} of {email_limit} -- daily limit is the real constraint here)"
        )
    elif monthly_elevated and has_daily and not daily_elevated:
        detail = (
            f" ({daily_sent} of {daily_limit} daily emails sent, but {emails_used} of {email_limit} "
            f"for the month -- monthly limit is the real constraint here)"
        )
    elif has_daily:
        detail = f" ({daily_sent} of {daily_limit} daily, {emails_used} of {email_limit} monthly)"
    else:
        detail = ""

    if upgrade is None:
        return (
            f"Already on the highest published AgentMail tier ({tier}) and "
            f"{driver_text} is high{detail}; contact AgentMail for custom/enterprise limits."
        )
    if alert_level == "at_cap":
        return f"At or over the {tier} tier {driver_text} limit{detail}; upgrade to {upgrade} now to avoid service interruption."
    return f"Approaching the {tier} tier {driver_text} limit{detail}; consider upgrading to {upgrade} soon."


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
        daily_sent = int(row.get("daily_sent", 0))
        daily_limit = caps["daily_send_limit"]

        # No zero-guard needed here: all three denominators come from the
        # hardcoded TIERS config above, never from per-account data.
        inbox_pct = round(inbox_count / caps["inbox_limit"] * 100, 1)
        inbox_at_cap = inbox_count >= caps["inbox_limit"]
        email_pct = round(emails_used / caps["email_limit"] * 100, 1)
        daily_pct = round(daily_sent / daily_limit * 100, 1) if daily_limit else None

        monthly_level = classify_monthly(inbox_at_cap, email_pct)
        daily_level = classify_daily(daily_pct, daily_limit)
        alert_level = worse(monthly_level, daily_level)

        upgrade = next_tier(tier)
        suggested_next_tier = tier if (alert_level == "none" or upgrade is None) else upgrade
        action = suggest_action(
            tier, alert_level, inbox_at_cap, email_pct, emails_used, caps["email_limit"],
            daily_level, daily_sent, daily_limit,
        )

        results.append(
            {
                "pod_id": row["pod_id"],
                "pod_name": row.get("pod_name", ""),
                "tier": tier,
                "inbox_usage_pct": inbox_pct,
                "inbox_at_cap": inbox_at_cap,
                "email_usage_pct": email_pct,
                "daily_sent": daily_sent,
                "daily_usage_pct": daily_pct if daily_pct is not None else "",
                "daily_alert_level": daily_level,
                "alert_level": alert_level,
                "suggested_next_tier": suggested_next_tier,
                "suggested_action": action,
                "data_source": row.get("data_source", ""),
                "_worst_pct": max(email_pct, daily_pct or 0),
            }
        )

    # sort by severity, then by whichever running-total metric (monthly or daily) is worse
    results.sort(key=lambda r: (SEVERITY_ORDER[r["alert_level"]], -r["_worst_pct"]))

    fieldnames = [
        "pod_id",
        "pod_name",
        "tier",
        "inbox_usage_pct",
        "inbox_at_cap",
        "email_usage_pct",
        "daily_sent",
        "daily_usage_pct",
        "daily_alert_level",
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
        daily_str = f"{r['daily_usage_pct']:>5.1f}%" if r["daily_usage_pct"] != "" else "  n/a"
        print(
            f"[{r['alert_level'].upper():>10}] {r['pod_name'] or r['pod_id']:<18} "
            f"[{r['data_source']:<9}] tier={r['tier']:<9} inbox={r['inbox_usage_pct']:>5.1f}%"
            f"{'(AT CAP)' if r['inbox_at_cap'] else '':<9} email={r['email_usage_pct']:>5.1f}% "
            f"daily={daily_str} -> {r['suggested_action']}"
        )
    print(f"\nWrote {CSV_OUT.name} ({len(results)} accounts)")


if __name__ == "__main__":
    main()
