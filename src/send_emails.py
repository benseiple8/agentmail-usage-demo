"""Sends a small, deliberately uneven set of test emails between the 3 real
inboxes, so one pod looks high-usage, one moderate, one dormant. Reads
state.json for pod/inbox IDs. Writes nothing directly; the sent emails show
up in AgentMail's Metrics API for pull_metrics.py to read later. Before every
batch, checks the org's real cumulative message_count and aborts if it's
approaching 2,800 (well short of the 3,000/month Free-tier ceiling).

Each multi-message exchange is a real reply chain: the first message in a
thread uses POST /messages/send, and every follow-up uses
POST /messages/{message_id}/reply on the previous message, so AgentMail
threads them together server-side instead of every message starting its own
thread.

Unverified assumption: this relies on message_id from a send/reply response
being a shared identifier usable in a reply call from the OTHER party's
inbox_id (Bright replying to a message_id it received from Acme's send).
This hasn't been confirmed against a real send yet (see README "Known
limitations"). Confirm it by running this for real and checking that
thread_count in pull_metrics.py's output is lower than the message count,
not equal to it.

Traffic shape (all totals are sent+received "involvement" per pod, since
every message touches exactly two pods):
  - Acme <-> Bright: 5 threads, 14 messages  -> Acme +14, Bright +14
  - Acme <-> Cold:    3 threads, 6 messages  -> Acme +6,  Cold +6
  - Bright <-> Cold:  0 messages (dormant pair)
  Pod totals: Acme 20 (high), Bright 14 (moderate), Cold 6 (low/dormant).
  20 messages / 8 threads total, far under the free-tier ceiling.
"""
import json
import time
from pathlib import Path

from client import get, post

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_JSON = PROJECT_ROOT / "state.json"

SAFETY_CAP = 2800


def current_message_count():
    usage = get("/v0/metrics/usage", params={"usage_types": ["message_count"]})
    points = usage.get("message_count", [])
    return points[-1]["value"] if points else 0


def send_first(inbox_id, to_email, subject, text):
    resp = post(
        f"/v0/inboxes/{inbox_id}/messages/send",
        {"to": [to_email], "subject": subject, "text": text},
    )
    return resp["message_id"]


def send_reply(inbox_id, message_id, text):
    resp = post(f"/v0/inboxes/{inbox_id}/messages/{message_id}/reply", {"text": text})
    return resp["message_id"]


def run_thread(subject, turns):
    """turns: list of (inbox_id, to_email_or_None, text). First turn uses
    send (to_email required); later turns use reply (to_email ignored,
    AgentMail infers the recipient from the message being replied to)."""
    last_message_id = None
    for idx, (inbox_id, to_email, text) in enumerate(turns):
        if idx == 0:
            last_message_id = send_first(inbox_id, to_email, subject, text)
            print(f"  [send]  {subject!r} -> {to_email} (message_id={last_message_id})")
        else:
            last_message_id = send_reply(inbox_id, last_message_id, text)
            print(f"  [reply] Re: {subject!r} (message_id={last_message_id})")
        time.sleep(0.3)


def guarded_batch(label, threads):
    count = current_message_count()
    print(f"[usage check] org message_count so far: {count}")
    if count >= SAFETY_CAP:
        raise SystemExit(
            f"STOP: org message_count {count} is approaching the {SAFETY_CAP} safety threshold."
        )

    print(f"--- sending batch: {label} ({len(threads)} threads) ---")
    for subject, turns in threads:
        run_thread(subject, turns)


def main():
    with open(STATE_JSON) as f:
        state = json.load(f)
    pods = {p["pod_name"]: p for p in state["pods"]}
    acme = pods["Acme Corp"]
    bright = pods["Bright Labs"]
    cold = pods["Cold Startup"]

    guarded_batch(
        "Acme <-> Bright (high volume)",
        [
            (
                "Order #1042 confirmed",
                [
                    (acme["inbox_id"], bright["email"], "Hi, confirming order #1042 shipped today."),
                    (bright["inbox_id"], None, "Thanks, received!"),
                ],
            ),
            (
                "Invoice INV-88 issued",
                [
                    (acme["inbox_id"], bright["email"], "Invoice INV-88 is now available, due Friday."),
                    (bright["inbox_id"], None, "Paid, thank you."),
                ],
            ),
            (
                "Shipment update for order #1042",
                [
                    (acme["inbox_id"], bright["email"], "Your package is out for delivery."),
                    (bright["inbox_id"], None, "Great, thanks for the update."),
                ],
            ),
            (
                "Support ticket #204",
                [
                    (acme["inbox_id"], bright["email"], "We've opened ticket #204 for your request."),
                    (bright["inbox_id"], None, "Appreciate the quick response."),
                    (acme["inbox_id"], None, "Ticket #204 has been resolved."),
                    (bright["inbox_id"], None, "Confirmed working, thanks!"),
                ],
            ),
            (
                "Weekly usage digest",
                [
                    (acme["inbox_id"], bright["email"], "Here is your weekly usage digest."),
                    (bright["inbox_id"], None, "Quick question about last week's spike."),
                    (acme["inbox_id"], None, "Answered inline below."),
                    (bright["inbox_id"], None, "Got it, thanks for clarifying!"),
                ],
            ),
        ],
    )

    guarded_batch(
        "Acme <-> Cold (occasional re-engagement)",
        [
            (
                "We miss you - quick check-in",
                [
                    (acme["inbox_id"], cold["email"], "We noticed you haven't logged in recently."),
                    (cold["inbox_id"], None, "Still evaluating, will follow up."),
                ],
            ),
            (
                "Your account usage summary",
                [
                    (acme["inbox_id"], cold["email"], "Your account has had minimal activity this month."),
                    (cold["inbox_id"], None, "Thanks for the summary."),
                ],
            ),
            (
                "Final reminder before plan review",
                [
                    (acme["inbox_id"], cold["email"], "Following up ahead of your plan review."),
                    (cold["inbox_id"], None, "Will decide next week."),
                ],
            ),
        ],
    )

    final_count = current_message_count()
    print(f"[usage check] org message_count after run: {final_count}")


if __name__ == "__main__":
    main()
