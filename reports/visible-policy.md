# Policy recovery with the shared contract visible

The first counterfactual pair lost shared ordering rules in every recent-turn continuation. This follow-up keeps those rules visible and executable in both checkpoints, leaving only the opposing historical dependency decision unfinished.

This narrows the task from implementing the full admission routine to **recovering a historical decision in a small predicate**. Its success rates are reported separately from the earlier pair.

## Measured outcome

The fixed batch completed **12 continuations and 4 summaries** at [`63f6054`](https://github.com/original4422/agent-context-regression/tree/63f6054), using Codex CLI 0.155.1, `gpt-6-sol`, low reasoning. No attempt was replaced. [Environment](visible-policy-environment.json), [results JSON](visible-policy-results.json), [all own-policy outcomes](visible-policy-outcomes.md), and [complete cross-scores](visible-policy-cross-scores.json) are public.

| Strategy | Shared rules pass | Requested policy passes | Both A/B pass per repetition | Input + output tokens | Median end-to-end seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full | 4/4 | 4/4 | 2/2 | 402,402 | 33.71 |
| Recent | 4/4 | 2/4 | 0/2 | 396,578 | 34.06 |
| Structured | 4/4 | 4/4 | 2/2 | 460,968 | 48.73 |

All twelve candidates satisfied every shared external check. All four recent candidates implemented policy B, which allows an earlier selected prerequisite to satisfy a dependency. They therefore passed the two B attempts and failed only `dependency_policy` on the two A attempts. Cross-scoring classifies the latter as **opposite policy**, not invalid shared implementations.

| Strategy | Requested-policy implementation | Opposite-policy implementation | Neither complete policy |
| --- | ---: | ---: | ---: |
| Full | 4 | 0 | 0 |
| Recent | 2 | 2 | 0 |
| Structured | 4 | 0 | 0 |

Full and structured followed both explicit historical decisions. The recent arm had identical observations across A/B and consistently selected the sequential interpretation in these four samples. The result demonstrates this controlled distinction between policy recovery and shared-code correctness. It does not estimate real-world compaction performance, and its smaller predicate-edit task is not pooled with the earlier full-implementation pair.

Every saved candidate was rerun against both oracles under the real read-only sandbox. All original own-policy verdicts matched. Four actual recent prompt files were byte-identical and matched the frozen input hash; every task and runner fingerprint matched. All sixteen private phase traces had exactly one `turn.completed` record, matching the published usage. No extra model runs were used for this validation.

### Phase accounting

| Strategy | Phase | Count | Input | Cached input (subset) | Output | Median phase seconds |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Full | Continuation | 4 | 399,712 | 333,824 | 2,690 | 33.21 |
| Recent | Continuation | 4 | 393,794 | 356,352 | 2,784 | 33.58 |
| Structured | Summary | 4 | 62,396 | 16,128 | 1,212 | 15.84 |
| Structured | Continuation | 4 | 394,588 | 348,544 | 2,772 | 31.72 |

Mean retained context lengths were 1,629 characters (full), 236 (recent) and 1,476 (structured); the identical source checkpoint is also available through file tools in every arm. Summary generation is included once in each structured total. Cached input is part of input, not an additional quantity. These are CLI token counts, not subscription allowance units. End-to-end time includes setup and external verification; phase medians are not additive to the median of total attempt times.

To recheck your own private run with the same task definitions and runner:

```sh
python3 scripts/score_policy_pair.py /path/to/private/batch/results.json
```

This completes the planned policy-isolation follow-up. Further work should improve selecting, running and reproducing these comparisons rather than add samples of this same policy.

## Shared implementation and opposite decision

Both tasks expose the same `plan.py`. Its docstring specifies the full shared contract, and its existing `select_plan` function implements stable descending priority, input-order ties, one pass without revisiting skipped jobs, manual approval, all-prerequisite gating, a shared capacity budget, skip-and-continue, exact fits, zero-cost jobs, admission order, and no input mutation. Only `_dependencies_satisfied(needs, completed, selected)` returns the placeholder `False`.

- **A:** concurrent launch wave; dependencies must have completed before this call.
- **B:** sequential plan; dependencies may also be earlier selected jobs because the executor waits for each to succeed before continuing.

Only the earlier explicit user decision differs between histories. The final turn, request, schema, complete source, file names, public checks and tool metadata match exactly. The candidate can still edit the entire file. If it breaks a shared rule, the external oracle reports that failure.

Both trusted oracles import the **same `SHARED_CHECKS` callables** from `context_regression/release_checks.py`. The sole different check is `dependency_policy`: for the same `base → app` input, A requires `["base"]`, B requires `["base", "app"]`. Public smoke checks are neutral between these policies.

## Offline evidence

[Common input fingerprints](visible-policy-inputs.json) can be reproduced with:

```sh
python3 scripts/audit_policy_pair.py visible-policy
```

Offline tests replace only the AST body of the pending policy hook with each reference predicate. They prove that all other executable statements still equal the checkpoint and then execute public and external checks. Both reference versions pass their own oracle; each fails the other only at `dependency_policy`. This tests the executable shared contract, not whether its docstring contains a list of keywords. Both oracles also use the same shared check function objects. The source checkpoint itself fails public and independent checks.

## Frozen protocol

- One pair × two policies × three strategies × two repetitions = **12 continuations plus 4 summaries**.
- Codex `gpt-6-sol`, low reasoning, seed `20260930`; all runs serial.
- One retained recent turn; automatic summary limited to 4,096 characters and 90 seconds.
- Continuation limited to 180 seconds and 16 tool calls.
- Report every attempt; do not replace failures or extend sampling to seek a desired result.
- Re-evaluate every saved candidate against both oracles. Report shared-rule success independently from the A/B discriminator and requested-policy success.
- Report whether both requested policies pass within each strategy/repetition, along with summary and continuation costs.

```sh
python3 -m context_regression run --model gpt-6-sol --effort low \
  --task visible-policy-a --task visible-policy-b --repetitions 2 --seed 20260930 \
  --recent-turns 1 --summary-chars 4096 --summary-timeout 90 \
  --timeout 180 --max-tools 16
```

Recent inputs contain no signal identifying which opposing policy is requested. Independent samples can still produce different choices. This fixed two-repetition experiment reports controlled outcomes, not a general memory ranking. The previous pair, task fixtures and reports remain unchanged. After this batch, development moves to running and reproducing comparisons rather than adding more samples of the same policy.
