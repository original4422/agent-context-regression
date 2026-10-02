def select_batch(jobs, completed, capacity):
    """Return selected string ids; policy gates are pending.

    jobs: list of {id: str, needs: list[str], priority: int, cost: int,
                   manual: bool, approved: bool}; ids are unique, cost >= 0.
    completed: list[str] of successful deployment ids before this call.
    capacity: nonnegative integer resource units available for this batch.
    """
    return [job["id"] for job in sorted(jobs, key=lambda job: -job["priority"])]
