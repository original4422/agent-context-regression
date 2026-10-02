def job(id, cost, priority=0):
    return dict(id=id, needs=[], priority=priority, cost=cost, manual=False, approved=False)


CHECKS = {
    "shared_budget": lambda m: m.select_batch([job("api", 3), job("worker", 3)], [], 3) == ["api"],
    "priority": lambda m: m.select_batch([job("low", 1, 0), job("high", 1, 5)], [], 2) == ["high", "low"],
    "empty_batch": lambda m: m.select_batch([], [], 0) == [],
}
