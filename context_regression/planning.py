"""Task selection and the read-only presentation of the runner's schedule."""
from .tasks import BUILTIN_TASKS, tasks_in

SUITES = {
    "micro": ("case-sensitive-slugs", "event-window-order", "explicit-empty-overrides", "retry-method-policy"),
    "software-policy": ("rollout-dependency-admission", "scoped-policy-precedence"),
    "paired": ("wave-policy-a", "wave-policy-b"),
    "visible-policy": ("visible-policy-a", "visible-policy-b"),
}
SUITE_NAMES = (*SUITES, "all")


def select_tasks(root, suite=None, ids=None, repetitions=None):
    tasks = tasks_in(root)
    if not tasks:
        raise ValueError("No tasks found")
    if suite and root.resolve() != BUILTIN_TASKS.resolve():
        raise ValueError("Named suites select built-in tasks; use --task with an external --tasks directory")
    quickstart = not suite and not ids and root.resolve() == BUILTIN_TASKS.resolve()
    if quickstart:
        wanted = SUITES["visible-policy"]
        selection = "quickstart (visible-policy, one repetition by default)"
    elif suite:
        wanted = SUITES[suite] if suite != "all" else None
        selection = suite
    else:
        wanted = ids
        selection = "explicit tasks" if ids else "external task directory"
    if wanted:
        unknown = set(wanted) - {task["spec"]["id"] for task in tasks}
        if unknown:
            raise ValueError(f"Unknown tasks: {', '.join(sorted(unknown))}")
        tasks = [task for task in tasks if task["spec"]["id"] in wanted]
    return tasks, repetitions if repetitions is not None else (1 if quickstart else 2), selection


def describe_plan(plan, config, selection):
    lines = [f"Selection: {selection}", "Tasks: " + ", ".join(plan["task_ids"]),
             "Strategies: " + ", ".join(plan["strategies"]),
             f"Repetitions per task/strategy: {config['repetitions']}",
             f"Model: {config['model'] or '(choose with --model before running)'}; effort: {config['effort']}; seed: {config['seed']}",
             f"Requests: {plan['continuations']} continuations + {plan['summaries']} summaries = {plan['continuations'] + plan['summaries']} model phases",
             f"Continuation timeout: {config['timeout']} s; tool-call budget: {config['max_tools']}",
             f"Summary timeout: {config['summary_timeout']} s; character limit: {config['summary_chars']}",
             f"Independent verification timeout: {plan['verification_timeout']} s per continuation",
             f"Configured model-phase timeout budget: {plan['model_timeout_budget']} s",
             f"Configured model + verification timeout budget: {plan['phase_timeout_budget']} s",
             "These are sums of configured phase limits, not elapsed-time or token estimates; process setup/cleanup is additional.",
             "Order:"]
    lines.extend(f"  {index}. {task['spec']['id']} / {strategy} / repetition {repeat + 1}"
                 for index, (task, repeat, strategy) in enumerate(plan["runs"], 1))
    return "\n".join(lines)
