"""Creates 3 pods (mock customer accounts), 1 inbox each: the ceiling for
AgentMail's Free tier. Reads nothing. Writes state.json with each pod's ID,
inbox ID, and email address, for later scripts to read. Creates real
resources in the AgentMail account. Do not run this against an account that
already has pods you want to keep.
"""
import json
from pathlib import Path

from client import post

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_JSON = PROJECT_ROOT / "state.json"

# display_name rejects parentheses/special chars, so the usage tier
# (high / moderate / low-dormant) is documented in the README instead.
POD_SPECS = [
    {"name": "Acme Corp", "client_id": "demo-acme-corp"},
    {"name": "Bright Labs", "client_id": "demo-bright-labs"},
    {"name": "Cold Startup", "client_id": "demo-cold-startup"},
]


def create_pods_and_inboxes():
    state = {"pods": []}
    for spec in POD_SPECS:
        pod = post("/v0/pods", {"name": spec["name"], "client_id": spec["client_id"]})
        pod_id = pod["pod_id"]

        inbox = post(
            f"/v0/pods/{pod_id}/inboxes",
            {"display_name": spec["name"], "client_id": spec["client_id"]},
        )

        state["pods"].append(
            {
                "pod_id": pod_id,
                "pod_name": spec["name"],
                "inbox_id": inbox["inbox_id"],
                "email": inbox["email"],
            }
        )
        print(f"Created pod {pod_id} ({spec['name']}) with inbox {inbox['email']}")

    with open(STATE_JSON, "w") as f:
        json.dump(state, f, indent=2)
    print(f"\nWrote {STATE_JSON.name}")
    return state


if __name__ == "__main__":
    create_pods_and_inboxes()
