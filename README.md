# AgentMail Usage Demo

A usage-based product creates natural expansion signals. When an account gets close to its inbox or email limit, AgentMail has a chance to step in before the customer hits a wall, upgrades without assistance, or churns out of frustration.

This project turns AgentMail usage data into a ranked list of accounts that may need attention.

## What it does

The pipeline:

* Pulls live usage data from AgentMail's API
* Compares each account against its plan's inbox limit, monthly email limit, and (Free tier only) daily email limit
* Flags accounts that are approaching or already at a cap, on either the monthly or the daily view
* Scores customer fit using a small set of usage-based criteria
* Ranks accounts by urgency and fit
* Separates accounts that can receive an automated nudge from those that should go to a person

The current dataset includes 18 accounts:

* 3 real accounts created through AgentMail's production API
* 15 simulated accounts added to show how the system works across a larger customer base

Every output includes a `data_source` field so real and simulated records are easy to distinguish.

## Current output

The latest run identifies:

* 4 accounts at a plan limit
* 4 accounts approaching a limit
* 10 accounts with no immediate usage concern

The highest-priority accounts are Acme Corp, Fetchly AI, and RoadSync Dealers, tied at the top (Wrapley ties them too, just past the top three). Acme Corp is a real account: its monthly usage is low (4% of the 3,000/month cap), but it sent exactly 100 of its 100-per-day limit today, so it's at cap on the daily view alone. Fetchly AI and RoadSync Dealers are simulated accounts at their tier's inbox limit.

The final ranked output is written to `priority_accounts.csv`.

## Run the demo

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 run_all.py
```

The project runs in replay mode by default, so no API key is required. It uses the checked-in usage data and prints:

* Total accounts processed
* Alert breakdown
* Top three priority accounts

To regenerate the real usage data from an AgentMail account:

```bash
cp .env.example .env
# Add AGENTMAIL_API_KEY
python3 run_all.py --live
```

Live mode first checks that the account is on the Free tier with no payment method attached. It then creates the demo resources, sends the seed messages, pulls usage data, and runs the same scoring pipeline.

## How the pipeline works

1. `create_resources.py` creates three pods and one inbox per pod.
2. `send_emails.py` sends an uneven set of test messages so the accounts show different usage patterns.
3. `pull_metrics.py` retrieves real per-pod usage from AgentMail's Metrics API, including today's send count via the API's daily bucketing.
4. `simulated_accounts.py` adds 15 mock accounts across AgentMail's three tiers.
5. `tier_alerts.py` compares usage against plan limits and assigns an alert status. Monthly and daily email volume are scored independently, since an account can be fine on one and at cap on the other; the overall status is whichever is worse.
6. `icp_scoring.py` scores each account against two customer-fit segments.
7. `combine.py` merges urgency and fit into one ranked account list.

`auto_nudge.py` runs separately. It emails real Free- and Developer-tier accounts that have reached a cap, naming whichever of the monthly or daily limit is actually responsible, while leaving Startup-tier accounts for a person to review.

The idea is that a small, self-serve upgrade can be automated. A larger account with SSO, custom deployment, or negotiated pricing deserves a conversation.

## Repository structure

```text
agentmail-usage-demo/
  run_all.py
  real_accounts_usage.csv
  simulated_accounts.csv
  alerts.csv
  icp_scores.csv
  priority_accounts.csv
  state.json
  src/
    client.py
    safety_check.py
    create_resources.py
    send_emails.py
    pull_metrics.py
    simulated_accounts.py
    tier_alerts.py
    icp_scoring.py
    combine.py
    auto_nudge.py
    bolster_real_usage.py
```

## What I would build next

The next version would add:

* Usage trends and projected cap dates instead of relying on a snapshot percentage, on both the monthly and daily views
* Webhook-based updates rather than scheduled batch runs
* Slack or CRM routing so the output reaches the team automatically
* A scoring model calibrated against real conversion and expansion data
* A dedicated AgentMail-owned sending inbox for automated outreach

## Limitations

The three real accounts are valid production API records. AgentMail's Free tier limits sending to 100 emails per day, separate from and stricter than the 3,000/month figure, which made it impractical to push a real account's monthly usage anywhere near its cap during this demo. Tracking that daily limit directly turned this into a real result instead of just an obstacle: Acme Corp sent exactly 100 of its 100-per-day limit today, so it's a genuine at-cap example, driven by the daily view rather than the monthly one its usage still looks low against.

The reply-endpoint fix that lets real conversations thread together server-side (rather than every message starting its own thread) hasn't been re-verified against a live send, since that would require sending real email and the daily limit above is still in effect.

The scoring model is intentionally simple. Its thresholds and weights are reasonable defaults, not values learned from AgentMail's customer data.

The automated nudge also reuses one of the demo inboxes as the sender. A production version should send from an AgentMail-owned inbox and domain.
