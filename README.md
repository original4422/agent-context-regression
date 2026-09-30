# Agent Context Regression

Does a coding agent still produce the correct change after its context is shortened?

This CLI resumes small coding tasks from fixed source checkpoints under three context strategies. Independent executable checks evaluate the resulting code. It measures corrected requirements that were lost, task success, total tokens, and elapsed time—including automatic summary generation.

The built-in suite contains **ten hand-authored Python tasks with reconstructed conversations**: four microtasks, two software-policy checkpoints and two counterfactual policy pairs. It tests controlled context reconstruction, not Codex's native compaction or production conversation memory.

## Try it without a model

Python 3.11+ is enough to inspect a run. The package uses only the standard library.

```sh
git clone https://github.com/original4422/agent-context-regression.git
cd agent-context-regression
python3 -B -m context_regression plan
```

The preview lists the exact task ids, seeded execution order, strategies, repetitions, phase counts and configured limits. The default is the visible-contract A/B pair, one repetition: **6 continuations + 2 summaries**. It does not need Codex, login or a model name, and creates no result directory. `run --dry-run` produces the same preview.

```sh
python3 -B -m context_regression plan --suite micro
python3 -B -m context_regression run --dry-run --suite all
python3 -B -m context_regression list --suite visible-policy
```

## Native compaction smoke

A separate [real native smoke](reports/native-smoke.md) completed **2 real seed turns, 2 native compactions and 4 continuations** on Codex CLI 0.155.1 with `gpt-6-astra`/low. Both short A/B histories preserved the requested policy after compaction; all four control/native candidates passed their target external oracle and failed the opposite policy. Each native stage had a matching completed `contextCompaction` item and successful turn terminal. Usage remains null/incomplete.

`acr native-plan --model gpt-6-astra --effort low` previews the protocol; its model options affect only the plan. `acr native-run --allow-model` executes the fixed `gpt-6-astra`/low batch. `acr native-preflight` checks real configuration and the four-tool MCP connection without model turns. The [protocol](docs/native-compaction.md) covers boundaries, scoped approvals, cancellation and evidence. The [first setup failure](reports/native-smoke-initial.md), [no-model cwd repair probe](reports/native-reset-probe.json), and successful batch are separate records. The existing quickstart below remains the reconstructed-context experiment.

The four actual candidate files are now [public with an offline recheck](reports/native-candidates/README.md). With Python 3.11+, run `python3 -B scripts/recheck_native_candidates.py` to recompute all eight oracle verdicts without Codex, credentials or network. The script verifies frozen input hashes before execution and compares every check to the unchanged historical result. This rechecks candidate behavior using Python subprocesses; it does not repeat native compaction or its timings.

四份真实候选已按原字节公开。上述命令仅需 Python 3.11+，会先核对候选、任务和验证器 hash，再独立重算 8 份 oracle 判定并逐项比较；详见[中文复核说明](reports/native-candidates/README.md#中文说明)。原始日志与真实 rollout 身份仍保留私有。

The separate [user-policy revision batch](reports/native-revision.md) completed A→B and B→A using two real prelude turns per direction, then forking at the correction boundary. All four control/native candidates followed the latest policy and passed the shared rules. Recheck their published code with `python3 -B scripts/recheck_native_candidates.py --scenario policy-revision`. The [protocol](docs/native-policy-revision.md) and default fixed-policy scenario remain distinct; usage is null/incomplete.

## Check readiness and run

```sh
# No model request: checks Python, CLI flags, existing login and read-only sandbox.
python3 -B -m context_regression doctor

# Uses your existing Codex login. Choose a model available to your account.
python3 -B -m context_regression run --model gpt-6-sol
```

`doctor` runs `codex --version`, `codex exec --help`, `codex login status`, and a temporary sandbox probe that verifies reading succeeds while writing is blocked. It does not install anything, log in, modify global configuration or invoke a model. Exit **0** means local prerequisites are ready; **1** means a check is not ready; CLI argument errors use **2**. Model availability and the complete MCP interaction are exercised by `run`. The real doctor passed on macOS 15.7.8 / Python 3.14.7 / Codex CLI 0.155.1; Linux model execution has not been measured.

The run prints the same plan before starting. Each continuation has a 180-second timeout and 16-tool-call budget; each summary has 90 seconds and a 4,096-character limit. The quickstart's configured model-phase timeout budget totals 1,260 seconds, plus independent verification limits. These sums describe phase limits, not expected running time or token usage; process startup and cleanup are additional. Infrastructure failures abort the batch; failed code checks remain valid outcomes.

Raw prompts, events, summaries and candidates stay in the printed private directory under `~/.local/state/agent-context-regression/`, with mode 0700. To render its metrics:

```sh
python3 -B -m context_regression summarize /path/from/run/results.json

# Optional installation provides the same commands through acr.
python3 -m pip install .
acr plan
```

## Select a comparison

| Selection | Tasks | Default repetitions | Continuations + summaries |
| --- | ---: | ---: | ---: |
| No selector: quickstart | Visible-contract pair | 1 | 6 + 2 |
| `--suite micro` | Original four microtasks | 2 | 24 + 8 |
| `--suite software-policy` | Two software-policy tasks | 2 | 12 + 4 |
| `--suite paired` | First counterfactual pair | 2 | 12 + 4 |
| `--suite visible-policy` | Visible-contract pair | 2 | 12 + 4 |
| `--suite all` | All ten tasks | 2 | 60 + 20 |

**The default changed from all ten tasks/two repetitions to the 6+2 quickstart.** Explicit `--task` selections keep their two-repetition default. `--repetitions` overrides either default. `--suite` and `--task` are mutually exclusive. An external `--tasks /path` directory still selects all its tasks with two repetitions unless filtered with `--task`; named suites select built-in tasks only.

```sh
# Preview the old full default explicitly.
acr plan --suite all --repetitions 2

# Run just one chosen task, once.
acr run --model gpt-6-sol --task retry-method-policy --repetitions 1
```

Historical samples and protocols remain unchanged. These explicit selections retain their task fingerprints and seeded order on the current runner:

```sh
acr plan --suite micro --repetitions 2 --seed 20260930
acr plan --suite software-policy --repetitions 2 --seed 20260930
acr plan --suite paired --repetitions 2 --seed 20260930
acr plan --suite visible-policy --repetitions 2 --seed 20260930
```

The reports link the measured commits (`d6274f6`, `af4840c`, `5cbc325`, `63f6054`). Check out the relevant commit and use its explicit task/repetition command to reproduce that runner fingerprint; current runner changes do not rewrite historical measurements. Tests verify that current explicit selections preserve the archived task fingerprints and execution orders.

## Measured pilot

Codex CLI 0.155.1, `gpt-6-sol`, low reasoning, two repetitions per task:

| Strategy | Tasks passed | Input + output tokens, including summary | Median end-to-end time |
| --- | ---: | ---: | ---: |
| Full history | 8/8 | 780,797 | 26.41 s |
| Recent user turn | 2/8 | 768,542 | 30.10 s |
| Automatic structured summary | 8/8 | 899,098 | 43.87 s |

On these short histories, the automatic summary preserved correctness but **increased total tokens and latency**. Truncation lost casing, window-boundary and retry-policy requirements; both truncation runs passed the configuration task. One slug failure concerned separator handling rather than the designated corrected requirement.

[Full results and accounting](reports/README.md) include all 24 continuations, all 8 summary generations, input/cached-input/output breakdowns, and the initial aborted integration batch. All 24 saved candidates were subsequently [rechecked with process-isolated verification](reports/isolated-verifier-recheck.json), with identical outcomes. The timing table records the original runner. The deterministic tests cover candidate outcomes, process isolation, usage accounting, failure handling and sandbox protection of acceptance files.

## Software-policy extension

Two additional tasks cover deployment admission and scoped authorization. In a separate fixed batch, **full passed 4/4, recent 3/4, and structured 4/4**. All designated historical corrections passed; the one failure omitted wildcard-tenant matching. More business rules did not by themselves create a strong retention discriminator. Summary generation again added time and tokens. [Protocol, complete results and phase accounting](reports/software-policy.md) explain the near-saturated outcome and a proposed paired-policy follow-up.

## Counterfactual policy pair

A second fixed batch holds the checkpoint, schema, latest request and public checks identical while reversing an earlier decision: concurrent release wave versus sequential plan. Full and structured passed both versions in both repetitions; recent passed neither complete contract. Cross-scoring shows the recent candidates chose sequential dependency behavior but also violated shared ordering rules. [The paired report](reports/paired-policy.md) includes input fingerprints, every cross-score, costs, and the remaining causal distinction.

The [visible-contract follow-up](reports/visible-policy.md) keeps all shared rules executable and asks the agent to fill only the historical policy predicate. All 12 candidates pass shared rules; full and structured recover both policies (4/4 each), while recent chooses sequential behavior throughout (2/4 requested policies, 0/2 pairs). This separates an opposite-policy implementation from broken shared code.

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
| Release-policy pair (A/B) | Finish a shared capacity budget | Explicit concurrent-wave versus sequential-plan dependency semantics |
| Visible-contract pair (A/B) | Complete only the dependency predicate | Same opposing policies, with all shared rules already implemented |

[Visible-contract protocol](reports/visible-policy.md) narrows the follow-up to recovering the historical policy decision in a shared executable framework.

[Counterfactual pair protocol](reports/paired-policy.md) holds the model-visible recent input fixed while reversing one earlier business decision.

[Software-policy protocol](reports/software-policy.md) distinguishes the final incremental request from earlier corrections and documents the counterexamples used to validate acceptance checks.

Acceptance checks return named booleans. A task passes only when every check passes. `regressions` lists failures of designated corrected requirements; it reports observable behavior, not an inference about the model's internal memory. No LLM judge is used.

Token totals include summary and continuation phases. Cached input is reported separately as a **subset** of input tokens. Token counts are not dollar costs or subscription quota units. End-to-end wall time includes independent verification. Missing usage stays missing; an aborted batch is not presented as a complete comparison.

## Add a task

Pass `--tasks /path/to/tasks` to `list`, `plan` or `run`. Each child directory contains:

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
