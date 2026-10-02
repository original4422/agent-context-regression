SUBJECT = {"tenant": "acme", "roles": ["reader"]}


def grant(end):
    return dict(tenant="acme", roles=["reader"], resource="report", action="read", effect="allow", start=None, end=end)


CHECKS = {
    "active_grant": lambda m: m.authorize([grant(20)], SUBJECT, "report", "read", 10) == "allow",
    "expired_grant": lambda m: m.authorize([grant(20)], SUBJECT, "report", "read", 21) == "deny",
    "default_deny": lambda m: m.authorize([], SUBJECT, "report", "read", 10) == "deny",
}
