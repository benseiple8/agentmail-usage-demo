"""Confirms the AgentMail account is Free tier with no payment method on file
before anything creates resources or sends email. Reads GET /v0/organizations
(AgentMail has no separate "Who Am I" endpoint) and prints the raw fields.
There's no literal "plan tier" field either, so free-tier status is inferred
from no billing_id/billing_type/billing_subscription_id, plus an inbox_limit
consistent with a free ceiling. Writes nothing; exits non-zero if anything
looks off.
"""
from client import get


def check():
    org = get("/v0/organizations")

    inbox_count = org.get("inbox_count")
    inbox_limit = org.get("inbox_limit")
    domain_count = org.get("domain_count")
    domain_limit = org.get("domain_limit")
    billing_id = org.get("billing_id")
    billing_type = org.get("billing_type")
    billing_subscription_id = org.get("billing_subscription_id")

    has_payment = bool(billing_id or billing_type or billing_subscription_id)

    print("=== AgentMail Organization (Auth + Org check, GET /v0/organizations) ===")
    print(f"organization_id:          {org.get('organization_id')}")
    print(f"inbox_count / inbox_limit: {inbox_count} / {inbox_limit}")
    print(f"domain_count / domain_limit: {domain_count} / {domain_limit}")
    print(f"billing_id:                {billing_id!r}")
    print(f"billing_type:              {billing_type!r}")
    print(f"billing_subscription_id:   {billing_subscription_id!r}")
    print(f"=> payment method on file: {has_payment}")

    if has_payment:
        print(
            "\nSTOP: a billing_id / billing_type / billing_subscription_id is present, "
            "meaning a payment method appears to be on file. Refusing to proceed."
        )
        return False

    if inbox_limit is not None and inbox_limit > 5:
        print(
            f"\nSTOP: inbox_limit ({inbox_limit}) is higher than expected for Free tier. "
            "Refusing to proceed."
        )
        return False

    print(
        "\nOK: no payment method on file and limits look consistent with Free tier. "
        "Safe to proceed, staying within 3 inboxes total / well under 3,000 emails/month."
    )
    return True


if __name__ == "__main__":
    ok = check()
    raise SystemExit(0 if ok else 1)
