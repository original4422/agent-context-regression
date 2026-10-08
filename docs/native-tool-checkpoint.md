# Native continuation from a real work checkpoint

Status: **one live four-phase batch completed; both final candidates passed all six checks.** [Measured report and public artifacts](../reports/native-tool-checkpoint.md). This scenario tests resuming partially completed coding work across native compaction. The existing fixed-policy and policy-revision measurements used zero-tool preludes and an unchanged starter.

```sh
acr native-plan --scenario tool-checkpoint
# One fixed batch, after arranging an exclusive measurement window:
acr native-run --scenario tool-checkpoint --allow-model
```

The fixture references the unchanged `retry-method-policy` task, public checks and six-check external oracle. A real work turn reads `retry.py`, implements the method gate without adding 429, writes the file, runs the public checks after the last write, and stops. The completed tool items must match the work turn returned by `thread/read`, including arguments and results. An outstanding tool at the terminal, unavailable result or mismatch stops the batch; no synthetic tool history is inserted.

The trusted external verifier requires this exact intermediate outcome:

| Check | Required at checkpoint |
| --- | --- |
| server_error | pass |
| rejected_post_retry | pass |
| exact_allowed_methods | pass |
| exact_status_set | pass |
| rate_limit | fail |
| case_insensitive_method | fail |

Both failing checks include the deliberately unfinished 429 behavior. The actual public tool result must record `rate_limit=false` and `not_found=true`. If the external intermediate checks differ, the runner saves the actual source and verdict, records `prelude_behavior_failed` with `comparison_established=false`, and stops without forks or another work attempt. A reference implementation never replaces the candidate.

After that gate, both forks are created from the work terminal before either continuation. Their visible histories must match the completed boundary, including the real read/write/check items. The runner saves the actual intermediate files in its private directory and restores those bytes before each arm at the same candidate path, preserving its directory inode. It checks the saved checkpoint hash before each restore, the restored hash, and the saved hash after verification. Thus control's later edits cannot become native's starting source.

Control continues first. Native requires a matching completed contextCompaction item and successful turn terminal, with source unchanged. Both arms receive the same request:

> Continue the remaining work from the current checkpoint and observed check results. Preserve completed behavior and run the public checks.

The request repeats neither the status set nor method policy. Each final candidate is evaluated against the original six-check oracle in separate candidate worker processes. A behavioral failure is retained and the other arm still runs. Adding 429 while discarding the method gate can pass public checks but fails `rejected_post_retry` and `exact_allowed_methods`; offline reference tests exercise this distinction.

## Fixed budget and output

The runner fixes `gpt-6-astra`/low: one work turn (180 seconds / 8 tools), one compact (90 seconds / zero tools), and two continuations (180 seconds / 16 tools each). This is four model phases across three persistent experiment threads, a 630-second sum of phase limits and at most 40 tool calls. Setup, independent verification and cleanup are additional. Unknown approvals, protocol/infrastructure failures, automatic compaction or changed checkpoints stop the group without retries. The existing process/thread isolation, precise single-call approvals, cancellation and owned-process cleanup apply; only `retry.py` is editable in this scenario.

The public report uses a `work` phase, intermediate verification and anonymous tool-evidence hashes, plus each arm's final `verification`. Raw tool content and real identities remain private. Usage stays null/incomplete. `native-run` continues to report sampling completion through its exit status; final behavior is recorded separately.

`acr native-accept FILE --scenario tool-checkpoint` now accepts saved runs through the [offline behavior gate](native-accept.md#tool-checkpoint-checks): 0 accepted, 1 complete final behavior failure, 2 invalid data, 3 incomplete comparison (including unmet work prerequisites). This support was added after the measured release. The published candidate recheck supports this release through `--scenario tool-checkpoint`, recomputing the partial checkpoint and two final candidates against their recorded results. Existing task/oracle bytes, reports and default plans remain unchanged.

The source itself preserves completed work and public checks can be rerun. This protocol tests an actual coding-work boundary; it does not isolate memory as the only source of task information or estimate a general compression effect.

## 中文

唯一真实四阶段组已完成，两臂最终六项检查全过；原始结果与源码见实测报告。Agent 先实际读取、修改 `retry.py` 并运行检查，外部 oracle 确认四项已完成、两项 429 行为未完成，才从真实终态建立双分支。前置不符就保存实际失败并停止，不重试挑样。两臂按同一真实中间产物原字节恢复，不能把 control 修改带给 native，也不能恢复最初 starter。

续写提示不重复答案。原六项 oracle 分别验证最终源码，撤销 method gate 即使 public 检查通过仍会被拒绝。固定一组四阶段、三个线程，630 秒阶段上限；无新增模型摘要、重试或扩样。`native-accept --scenario tool-checkpoint` 已支持保存结果行为验收；公开候选 recheck 的 `--scenario tool-checkpoint` 可重算三份实际源码。代码也保存进度，因此结果只说明这一实际工具工作流，不说明纯记忆保留、速度收益或普遍压缩无损。
