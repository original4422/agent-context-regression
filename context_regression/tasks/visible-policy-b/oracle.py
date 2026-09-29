from context_regression.release_checks import SHARED_CHECKS, job


CHECKS = {
    **SHARED_CHECKS,
    "dependency_policy": lambda m: m.select_plan([job("base", priority=9), job("app", priority=8, needs=["base"])], [], 2) == ['base', 'app'] and m.select_plan([job("base", priority=9), job("app", priority=8, needs=["base"]), job("web", priority=7, needs=["app"])], [], 3) == ['base', 'app', 'web'],
}
