"""Runs the pipeline and prints a final summary.

Default (no flags): replay mode. Runs simulated_accounts -> tier_alerts ->
icp_scoring -> combine against the checked-in real_accounts_usage.csv. No
AgentMail API key needed, no .env required.

--live: runs the full pipeline against the real AgentMail API --
safety_check -> create_resources -> send_emails -> pull_metrics ->
simulated_accounts -> tier_alerts -> icp_scoring -> combine. Requires
AGENTMAIL_API_KEY in .env. Skips create_resources and send_emails if pods
already exist (state.json) -- re-running them against a live account would
create duplicate pods or double the real email history, not just refresh
the demo state.

Reads: real_accounts_usage.csv (replay mode) or the live AgentMail API
(--live mode). Outputs: simulated_accounts.csv, alerts.csv, icp_scores.csv,
priority_accounts.csv always; real_accounts_usage.csv too in --live mode.
All at the project root, plus a console summary of accounts processed, the
alert breakdown, and the top 3 priority accounts.
"""
import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC = PROJECT_ROOT / "src"
STATE_JSON = PROJECT_ROOT / "state.json"
PRIORITY_CSV = PROJECT_ROOT / "priority_accounts.csv"

SAFETY_CHECK = "safety_check.py"

# simulated_accounts.py must run before tier_alerts.py: tier_alerts.py reads
# simulated_accounts.csv if it exists, and silently skips it (producing an
# incomplete alerts.csv) if it doesn't yet.
LIVE_PIPELINE = [
    "create_resources.py",
    "send_emails.py",
    "pull_metrics.py",
    "simulated_accounts.py",
    "tier_alerts.py",
    "icp_scoring.py",
    "combine.py",
]

REPLAY_PIPELINE = [
    "simulated_accounts.py",
    "tier_alerts.py",
    "icp_scoring.py",
    "combine.py",
]


def pods_already_exist():
    if not STATE_JSON.exists():
        return False
    with open(STATE_JSON) as f:
        state = json.load(f)
    return bool(state.get("pods"))


def run_step(script):
    print(f"\n{'=' * 60}\n{script}\n{'=' * 60}", flush=True)
    result = subprocess.run([sys.executable, script], cwd=SRC)
    if result.returncode != 0:
        raise SystemExit(f"STOP: {script} exited with code {result.returncode}")


def print_summary():
    with open(PRIORITY_CSV, newline="") as f:
        rows = list(csv.DictReader(f))

    alert_counts = Counter(r["alert_level"] for r in rows)
    top3 = sorted(rows, key=lambda r: int(r["composite_score"]), reverse=True)[:3]

    print(f"\n{'=' * 60}\nSUMMARY\n{'=' * 60}")
    print(f"Accounts processed: {len(rows)}")
    print(
        f"Alert breakdown: {alert_counts.get('at_cap', 0)} at_cap, "
        f"{alert_counts.get('approaching', 0)} approaching, "
        f"{alert_counts.get('none', 0)} none"
    )
    print("\nTop 3 priority accounts:")
    for r in top3:
        print(
            f"  {r['composite_score']:>4}  [{r['alert_level']:>10}]  {r['pod_name']:<18} "
            f"({r['data_source']}, {r['tier']})"
        )
    print(f"\nFull results: {PRIORITY_CSV.name}")


def run_replay():
    print(
        "Running in replay mode against saved AgentMail data (see real_accounts_usage.csv) "
        "-- no API key needed. Use --live to regenerate against the real API with your own key.",
        flush=True,
    )
    for script in REPLAY_PIPELINE:
        run_step(script)
    print_summary()


def run_live():
    run_step(SAFETY_CHECK)

    if pods_already_exist():
        print(
            f"\n{STATE_JSON.name} already has pods -- skipping create_resources.py and send_emails.py.",
            flush=True,
        )
        steps = LIVE_PIPELINE[2:]
    else:
        steps = LIVE_PIPELINE

    for script in steps:
        run_step(script)

    print_summary()


def main():
    parser = argparse.ArgumentParser(description="Run the AgentMail usage demo pipeline.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run the full pipeline against the real AgentMail API (requires AGENTMAIL_API_KEY in .env).",
    )
    args = parser.parse_args()

    if args.live:
        run_live()
    else:
        run_replay()


if __name__ == "__main__":
    main()
