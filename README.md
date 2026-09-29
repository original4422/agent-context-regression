# Agent Context Regression

Does a coding agent still produce the correct change after its context is shortened?

This CLI resumes small coding tasks from fixed source checkpoints under three context strategies. Independent executable checks evaluate the resulting code. It measures corrected requirements that were lost, task success, total tokens, and elapsed time—including automatic summary generation.

The built-in suite contains **six hand-authored Python tasks with reconstructed conversations**: four microtasks and two software-policy checkpoints. It tests controlled context reconstruction, not Codex's native compaction or production conversation memory.

## Measured pilot

Codex CLI 0.155.1, `gpt-6-sol`, low reasoning, two repetitions per task:

| Strategy | Tasks passed | Input + output tokens, including summary | Median end-to-end time |
| --- | ---: | ---: | ---: |
| Full history | 8/8 | 780,797 | 26.41 s |
| Recent user turn | 2/8 | 768,542 | 30.10 s |
| Automatic structured summary | 8/8 | 899,098 | 43.87 s |

On these short histories, the automatic summary preserved correctness but **increased total tokens and latency**. Truncation lost casing, window-boundary and retry-policy requirements; both truncation runs passed the configuration task. One slug failure concerned separator handling rather than the designated corrected requirement.

[Full results and accounting](reports/README.md) include all 24 continuations, all 8 summary generations, input/cached-input/output breakdowns, and the initial aborted integration batch. All 24 saved candidates were subsequently [rechecked with process-isolated verification](reports/isolated-verifier-recheck.json), with identical outcomes. The timing table records the original runner. The 28 deterministic tests cover candidate outcomes, process isolation, usage accounting, failure handling and sandbox protection of acceptance files.

## Run

Requires Python 3.11+, a logged-in Codex CLI supporting `exec --ignore-user-config`, and its working OS sandbox. The measured platform is macOS; Linux execution has not been measured. Python code uses only the standard library.

```sh
git clone https://github.com/original4422/agent-context-regression.git
cd agent-context-regression
python3 -m context_regression list
python3 -m unittest discover -s tests -v

# Existing Codex login; no separate model API key is used.
# Choose a model available to your account; it is held fixed for all phases.
python3 -m context_regression run --model gpt-6-sol
```

Defaults run 6 tasks × 3 strategies × 2 repetitions: **36 continuations plus 12 summary generations**, serially. Each continuation has a 180-second timeout and 16-tool-call budget; each summary has 90 seconds and a 4,096-character limit. Infrastructure failures abort the batch; failed code checks remain valid outcomes and do not stop it.

The CLI prints a private result directory under `~/.local/state/agent-context-regression/`. Raw prompts, events, summaries and candidate files stay there, behind a mode-0700 directory. To render the metrics:

```sh
python3 -m context_regression summarize /path/from/run/results.json

# Optional installation provides the equivalent `acr` command.
python3 -m pip install .
acr list
```

## Comparison

| Strategy | Retained context | Extra model phase |
| --- | --- | --- |
| `full` | All supplied messages | None |
| `recent` | Most recent user turn and its assistant/tool messages | None |
| `structured` | Automatically generated objective, constraints, rejected approaches, observations and next steps | Same model and effort as continuation |

The current request is identical across strategies. Each attempt starts from a fresh copy of the same source snapshot. A seeded schedule shuffles task/repetition groups and rotates/reverses strategy order within groups. The schedule, task fingerprints, runner fingerprint, model, effort and budgets are saved with the results.

The agent has four MCP tools: list files, read a listed file, replace a listed file, and run public smoke checks. Native shell and web search are disabled. This is a constrained coding loop: the agent edits and executes actual Python code, with the same capabilities in every arm.

Public checks are deliberately incomplete. Acceptance scripts stay outside the candidate workspace and execute in the trusted verifier process. Each candidate function call runs in a fresh Python process under Codex's read-only OS sandbox. The verifier sends JSON arguments, receives JSON values, and computes every pass/fail decision itself; acceptance functions and verdict memory never enter the candidate process. Input mutations, candidate exceptions, `SystemExit`, hard exits and malformed replies produce failed checks. A worker that cannot start is a harness error and aborts the batch.

The file tools and sandbox prevent candidates from rewriting acceptance scripts; task fingerprints are also checked before and after each attempt. Regression tests reproduce attempted file overwrites, stack-based check replacement and abrupt candidate termination. Filesystem read access follows Codex's sandbox policy; test secrecy is not part of this adapter's contract.

## Tasks and outcomes

| Task | Pending work | Earlier requirement checked independently |
| --- | --- | --- |
| Case-sensitive slugs | Normalize punctuation | Preserve existing URL casing |
| Explicit empty overrides | Implement `None` inheritance | Keep empty strings, `0` and `False` |
| Retry method policy | Add rate-limit retries and finish policy | Respect the exact method allowlist |
| Event window order | Add deduplication and finish window selection | Exclude the right endpoint; keep ingestion order |
| Rollout dependency admission | Finish shared capacity budget | Completed-before-batch dependencies, approval scope, stable priority, skip-and-continue |
| Scoped policy precedence | Finish expiration support | Tenant boundaries, deny precedence, empty roles, half-open validity |

[Software-policy protocol](reports/software-policy.md) distinguishes the final incremental request from earlier corrections and documents the counterexamples used to validate acceptance checks.

Acceptance checks return named booleans. A task passes only when every check passes. `regressions` lists failures of designated corrected requirements; it reports observable behavior, not an inference about the model's internal memory. No LLM judge is used.

Token totals include summary and continuation phases. Cached input is reported separately as a **subset** of input tokens. Token counts are not dollar costs or subscription quota units. End-to-end wall time includes independent verification. Missing usage stays missing; an aborted batch is not presented as a complete comparison.

## Add a task

Pass `--tasks /path/to/tasks` to `list` or `run`. Each child directory contains:

```text
my-task/
  task.json        # id, title, module, editable, request, regression_checks, provenance
  history.json     # [{"role": "user|assistant|tool", "content": "..."}, ...]
  snapshot/        # initial candidate files; never contains acceptance tests
  public.py        # CHECKS: dict[str, callable(candidate_module) -> bool]
  oracle.py        # same interface; independent acceptance checks
```

Copy a [built-in task](context_regression/tasks/explicit-empty-overrides) for the exact schema. Use trusted Python check scripts; task definitions are executable code. `candidate_module` is a proxy for **pure functions with JSON-compatible arguments and return values**: strings, numbers, booleans, null, lists and dictionaries with string keys. Every call imports a fresh candidate module, and changed arguments fail verification. Module state, Python object identity and non-JSON return types are outside this adapter. The agent can edit only files listed in `editable`. Changing strategy logic is a small edit to `runner.py`; adding general agent/provider adapters is outside this first version.

Useful controls:

```sh
acr run --model gpt-6-sol --task retry-method-policy --repetitions 1
acr run --model gpt-6-sol --recent-turns 2 --seed 42 --effort medium
```

The microtasks intentionally contain requirements that are easy to lose. Results describe the selected tasks and this constrained tool surface. The historical four-task pilot and the two-task software-policy extension are separate batches, each with two repetitions; neither establishes a general ranking of compression methods.

## Related work and attribution

[CompactBench](https://github.com/compactbench/compactbench) evaluates compaction through probes and multi-cycle drift. [Hermes compression eval](https://github.com/NousResearch/hermes-compression-eval) evaluates continuation probes using LLM grading. [LongMemEval-V2](https://github.com/xiaowu0162/LongMemEval-V2) evaluates memory over agent trajectories. This project focuses on executable code outcomes at fixed intermediate checkpoints.

The runner, task fixtures and checks in this repository are original work. Codex CLI and the Model Context Protocol are external interfaces; their implementations are not vendored. MIT © 2026 Daniel Peng (original4422).
