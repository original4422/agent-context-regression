# Policy recovery with the shared contract visible

The first counterfactual pair lost shared ordering rules in every recent-turn continuation. This follow-up keeps those rules visible and executable in both checkpoints, leaving only the opposing historical dependency decision unfinished.

This narrows the task from implementing the full admission routine to **recovering a historical decision in a small predicate**. Its success rates are reported separately from the earlier pair.

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
