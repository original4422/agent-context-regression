# Pilot: four controlled coding checkpoints

The fixed batch completed **24 continuations and 8 automatic summary generations**. No additional samples were selected after inspecting the outcomes.

Measured runtime: commit [`d6274f6`](https://github.com/original4422/agent-context-regression/tree/d6274f6), Codex CLI 0.155.1, model `gpt-6-sol`, low reasoning. [Environment](environment.json) records Python and OS versions. [Machine-readable results](pilot-02.json) contain the fixed configuration, seeded execution order, per-check outcomes, per-phase metrics, and source/task fingerprints. [Rendered outcomes](pilot-02.md) show every continuation.

## Outcome

| Strategy | Passed / attempts | Rows failing a designated corrected requirement | Median wall time |
| --- | ---: | ---: | ---: |
| Full history | 8/8 | 0 | 26.41 s |
| Recent turn | 2/8 | 5 | 30.10 s |
| Automatic structured summary | 8/8 | 0 | 43.87 s |

The recent strategy passed both settings-merge attempts. It failed both attempts for each other task. Five of its six failures violated designated corrected requirements; the other slug attempt preserved casing but mishandled repeated separators. These are executable behavior checks, not an LLM assessment of whether the agent remembered something.

## Token accounting

All values below come from Codex's JSONL `turn.completed.usage`. Each of the **32 phase traces contained exactly one `turn.completed` event**, so no cumulative events were counted twice. Its usage includes the model interactions within that phase, including the continuation's tool loop.

| Strategy | Phase | Phase count | Input | Cached input (subset of input) | Output |
| --- | --- | ---: | ---: | ---: | ---: |
| Full | Continuation | 8 | 777,984 | 671,872 | 2,813 |
| Recent | Continuation | 8 | 764,009 | 655,872 | 4,533 |
| Structured | Summary generation | 8 | 124,526 | 22,144 | 1,984 |
| Structured | Continuation | 8 | 769,423 | 689,408 | 3,165 |

Input + output totals are **780,797 / 768,542 / 899,098**, respectively. Cached input is not added again. These are reported token counts, not prices, billed dollars, or units of remaining subscription quota. The generated summary is paid for once per structured attempt in this comparison; it is not reused or amortized across repetitions.

The retained context averaged 1,259 characters for full history, 172 for recent, and 1,103 for structured. This pilot therefore does not show a cost advantage for summarizing short contexts: the modest continuation reduction did not recover the summary-generation overhead. The CLI's fixed scaffolding and tool interactions are included in usage, rather than estimating cost from the supplied history alone.

`wall_seconds` measures summary generation, continuation, workspace setup, and independent verification for that attempt. `phases.*.elapsed_seconds` measures each Codex process separately. All runs were serial; strategy order rotated and reversed within shuffled task/repetition groups. The timing batch ran after the earlier browser-model experiment ended.

## Validation and reproduction

After the batch, all 24 saved candidate modules were independently re-evaluated under the read-only sandbox, matching the recorded outcomes. All 32 phase usage records were reconciled against private JSONL, and runtime/task fingerprints matched the frozen sources. These rechecks are verification of saved candidates, not additional model samples.

```sh
git checkout d6274f6
python3 -m unittest discover -s tests -v
python3 -m context_regression run --model gpt-6-sol --effort low \
  --repetitions 2 --seed 20260930 --recent-turns 1 \
  --summary-chars 4096 --summary-timeout 90 --timeout 180 --max-tools 16
python3 -m context_regression summarize /path/from/run/results.json
```

Fresh runs generate new model outputs. The repository supplies the exact reconstructed histories, checkpoints and executable checks; the comparison measures these four microtasks and the constrained file-tool interface.

## Aborted integration batch

[The initial attempt](integration-failure.json), at `64bab22`, encountered a harness configuration error: the first two continuations could not use their MCP tools because approval was required while the policy was `never`. The third attempt was interrupted during summary generation. Those first two test failures are **integration failures**, excluded from the strategy comparison above.

The fix explicitly authorizes only the four local fixture tools and aborts immediately on rejected MCP calls. A regression test covers that failure path. The old empty-phase aggregation emitted zero usage for the interrupted summary; the published integration record marks that value `null` because no usage event was received. Original events and the original record remain private. No raw prompt, model output, candidate source or credential has been published in these reports.
