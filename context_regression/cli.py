import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics

from .runner import STRATEGIES, execution_plan, run_batch
from .planning import SUITE_NAMES, describe_plan, select_tasks
from .native import native_plan
from .native_preflight import preflight
from .doctor import format_doctor, inspect_environment
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


def add_run_options(command):
    command.add_argument("--tasks", type=Path, default=BUILTIN_TASKS)
    selection = command.add_mutually_exclusive_group()
    selection.add_argument("--suite", choices=SUITE_NAMES, help="Select a named built-in suite")
    selection.add_argument("--task", action="append", help="Select a task id; repeat to select more")
    command.add_argument("--model", help="Required for execution; held fixed for both phases")
    command.add_argument("--effort", choices=["low", "medium", "high"], default="low")
    command.add_argument("--repetitions", type=int, help="Default: 1 for implicit quickstart; 2 for explicit selections")
    command.add_argument("--seed", type=int, default=20260930)
    command.add_argument("--recent-turns", type=int, default=1)
    command.add_argument("--summary-chars", type=int, default=4096)
    command.add_argument("--timeout", type=int, default=180, help="Continuation wall-clock seconds per attempt")
    command.add_argument("--summary-timeout", type=int, default=90)
    command.add_argument("--max-tools", type=int, default=16)
    command.add_argument("--codex", default="codex")
    command.add_argument("--private-dir", type=Path, help="New private result directory; previews never create it")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Executable checks for coding tasks after controlled context compression")
    commands = parser.add_subparsers(dest="command", required=True)
    native = commands.add_parser("native-plan", help="Offline native-compaction protocol preparation; no model execution")
    native.add_argument("--model")
    native.add_argument("--effort", choices=["low", "medium", "high"], default="low")
    native_check = commands.add_parser("native-preflight", help="Validate real app-server/MCP isolation without model requests")
    native_check.add_argument("--codex", default="codex")
    native_check.add_argument("--private-dir", type=Path)
    listing = commands.add_parser("list", help="List built-in or external tasks")
    listing.add_argument("--tasks", type=Path, default=BUILTIN_TASKS)
    listing.add_argument("--suite", choices=SUITE_NAMES)
    plan = commands.add_parser("plan", help="Preview the exact task schedule without Codex or result directories")
    add_run_options(plan)
    run = commands.add_parser("run", help="Run a serial comparison; defaults to the 6+2 quickstart")
    add_run_options(run)
    run.add_argument("--dry-run", action="store_true", help="Print the same offline preview as plan")
    doctor = commands.add_parser("doctor", help="Check local prerequisites without a model request")
    doctor.add_argument("--codex", default="codex")
    summary = commands.add_parser("summarize", help="Create a report from the machine-readable results")
    summary.add_argument("results", type=Path)
    args = parser.parse_args(argv)
    if args.command == "native-preflight":
        private = args.private_dir or Path.home() / ".local/state/agent-context-regression" / ("native-preflight-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ"))
        report = preflight(private, args.codex)
        print(json.dumps(report, indent=2))
        raise SystemExit(0 if report["status"] == "completed" else 1)
    if args.command == "native-plan":
        print(json.dumps(native_plan(args.model, args.effort), indent=2))
        return
    if args.command == "summarize":
        print(summarize(json.loads(args.results.read_text())), end="")
        return
    if args.command == "doctor":
        report = inspect_environment(args.codex)
        print(format_doctor(report))
        raise SystemExit(0 if report["ready"] else 1)
    if args.command == "list":
        try:
            tasks = select_tasks(args.tasks, args.suite)[0] if args.suite else tasks_in(args.tasks)
        except ValueError as error:
            parser.error(str(error))
        if not tasks:
            parser.error("No tasks found")
        for task in tasks:
            print(f"{task['spec']['id']}: {task['spec']['title']}")
        return
    try:
        tasks, args.repetitions, selection = select_tasks(args.tasks, args.suite, args.task, args.repetitions)
    except ValueError as error:
        parser.error(str(error))
    for key in ("repetitions", "recent_turns", "summary_chars", "summary_timeout", "timeout", "max_tools"):
        if getattr(args, key) < 1:
            parser.error(f"{key} must be positive")
    preview = args.command == "plan" or args.dry_run
    if not preview and not args.model:
        parser.error("run requires --model; use plan or run --dry-run for an offline preview")
    config = {key: getattr(args, key) for key in ("model", "effort", "repetitions", "seed", "recent_turns", "summary_chars", "summary_timeout", "timeout", "max_tools", "codex")}
    print(describe_plan(execution_plan(tasks, config), config, selection))
    if preview:
        return
    private = args.private_dir or Path.home() / ".local/state/agent-context-regression" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    print(f"Private traces and results: {private}", flush=True)
    report = run_batch(tasks, config, private)
    print(summarize(report))
