def select_plan(jobs, completed, capacity):
    """Return an ordered list of selected release job ids; selection is pending.

    jobs: list of {id: str, needs: list[str], priority: int, cost: int,
                   manual: bool, approved: bool}; ids are unique, costs >= 0.
    completed: list[str] of successful deployment ids before this call.
    capacity: nonnegative integer resource units available for this plan.
    Inputs are schema-valid JSON values. Do not mutate them.
    """
    return []
