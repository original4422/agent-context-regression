def authorize(rules, subject, resource, action, now):
    """Return "allow" or "deny"; policy gates are pending.

    rules: list of {tenant: str, roles: list[str], resource: str, action: str,
                    effect: "allow"|"deny", start: int|None, end: int|None}.
    subject: {tenant: str, roles: list[str]}; resource/action are strings.
    now is an integer timestamp. Inputs are schema-valid JSON values.
    """
    return "allow" if any(rule["effect"] == "allow"
                          and rule["resource"] in ("*", resource)
                          and rule["action"] in ("*", action)
                          for rule in rules) else "deny"
