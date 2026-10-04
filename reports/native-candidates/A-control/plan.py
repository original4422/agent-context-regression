def _dependencies_satisfied(needs, completed, selected):
    """Only deployments completed before this call satisfy prerequisites."""
    return all(need in completed for need in needs)


def select_plan(jobs, completed, capacity):
    """Return selected release job ids without changing any input.

    jobs: list of {id: str, needs: list[str], priority: int, cost: int,
                   manual: bool, approved: bool}; ids are unique, costs >= 0.
    completed: list[str] of successful deployment ids before this call.
    capacity: nonnegative integer resource units available for this plan.
    Inputs are schema-valid JSON values.

    Shared contract, already implemented below:
    * Scan once in descending priority, preserving input order for ties.
    * Never revisit a skipped job, even if a later selection changes readiness.
    * Manual jobs need approved=True; automatic jobs need no approval.
    * All prerequisites must satisfy the earlier chosen dependency policy.
      Unknown prerequisites block admission; approval bypasses no other gate.
    * Use one remaining capacity budget, subtracting each admitted job's cost.
    * Skip oversized jobs and continue; exact fits and zero-cost jobs are valid,
      including zero-cost jobs at capacity zero. Do not optimize a knapsack.
    * Return admission order. No deployment execution or input mutation.

    Only _dependencies_satisfied remains to be implemented from the history.
    """
    completed = set(completed)
    selected = []
    for job in sorted(jobs, key=lambda job: -job["priority"]):
        if job["manual"] and not job["approved"]:
            continue
        if not _dependencies_satisfied(job["needs"], completed, selected):
            continue
        if job["cost"] > capacity:
            continue
        selected.append(job["id"])
        capacity -= job["cost"]
    return selected
