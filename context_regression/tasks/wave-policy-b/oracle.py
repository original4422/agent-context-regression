def job(id, cost=1, priority=0, needs=None, manual=False, approved=False):
    return dict(id=id, needs=needs or [], priority=priority, cost=cost, manual=manual, approved=approved)


CHECKS = {
    "dependency_policy": lambda m: m.select_plan([job("base", priority=9), job("app", priority=8, needs=["base"])], [], 2) == ['base', 'app'] and m.select_plan([job("base", priority=9), job("app", priority=8, needs=["base"]), job("web", priority=7, needs=["app"])], [], 3) == ['base', 'app', 'web'],
    "no_revisit": lambda m: m.select_plan([job("app", priority=9, needs=["base"]), job("base", priority=8)], [], 2) == ["base"],
    "blocked_prerequisite": lambda m: m.select_plan([job("base", priority=9, manual=True), job("app", priority=8, needs=["base"])], [], 3) == [],
    "unknown_dependency": lambda m: m.select_plan([job("app", needs=["missing"])], [], 2) == [],
    "all_dependencies_required": lambda m: m.select_plan([job("app", needs=["ready", "missing"])], ["ready"], 2) == [],
    "previously_completed": lambda m: m.select_plan([job("app", needs=["base"])], ["base"], 1) == ["app"],
    "manual_gate": lambda m: m.select_plan([job("blocked", manual=True), job("ready", manual=True, approved=True), job("auto")], [], 3) == ["ready", "auto"],
    "stable_priority_budget": lambda m: m.select_plan([job("z", priority=5), job("a", priority=5), job("high", priority=9)], [], 2) == ["high", "z"],
    "skip_and_exact_fit": lambda m: m.select_plan([job("large", cost=4, priority=9), job("exact", cost=2, priority=8), job("free", cost=0)], [], 2) == ["exact", "free"],
    "empty": lambda m: m.select_plan([], [], 0) == [],
}
