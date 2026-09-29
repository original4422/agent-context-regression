"""Reference implementations used only to validate task definitions offline."""

SOLUTIONS = {
    "rollout-dependency-admission": '''def select_batch(jobs, completed, capacity):
    completed = set(completed)
    selected = []
    for job in sorted(jobs, key=lambda job: -job["priority"]):
        if job["manual"] and not job["approved"]:
            continue
        if not set(job["needs"]) <= completed:
            continue
        if job["cost"] > capacity:
            continue
        selected.append(job["id"])
        capacity -= job["cost"]
    return selected
''',
    "scoped-policy-precedence": '''def authorize(rules, subject, resource, action, now):
    decision = "deny"
    for rule in rules:
        if rule["tenant"] not in ("*", subject["tenant"]):
            continue
        if rule["resource"] not in ("*", resource) or rule["action"] not in ("*", action):
            continue
        if "*" not in rule["roles"] and not set(rule["roles"]) & set(subject["roles"]):
            continue
        if rule["start"] is not None and now < rule["start"]:
            continue
        if rule["end"] is not None and now >= rule["end"]:
            continue
        if rule["effect"] == "deny":
            return "deny"
        decision = "allow"
    return decision
''',
}

# Each mutant models one tempting implementation that violates a recorded rule.
MUTATIONS = {
    "rollout-dependency-admission": [
        ("selected_is_completed", 'selected.append(job["id"])', 'selected.append(job["id"]); completed.add(job["id"])', "completed_before_batch"),
        ("approval_bypasses_dependencies", 'if not set(job["needs"]) <= completed:', 'if not job["approved"] and not set(job["needs"]) <= completed:', "approval_does_not_bypass_dependencies"),
        ("alphabetical_ties", 'key=lambda job: -job["priority"]', 'key=lambda job: (-job["priority"], job["id"])', "stable_priority_ties"),
        ("stop_on_oversize", 'if job["cost"] > capacity:\n            continue', 'if job["cost"] > capacity:\n            break', "skip_oversized_without_stopping"),
        ("any_dependency", 'if not set(job["needs"]) <= completed:', 'if job["needs"] and not set(job["needs"]) & completed:', "all_dependencies_required"),
        ("reject_exact_fit", 'if job["cost"] > capacity:', 'if job["cost"] >= capacity:', "zero_capacity_zero_cost"),
    ],
    "scoped-policy-precedence": [
        ("first_matching_effect", 'decision = "allow"', 'return "allow"', "deny_overrides_specific_allow"),
        ("unscoped_deny", 'if rule["tenant"] not in ("*", subject["tenant"]):', 'if rule["effect"] != "deny" and rule["tenant"] not in ("*", subject["tenant"]):', "tenant_isolation"),
        ("empty_roles_wildcard", 'if "*" not in rule["roles"] and not set(rule["roles"]) & set(subject["roles"]):', 'if rule["roles"] and "*" not in rule["roles"] and not set(rule["roles"]) & set(subject["roles"]):', "empty_roles_match_nobody"),
        ("inclusive_end", 'now >= rule["end"]', 'now > rule["end"]', "half_open_validity"),
        ("truthy_timestamps", 'rule["end"] is not None', 'rule["end"]', "zero_is_a_timestamp"),
        ("deny_before_validity", 'if rule["start"] is not None', 'if rule["effect"] == "deny":\n            return "deny"\n        if rule["start"] is not None', "inactive_deny_does_not_override"),
    ],
}
