"""Emails real accounts that just hit a Free or Developer tier cap. Reads
priority_accounts.csv, filtered to alert_level = at_cap and tier in (Free,
Developer). Writes nothing to disk; either sends real email or prints a
preview.

Free and Developer tier caps get an automated nudge: the upgrade decision at
those tiers is small and self-serve, so a specific, numbers-driven email is
enough to get the account unblocked. Startup tier is excluded on purpose.
Those accounts stay flagged in priority_accounts.csv for a human, since deal
complexity at that tier (SSO, custom deployment, bulk discounts) is worth a
real conversation.

Only sends real email to the 3 real accounts (Acme Corp, Bright Labs, Cold
Startup), since they're the only ones with a real inbox to receive it. The
15 simulated accounts never receive anything. If no real account currently
qualifies, their nudge emails print as a labeled preview instead.

The email names whichever of monthly or daily volume is actually driving
the alert (Free tier only has a daily cap), instead of always citing
monthly numbers that may look fine for an account that's only at_cap on
the daily dimension.

Demo limitation, not a design choice: real sends use one of the 3 mock
customer inboxes (e.g. Acme Corp) as the "From" address, signing off as
"AgentMail Growth." A real system would send from AgentMail's own domain,
not a customer's inbox. See README.md "Known limitations".
"""
import csv
import json
from pathlib import Path

from client import post
from send_emails import current_message_count, SAFETY_CAP
from tier_alerts import TIERS, next_tier, EMAIL_APPROACHING_PCT

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRIORITY_CSV = PROJECT_ROOT / "priority_accounts.csv"
REAL_CSV = PROJECT_ROOT / "real_accounts_usage.csv"
SIM_CSV = PROJECT_ROOT / "simulated_accounts.csv"
STATE_JSON = PROJECT_ROOT / "state.json"

SENDER_DISPLAY_NAME = "AgentMail Growth"
# Demo workaround, not a real design choice: picks one of the 3 mock customer
# inboxes to double as the "AgentMail Growth" sender, since the demo has no
# separate AgentMail-owned sending inbox and is capped at 3 real inboxes
# total. A real deployment would send from AgentMail's own domain, never a
# customer's inbox. Falls back to a different real pod if the preferred
# sender is ever also the recipient.
PREFERRED_SENDER_POD = "Acme Corp"


def load_qualifying():
    with open(PRIORITY_CSV, newline="") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if r["alert_level"] == "at_cap" and r["tier"] in ("Free", "Developer")]


def load_usage_lookup():
    lookup = {}
    for path in (REAL_CSV, SIM_CSV):
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                lookup[row["pod_id"]] = row
    return lookup


def load_real_inboxes():
    with open(STATE_JSON) as f:
        state = json.load(f)
    return {p["pod_name"]: p for p in state["pods"]}


def compose_email(account, usage_row):
    tier = account["tier"]
    caps = TIERS[tier]
    inbox_count = int(usage_row["inbox_count"])
    emails_used = int(usage_row["messages_sent"]) + int(usage_row["messages_received"])
    upgrade = next_tier(tier)
    upgrade_caps = TIERS[upgrade]

    inbox_at_cap = inbox_count >= caps["inbox_limit"]
    email_pct = emails_used / caps["email_limit"] * 100
    monthly_elevated = inbox_at_cap or email_pct >= EMAIL_APPROACHING_PCT

    daily_limit = caps.get("daily_send_limit")
    daily_alert_level = account.get("daily_alert_level", "n/a")
    daily_elevated = daily_alert_level in ("approaching", "at_cap")
    daily_sent = int(account.get("daily_sent") or usage_row.get("daily_sent") or 0)

    usage_line = (
        f"you've used {inbox_count} of {caps['inbox_limit']} inboxes and sent "
        f"{emails_used} of {caps['email_limit']} emails this month on the {tier} plan"
    )
    if daily_limit is not None:
        if daily_elevated and not monthly_elevated:
            usage_line = (
                f"you've sent {daily_sent} of the {daily_limit} emails your {tier} plan "
                f"allows per day. Monthly usage is still low ({emails_used} of "
                f"{caps['email_limit']}) — it's today's daily limit that's blocking you, "
                f"not the month"
            )
        elif daily_elevated and monthly_elevated:
            usage_line += f", and you've also sent {daily_sent} of {daily_limit} allowed today"
        elif monthly_elevated:
            usage_line += f" ({daily_sent} of {daily_limit} sent today, which is fine)"

    daily_removed_note = ", with no daily send limit" if daily_limit is not None else ""

    subject = f"You've hit the {tier} tier limit on AgentMail"
    text = (
        f"Hi {account['pod_name']} team,\n\n"
        f"Your AgentMail account just hit its {tier} tier limit — {usage_line}.\n\n"
        f"The {upgrade} tier gives you {upgrade_caps['inbox_limit']} inboxes and "
        f"{upgrade_caps['email_limit']:,} emails/month{daily_removed_note} — upgrading "
        f"unblocks you right away and only takes a couple of minutes.\n\n"
        f"— {SENDER_DISPLAY_NAME}"
    )
    return subject, text


def send_real_nudges(qualifying, usage_lookup):
    real_inboxes = load_real_inboxes()

    count = current_message_count()
    print(f"[usage check] org message_count so far: {count}")
    if count >= SAFETY_CAP:
        raise SystemExit(f"STOP: org message_count {count} is approaching the {SAFETY_CAP} safety threshold.")

    print(f"=== Sending real nudge emails to {len(qualifying)} qualifying REAL account(s) ===\n")
    for account in qualifying:
        usage_row = usage_lookup[account["pod_id"]]
        subject, text = compose_email(account, usage_row)

        recipient_name = account["pod_name"]
        recipient = real_inboxes[recipient_name]
        sender_name = (
            PREFERRED_SENDER_POD
            if recipient_name != PREFERRED_SENDER_POD
            else next(name for name in real_inboxes if name != PREFERRED_SENDER_POD)
        )
        sender = real_inboxes[sender_name]

        print(
            f"--- {recipient_name} ({recipient['email']}) <- {sender_name} acting as {SENDER_DISPLAY_NAME} "
            f"(demo workaround: reusing a customer inbox as sender, see README) ---"
        )
        print(f"Subject: {subject}\n{text}\n")
        post(
            f"/v0/inboxes/{sender['inbox_id']}/messages/send",
            {"to": [recipient["email"]], "subject": subject, "text": text},
        )
        print("Sent.\n")


def preview_simulated_nudges(qualifying, usage_lookup):
    print(
        f"No real accounts currently qualify (alert_level=at_cap, tier in Free/Developer).\n"
        f"Showing a PREVIEW of what would be sent to {len(qualifying)} qualifying SIMULATED "
        f"account(s) — NOT sent, these accounts have no real AgentMail inbox.\n"
    )
    for account in qualifying:
        usage_row = usage_lookup[account["pod_id"]]
        subject, text = compose_email(account, usage_row)
        print(f"[PREVIEW ONLY - NOT SENT] To: {account['pod_name']} (simulated)")
        print(f"Subject: {subject}\n{text}\n{'-' * 60}\n")


def main():
    qualifying = load_qualifying()
    real_qualifying = [q for q in qualifying if q["data_source"] == "real"]
    sim_qualifying = [q for q in qualifying if q["data_source"] == "simulated"]
    usage_lookup = load_usage_lookup()

    if real_qualifying:
        send_real_nudges(real_qualifying, usage_lookup)
    elif sim_qualifying:
        preview_simulated_nudges(sim_qualifying, usage_lookup)
    else:
        print("No accounts (real or simulated) currently qualify as at_cap on Free/Developer tier.")


if __name__ == "__main__":
    main()
