"""One-time script that pushes Acme Corp's real usage toward its Free-tier
cap (see README "Known limitations"). Reads state.json for pod/inbox IDs.
Writes nothing directly; the sent emails show up in AgentMail's Metrics API.

Sends real, one-way outbound emails from each of the 3 real pods' own inboxes
to synthetic recipient addresses under example.com/example.org/example.net --
domains IANA reserves for documentation/testing, so nothing is ever delivered
to a real person. One-way sends only touch the SENDING pod's messages_sent
count, not any other real pod's messages_received -- that's what lets Acme's
total be pushed near its cap without dragging Bright/Cold's totals up too
(any inter-pod thread would inflate both sides equally, eating the shared
org-wide budget twice as fast).

Sequential with retry/backoff on 429 -- an earlier attempt at 10-way
concurrency hit AgentMail's rate limit almost immediately (84/2800 sends
succeeded before near-total failure). PLAN below is the REMAINING amount
needed per pod, computed from the real per-pod totals after that partial run,
not the original targets.

NOT idempotent -- re-running this adds MORE real messages on top of whatever
is already there. This was a deliberate one-time step to give the demo a
real at_cap example; it should not be re-run as part of the regular pipeline.
"""
import json
import time
from pathlib import Path

import requests

from client import API_KEY, BASE_URL, get

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_JSON = PROJECT_ROOT / "state.json"

# (pod_name, additional one-way sends needed) -- remaining amount after the
# first (partially rate-limited) attempt; see README for the math.
PLAN = [
    ("Acme Corp", 2700),
    ("Bright Labs", 40),
    ("Cold Startup", 25),
]

DOMAINS = ["example.com", "example.org", "example.net"]
TEMPLATES = [
    ("Weekly digest #{i}", "Here is your weekly digest, item #{i}."),
    ("Notification: event #{i} processed", "Event #{i} has been processed successfully."),
    ("Account update #{i}", "Your account was updated (ref #{i})."),
    ("New activity #{i}", "New activity detected in your workspace (id #{i})."),
]

PACING_DELAY = 0.4  # seconds between requests, proactive rate-limit avoidance
MAX_RETRIES = 8
CHECK_EVERY = 100  # print progress + org message_count every N sends
HARD_CEILING = 2950  # org-wide real message_count safety stop, leaves real margin under 3,000


def current_message_count():
    usage = get("/v0/metrics/usage", params={"usage_types": ["message_count"]})
    points = usage.get("message_count", [])
    return points[-1]["value"] if points else 0


def load_real_inboxes():
    with open(STATE_JSON) as f:
        state = json.load(f)
    return {p["pod_name"]: p for p in state["pods"]}


def send_one_with_retry(inbox_id, i):
    domain = DOMAINS[i % len(DOMAINS)]
    to_addr = f"user{i}@{domain}"
    subject_tpl, body_tpl = TEMPLATES[i % len(TEMPLATES)]
    payload = {"to": [to_addr], "subject": subject_tpl.format(i=i), "text": body_tpl.format(i=i)}
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    for attempt in range(MAX_RETRIES):
        r = requests.post(f"{BASE_URL}/v0/inboxes/{inbox_id}/messages/send", headers=headers, json=payload, timeout=30)
        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else min(2**attempt, 20)
            time.sleep(delay)
            continue
        r.raise_for_status()
        return
    raise RuntimeError(f"gave up after {MAX_RETRIES} retries (still 429)")


def send_batch(pod_name, inbox_id, count):
    sent = 0
    failed = 0
    for i in range(count):
        try:
            send_one_with_retry(inbox_id, i)
            sent += 1
        except Exception as e:
            failed += 1
            print(f"    [warn] send failed for index {i}: {e}")
        time.sleep(PACING_DELAY)

        if (i + 1) % CHECK_EVERY == 0 or (i + 1) == count:
            count_now = current_message_count()
            print(f"  [{pod_name}] sent {sent}/{count} so far (failed={failed}) -- org message_count={count_now}")
            if count_now >= HARD_CEILING:
                raise SystemExit(f"STOP: org message_count {count_now} reached the {HARD_CEILING} safety ceiling.")

    return sent, failed


def main():
    inboxes = load_real_inboxes()

    start_count = current_message_count()
    print(f"[usage check] org message_count before bolstering: {start_count}")
    if start_count >= HARD_CEILING:
        raise SystemExit(f"STOP: org message_count {start_count} already at/above the {HARD_CEILING} safety ceiling.")

    for pod_name, additional in PLAN:
        inbox = inboxes[pod_name]
        print(f"\n=== {pod_name}: sending {additional} one-way outbound emails ===")
        sent, failed = send_batch(pod_name, inbox["inbox_id"], additional)
        print(f"=== {pod_name}: done -- {sent} sent, {failed} failed ===")

    final_count = current_message_count()
    print(f"\n[usage check] org message_count after bolstering: {final_count}")


if __name__ == "__main__":
    main()
