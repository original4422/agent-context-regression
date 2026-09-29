SUBJECT = {"tenant": "acme", "roles": ["reader", "auditor"]}


def rule(effect="allow", tenant="acme", roles=None, resource="report", action="read", start=None, end=None):
    return dict(tenant=tenant, roles=["reader"] if roles is None else roles, resource=resource, action=action, effect=effect, start=start, end=end)


def auth(m, rules, now=10, subject=SUBJECT, resource="report", action="read"):
    return m.authorize(rules, subject, resource, action, now)


CHECKS = {
    "deny_overrides_specific_allow": lambda m: auth(m, [rule("deny", resource="*"), rule()]) == "deny" and auth(m, [rule(), rule("deny", resource="*")]) == "deny",
    "tenant_isolation": lambda m: auth(m, [rule(tenant="other")]) == "deny" and auth(m, [rule(), rule("deny", tenant="other")]) == "allow",
    "empty_roles_match_nobody": lambda m: auth(m, [rule(roles=[])]) == "deny" and auth(m, [rule(), rule("deny", roles=[])]) == "allow",
    "role_intersection_and_wildcard": lambda m: auth(m, [rule(roles=["editor", "auditor"])]) == "allow" and auth(m, [rule(roles=["*"])], subject={"tenant":"acme", "roles":[]}) == "allow" and auth(m, [rule(roles=["editor"])]) == "deny",
    "half_open_validity": lambda m: auth(m, [rule(start=10, end=20)], 10) == "allow" and auth(m, [rule(start=10, end=20)], 20) == "deny" and auth(m, [rule(start=10, end=20)], 9) == "deny",
    "zero_is_a_timestamp": lambda m: auth(m, [rule(end=0)], 0) == "deny" and auth(m, [rule(start=0)], -1) == "deny",
    "inactive_deny_does_not_override": lambda m: auth(m, [rule(), rule("deny", end=10)]) == "allow" and auth(m, [rule(), rule("deny", start=11)]) == "allow",
    "wildcard_scope": lambda m: auth(m, [rule(tenant="*", resource="*", action="*", roles=["*"])], subject={"tenant":"other", "roles":[]}, resource="invoice", action="write") == "allow",
    "exact_case_and_action": lambda m: auth(m, [rule(tenant="ACME")]) == "deny" and auth(m, [rule()], action="write") == "deny" and auth(m, [rule(resource="Report")]) == "deny",
    "default_deny": lambda m: auth(m, []) == "deny",
}
