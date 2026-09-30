import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics

from .runner import STRATEGIES, run_batch
from .tasks import BUILTIN_TASKS, tasks_in


def summarize(report):
    lines = ["# Context regression results", "", report["scope"], "",
             f"Batch: **{report['status']}**; {len(report['rows'])}/{report['planned_runs']} attempted.", "",
             "| Strategy | Passed / attempted | Regression rows | Total tokens¹ | Median end-to-end seconds² |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for strategy in STRATEGIES:
        rows = [r for r in report["rows"] if r["strategy"] == strategy]
        passed = sum(r.get("verification", {}).get("passed", False) for r in rows)
        regressions = sum(bool(r.get("regressions")) for r in rows)
        tokens = sum(r["total"]["usage"]["input_tokens"] + r["total"]["usage"]["output_tokens"] for r in rows if r["total"]["usage"] is not None)
        complete = all(r["total"]["usage"] is not None for r in rows)
        median = f"{statistics.median(r['wall_seconds'] for r in rows):.2f}" if rows else "—"
        lines.append(f"| {strategy} | {passed}/{len(rows)} | {regressions} | {tokens if complete and rows else 'incomplete'} | {median} |")
    lines += ["", "¹ Input + output tokens; summary generation is included. Cached input is a subset of input, not an extra charge. These are CLI-reported tokens, not dollars or subscription quota units.",
              "", "² Includes summary generation, continuation, and independent verification. All attempted rows remain in the report; aborted batches are not complete comparisons.",
              "", "## Per-task outcomes", "", "| Task | Repeat | Strategy | Passed | Failed checks |", "| --- | ---: | --- | --- | --- |"]
    for row in report["rows"]:
        verification = row.get("verification", {})
        failed = ", ".join(c["name"] for c in verification.get("checks", []) if not c["passed"])
        lines.append(f"| {row['task']} | {row['repeat']} | {row['strategy']} | {verification.get('passed', row['status'])} | {failed} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Executable checks for coding tasks after controlled context compression")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="List built-in or external tasks")
    listing.add_argument("--tasks", type=Path, default=BUILTIN_TASKS)
    run = commands.add_parser("run", help="Run a serial, seeded comparison using the existing Codex login")
    run.add_argument("--tasks", type=Path, default=BUILTIN_TASKS)
    run.add_argument("--task", action="append", help="Select a task id; repeat to select more")
    run.add_argument("--model", required=True, help="Explicit Codex model; held fixed for both phases")
    run.add_argument("--effort", choices=["low", "medium", "high"], default="low")
    run.add_argument("--repetitions", type=int, default=2)
    run.add_argument("--seed", type=int, default=20260930)
    run.add_argument("--recent-turns", type=int, default=1)
    run.add_argument("--summary-chars", type=int, default=4096)
    run.add_argument("--timeout", type=int, default=180, help="Continuation wall-clock seconds per attempt")
    run.add_argument("--summary-timeout", type=int, default=90)
    run.add_argument("--max-tools", type=int, default=16)
    run.add_argument("--codex", default="codex")
    run.add_argument("--private-dir", type=Path, help="New private results directory; must not exist")
    summary = commands.add_parser("summarize", help="Create a report from the machine-readable results")
    summary.add_argument("results", type=Path)
    args = parser.parse_args()
    if args.command == "summarize":
        print(summarize(json.loads(args.results.read_text())), end="")
        return
    tasks = tasks_in(args.tasks)
    if not tasks:
        parser.error("No tasks found")
    if args.command == "list":
        for task in tasks:
            print(f"{task['spec']['id']}: {task['spec']['title']}")
        return
    if args.task:
        unknown = set(args.task) - {task["spec"]["id"] for task in tasks}
        if unknown:
            parser.error(f"Unknown tasks: {', '.join(sorted(unknown))}")
        tasks = [task for task in tasks if task["spec"]["id"] in args.task]
    for key in ("repetitions", "recent_turns", "summary_chars", "timeout", "summary_timeout", "max_tools"):
        if getattr(args, key) < 1:
            parser.error(f"{key} must be positive")
    config = {key: getattr(args, key) for key in ("model", "effort", "repetitions", "seed", "recent_turns", "summary_chars", "timeout", "summary_timeout", "max_tools", "codex")}
    private = args.private_dir or Path.home() / ".local/state/agent-context-regression" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    print(f"Private traces and results: {private}", flush=True)
    report = run_batch(tasks, config, private)
    print(summarize(report))
