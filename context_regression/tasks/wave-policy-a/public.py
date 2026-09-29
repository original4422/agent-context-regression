def job(id, cost=1, priority=0, needs=None):
    return dict(id=id, needs=needs or [], priority=priority, cost=cost, manual=False, approved=False)


CHECKS = {
    "shared_capacity": lambda m: m.select_plan([job("first", 2), job("second", 2)], [], 2) == ["first"],
    "priority_order": lambda m: m.select_plan([job("low", priority=0), job("high", priority=9)], [], 2) == ["high", "low"],
    "previously_completed": lambda m: m.select_plan([job("app", needs=["base"])], ["base"], 1) == ["app"],
}
