# Accept saved native results

`native-run` reports whether a fixed sampling group completed. A candidate that follows the superseded policy remains a valid research outcome, so completion can exit 0 even when behavior fails. `native-accept` provides a separate, opt-in acceptance exit code for automation.

```sh
python3 -B -m context_regression native-accept reports/native-smoke.json --scenario fixed-policy
python3 -B -m context_regression native-accept reports/native-revision.json --scenario policy-revision
python3 -B -m context_regression native-accept reports/native-tool-checkpoint.json --scenario tool-checkpoint
acr native-accept /path/to/new/run/public.json --scenario policy-revision
```

Python 3.11+ is sufficient. The required scenario selects one of three fixed contracts; the command reads a single JSON file and prints a verdict. The same function supports public.json and private results.json through their common fields. It does not read candidate files, credentials, configuration, raw traces or rollout files, and does not execute a model, oracle, worker process or network call. Input files are unchanged; output contains fixed anonymous case/arm/check names and controlled reason codes, not private identities or arbitrary error text.

| Exit | Verdict | Meaning |
| ---: | --- | --- |
| 0 | accepted | The fixed group is complete and every final candidate satisfies its required behavior |
| 1 | behavior_failed | A complete recorded group includes a failed required final behavior |
| 2 | invalid_result | Unreadable JSON, duplicate JSON keys, unsupported protocol/direction, wrong field types, duplicate or unknown structure, or an incomplete generated check list |
| 3 | run_incomplete | A valid partial run, unmet work precondition, missing phase/candidate/oracle, insufficient compact evidence, exceeded tool budget or unconfirmed integrity/cleanup |

An incomplete group takes precedence over any observed behavioral failures. Malformed consumed fields still return 2, including when the rest of the run is incomplete. A failed setup with no pairs, or an empty private seed/null public seed projection, returns 3. Top-level completed alone cannot accept a partial result.

## Fixed-policy and policy-revision checks

- **Plan and group:** known protocol, correct pair/direction and arm order, exactly four unique case/arm results. Fixed-policy has two seed phases; policy-revision adds two separate revision phases. Both have two compact and four continuation phases.
- **Recorded completion:** each required phase has the expected kind, completed status and terminal, and no requested cancellation. Prelude/compact tool counts are zero, continuations use at most 16. Compact evidence includes a compaction-completed marker and successful terminal; a compaction marker in another phase marks the result incomplete. Required runner integrity and cleanup flags must be true.
- **Detailed outcomes:** both visible-policy oracles must record all ten shared checks and dependency_policy, each exactly once with boolean results. Every shared check passes, the known final policy passes, and the opposite policy fails. Both policies passing is an unsupported contradiction for this fixture.

The gate ignores redundant `classification`, `shared_rules_pass`, per-oracle summary `passed`, and `both_policies_pass` fields. It derives acceptance from the detailed checks. It does not audit every metadata field, reconstruct event ordering or match private request/thread identities. Its scope is explicitly **saved native result acceptance; no oracle rerun or wire verification**. Usage remains outside this behavioral gate, so null/incomplete cost coverage does not reject an otherwise complete result.

The public-candidate recheck serves a different purpose: it reruns the published code and compares it to the recorded verdicts. Such historical consistency can hold even for a failed candidate. The acceptance gate reads arbitrary new saved runs in the three supported shapes and requires successful target behavior. Neither command changes native-run's completion semantics.

## Tool-checkpoint checks

This contract requires the single `retry-work` case, one work phase, one compact and two continuations in control/native order. It reports `expected_candidates=2`; the work checkpoint is a prerequisite, not a final candidate. The work tool budget is 8, continuation 16 and compact zero. Phase completion and integrity checks are shared with the policy contracts, including `fixture_unchanged`.

The work oracle must contain all six original retry checks. `server_error`, `rejected_post_retry`, `exact_allowed_methods` and `exact_status_set` must be true; `rate_limit` and `case_insensitive_method` must be false, with no execution error. A different vector returns **3 / run_incomplete**, with `work_precondition_failed` and affected check names: the intended comparison was not established. Setup failures and missing later phases also return 3, with separate reasons. Once the work prerequisite and complete two-arm group are established, any false final check returns **1 / behavior_failed**. All six final checks in both arms must pass for 0.

The recorded tool-name list must use known fixture tools, match the work tool count, contain a read before the first write and a check after the last write. Its public check rows must be `rate_limit=false` and `not_found=true`. Repeated valid tools are allowed within budget. The gate derives these conditions from the sequence/checks rather than `last_check_after_last_write`, `work_outcome`, `comparison_established` or other summary flags.

Each arm's recorded `checkpoint_sha256` must equal the recorded `work_checkpoint_sha256`. This compares saved values only: it reads no source file, recomputes no hash and does not authenticate the work/fork/tool history. `history_matches_completed_calls` is not treated as proof of real wire behavior. Public/private empty work placeholders and work-precondition failure with zero arms are legitimate incomplete prefixes. Malformed consumed fields still return 2.

## 中文

`native-run` 的 0 表示固定采样完成，合法行为失败也会保留。自动化需要行为门时，显式运行 `native-accept FILE --scenario fixed-policy|policy-revision|tool-checkpoint`。它共用 public/private 的稳定字段，只读记录，不公开真实身份。

旧两个政策场景要求完整固定组、四个唯一候选、阶段完成和必要清理记录，以及双 oracle 的完整逐项结果。共享规则全过、最终政策过、相反政策不过才接受；原汇总 bool 和分类不参与放行。返回码 0=接受，1=有效行为失败，2=格式/结构不支持，3=未完成。真实启动失败的空结果也属于未完成。

tool-checkpoint 要求 work 六项结果严格四过两失败，再验收两个最终候选各六项全过；work 不计入最终候选数。前置不符返回 3 并列出受控原因，完整两臂最终行为失败返回 1。工具顺序由列表推导；checkpoint 只比较报告内记录值，不读源码重算 hash。合法失败前缀保留为未完成，格式错误仍为 2。

此命令不重跑候选/oracle，不核验真实 wire、身份、源码或压缩过程，不改旧采样命令和历史文件。若要重算已经公开的源码行为，继续使用 `scripts/recheck_native_candidates.py`。
