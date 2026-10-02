def job(id, cost=1, priority=0, needs=None, manual=False, approved=False):
    return dict(id=id, needs=needs or [], priority=priority, cost=cost, manual=manual, approved=approved)


CHECKS = {
    "shared_budget": lambda m: m.select_batch([job("api", 3), job("worker", 3)], [], 3) == ["api"],
    "completed_before_batch": lambda m: m.select_batch([job("base", priority=5), job("app", needs=["base"])], [], 2) == ["base"],
    "all_dependencies_required": lambda m: m.select_batch([job("app", needs=["base", "unknown"])], ["base"], 5) == [],
    "approval_does_not_bypass_dependencies": lambda m: m.select_batch([job("app", needs=["base"], manual=True, approved=True)], [], 5) == [],
    "manual_gate": lambda m: m.select_batch([job("blocked", manual=True), job("approved", manual=True, approved=True), job("automatic")], [], 5) == ["approved", "automatic"],
    "stable_priority_ties": lambda m: m.select_batch([job("z", priority=7), job("a", priority=7), job("urgent", priority=9)], [], 3) == ["urgent", "z", "a"],
    "skip_oversized_without_stopping": lambda m: m.select_batch([job("large", 6, 9), job("exact", 3, 5), job("small", 1, 1)], [], 4) == ["exact", "small"],
    "zero_capacity_zero_cost": lambda m: m.select_batch([job("paid", 1, 9), job("free", 0)], [], 0) == ["free"],
    "combined_gates_and_budget": lambda m: m.select_batch([job("manual", 0, 10, manual=True), job("ready", 2, 8, ["base"]), job("chained", 0, 7, ["ready"]), job("tail", 1, 1)], ["base"], 3) == ["ready", "tail"],
    "empty_batch": lambda m: m.select_batch([], [], 0) == [],
}
