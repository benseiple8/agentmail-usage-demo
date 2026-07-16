# AgentMail Usage Demo

AgentMail bills usage-based, so a tier cap isn't a soft nudge. It's a forced decision
point. The moment an account hits its inbox or email ceiling, something happens whether
anyone at AgentMail is watching or not: the account gets frustrated and churns, or it
upgrades on its own and no one internally knows why or gets credit for the assist. This
project pulls real usage data from AgentMail's own API, adds a larger synthetic book of
accounts to show the system at scale, and ranks all of them by how urgently a human
should look at each one.

## The result

Across 18 accounts (3 real, pulled live from AgentMail; 15 simulated), the pipeline
currently flags 3 as `at_cap`, 3 as `approaching` a cap, and 12 as fine. The top 3 by
priority score are Fetchly AI, RoadSync Dealers, and Wrapley, all at their tier's inbox
limit right now. Run the pipeline yourself and these numbers regenerate live.

## Run it yourself

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 run_all.py
```

No API key, no `.env` file. `run_all.py` runs in replay mode by default, using the
checked-in `real_accounts_usage.csv`, and prints a summary: accounts processed, alert
breakdown, top 3 priority accounts. Full results land in `priority_accounts.csv`.

To regenerate the real data against your own AgentMail account:

```bash
cp .env.example .env   # add your AGENTMAIL_API_KEY
python3 run_all.py --live
```

`--live` checks your account is Free tier with no payment method on file, creates 3
pods and sends the seed conversation if they don't already exist, then runs the same
pipeline against real API calls.

## What's real vs. simulated

3 of these 18 accounts are real: Acme Corp, Bright Labs, Cold Startup. Every pod, inbox,
and email for these three exists in AgentMail's production API. Their numbers in every
CSV here come straight from AgentMail's own Metrics API.

The other 15 are synthetic: Fetchly AI, Parsely Labs, Dockwise, Nimbic Legal, RoadSync
Dealers, Verdict AI, Agentix, Wrapley, CaseFlow Legal, DealerPing, SupportLoop, TortAI,
AutoScribe, Compozr, LegalMesh. None of these exist in AgentMail. No pods, no inboxes,
no emails. They're hand-built to show the system at a realistic scale, modeled on the
kind of companies in AgentMail's own customer base: agent-infra and dev-tool builders
like Browser Use and Composio, and vertical AI companies like eve.legal and CarEdge.
None of the 15 mock accounts are those companies.

Every CSV here carries a `data_source` column (`real` or `simulated`) on every row.
Every script's header states which kind of data it touches.

## How it works

1. **`create_resources.py`** creates 3 pods, 1 inbox each: the ceiling for AgentMail's
   Free tier.
2. **`send_emails.py`** sends a small, deliberately uneven set of test emails between
   them, so one account looks high-usage, one moderate, one dormant.
3. **`pull_metrics.py`** pulls real per-pod usage back out of AgentMail's Metrics API.
4. **`simulated_accounts.py`** adds 15 synthetic accounts spanning all three AgentMail
   tiers.
5. **`tier_alerts.py`** compares each account's usage to AgentMail's published tier
   caps, as if each pod were its own independent customer account. Inbox count gets a
   binary at-cap flag, since it's a one-time provisioning choice with no trend to read.
   Email volume gets graduated 70%/100% thresholds, since it's a running total that can
   actually trend toward a cap.
6. **`icp_scoring.py`** scores every account against 2 customer-fit segments using 3
   stated criteria each, computed directly from usage numbers.
7. **`combine.py`** merges the alert and fit data into one ranked list: an account
   about to hit a wall beats a good-fit account with no urgency.

`auto_nudge.py` runs separately, after the pipeline. It emails real `at_cap` accounts on
Free or Developer tier directly, since the upgrade there is small and self-serve. It
leaves Startup-tier accounts for a human, since that's where SSO, custom deployment, and
negotiated pricing make a real conversation worth having.

```
agentmail-usage-demo/
  run_all.py                  # runs the full pipeline, prints the summary
  real_accounts_usage.csv     # output of pull_metrics.py (data_source = real)
  simulated_accounts.csv      # output of simulated_accounts.py (data_source = simulated)
  alerts.csv                  # output of tier_alerts.py, all 18 accounts
  icp_scores.csv              # output of icp_scoring.py, all 18 accounts
  priority_accounts.csv       # output of combine.py, all 18 accounts, ranked
  state.json                  # pod/inbox IDs from create_resources.py
  src/
    client.py                 # AgentMail API wrapper
    safety_check.py           # confirms Free tier, no payment method, before anything runs
    create_resources.py
    send_emails.py
    pull_metrics.py
    simulated_accounts.py
    tier_alerts.py
    icp_scoring.py
    combine.py
    auto_nudge.py
    bolster_real_usage.py     # one-time script, see Known limitations
```

## What I'd build next

- **Trend-based email alerts.** Right now email usage is a single snapshot percentage.
  A real version would look at day-over-day rate and flag an account projected to hit
  its cap in 3 days, not just one already past 70%.
- **A calibrated ICP model.** The current scoring criteria are simple heuristics I could
  state and defend in one sentence each. A real version would train against actual
  AgentMail conversion or expansion data, if I had access to it.
- **Webhook-driven alerts instead of a batch pipeline.** AgentMail has a webhooks API.
  A production version would react to `message.sent` and `message.received` events as
  they happen instead of running this pipeline on a schedule.
- **A dedicated AgentMail-owned sending inbox** for `auto_nudge.py`, instead of reusing
  a customer's own inbox (see Known limitations below).
- **Routing the output somewhere a human actually works.** Slack or a CRM task, not a
  CSV someone has to remember to open.

## Known limitations

**AgentMail's Free tier caps sending at 100 emails/day**, published on AgentMail's
pricing and rate-limits pages (the Developer tier removes this cap). Pushing Acme
Corp toward the 3,000/month Free-tier ceiling meant sending far more than 100 messages
in one run, and I ran into that daily cap directly: an account-wide lockout across all
3 real inboxes at once, not a gradual throttle. Real Acme Corp usage is at 120 messages
(4% of the Free-tier cap) rather than the ~90-95% this demo aims to show for a real
`at_cap` example, because reaching that target within the daily cap would take dozens
of days, not one. The 3 `at_cap` accounts in the current run are all simulated, not
real.

**The thread-count fix is implemented but not re-verified against the live API.**
`send_emails.py` sends follow-up messages via AgentMail's reply endpoint so real
conversations thread together server-side, instead of every message starting its own
thread. Confirming this works as expected requires a real send, which is blocked by the
same daily limit above.

**`auto_nudge.py` sends real nudges from a customer inbox, not a dedicated AgentMail
sender.** This demo only has 3 real inboxes total, all standing in for mock customers,
so one of them (Acme Corp) doubles as the "AgentMail Growth" sender. A real deployment
would send from AgentMail's own domain, not a customer's inbox.

**ICP scoring is intentionally modest.** 3 stated criteria per segment, scored 0-3,
thresholds set to the dataset's own median rather than a hand-picked number. Most
accounts land in a narrow 2-3 range, and several tie as `Mixed / inconclusive`. That's
the result of scoring simple structural criteria against data built for tier variety,
not segment-identity variance.

**The 70%/100% usage thresholds and the 100/50/0 alert-priority weights are defaults I
chose to make the ranking behave sensibly**, not values derived from AgentMail's actual
churn or conversion data. I don't have access to that data.
