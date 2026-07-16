"""Generates 15 synthetic mock accounts spanning all three AgentMail tiers.
Reads nothing. Writes simulated_accounts.csv.

These are NOT created via the AgentMail API: no pods, inboxes, or emails
exist for them. Numbers are hand-picked, not randomized, so the demo has a
reproducible, fuller book of business: a handful of Free-tier accounts near
their cap, a batch of Developer-tier accounts at varying usage, and a couple
of larger Startup-tier accounts. Every row is tagged data_source =
"simulated" to keep it clearly distinguishable from the 3 real accounts in
real_accounts_usage.csv.

daily_sent is roughly messages_sent / 30 for most accounts, scaled to a
plausible single day at that account's usage level. 4 Free-tier accounts
(where AgentMail's 100/day cap actually applies) are deliberately set away
from that average to show the daily and monthly views can disagree: Fetchly
AI and RoadSync Dealers are already at their monthly/inbox cap but calm on a
daily basis, while Dockwise is fine on the month but spikes near the daily
cap on a single busy day.
"""
import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_CSV = PROJECT_ROOT / "simulated_accounts.csv"

# (pod_id, pod_name, tier, inbox_count, messages_sent, messages_received, thread_count, daily_sent)
ACCOUNTS = [
    ("sim-001", "Fetchly AI",       "Free",      3,   1450,  1400,   620,   45),
    ("sim-002", "Parsely Labs",     "Free",      2,   1100,  1100,   540,   48),
    ("sim-003", "Dockwise",         "Free",      2,    610,   590,   310,   98),
    ("sim-004", "Nimbic Legal",     "Free",      1,    210,   190,    95,   15),
    ("sim-005", "RoadSync Dealers", "Free",      3,    260,   240,   140,   20),
    ("sim-006", "Verdict AI",       "Free",      1,     28,    22,    18,    3),
    ("sim-007", "Agentix",          "Developer", 9,   4500,  4300,  1950,  150),
    ("sim-008", "Wrapley",          "Developer", 10,  4900,  4700,  2100,  163),
    ("sim-009", "CaseFlow Legal",   "Developer", 6,   2650,  2550,  1300,   88),
    ("sim-010", "DealerPing",       "Developer", 7,   3100,  3000,  1450,  103),
    ("sim-011", "SupportLoop",      "Developer", 4,   1320,  1280,   780,   44),
    ("sim-012", "TortAI",           "Developer", 8,   3750,  3650,  1600,  125),
    ("sim-013", "AutoScribe",       "Developer", 5,   1680,  1620,   900,   56),
    ("sim-014", "Compozr",          "Startup",   45, 26500, 25500, 11200,  883),
    ("sim-015", "LegalMesh",        "Startup",   112, 49500, 48500, 21000, 1650),
]

FIELDNAMES = [
    "pod_id",
    "pod_name",
    "tier",
    "inbox_count",
    "messages_sent",
    "messages_received",
    "thread_count",
    "daily_sent",
    "data_source",
]


def main():
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for pod_id, pod_name, tier, inbox_count, sent, received, threads, daily_sent in ACCOUNTS:
            writer.writerow(
                {
                    "pod_id": pod_id,
                    "pod_name": pod_name,
                    "tier": tier,
                    "inbox_count": inbox_count,
                    "messages_sent": sent,
                    "messages_received": received,
                    "thread_count": threads,
                    "daily_sent": daily_sent,
                    "data_source": "simulated",
                }
            )
    print(f"Wrote {OUT_CSV.name} ({len(ACCOUNTS)} simulated accounts)")


if __name__ == "__main__":
    main()
