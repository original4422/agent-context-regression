# Native user-policy revision

**Measured:** one [fixed ten-phase batch](../reports/native-revision.md) completed; both directions passed the latest policy in control and native arms. Four actual candidates are public and can be rechecked with `python3 -B scripts/recheck_native_candidates.py --scenario policy-revision`.

This scenario checks a different question from fixed-policy retention: after the user explicitly replaces an earlier valid decision, does a compacted thread implement the latest policy or revive the superseded one?

The fixture contains two directions, A→B and B→A. A means concurrent launch (dependencies already completed); B means sequential execution (earlier selections may satisfy dependencies). Each direction uses **two separate real user turns**: an initial policy with a real completed reply, then an explicit correction with another completed reply. Neither turn may call tools or change source. Both control and native forks are created from the correction's completed turn, preserving both turns in the boundary comparison. No synthetic assistant/tool history is injected.

```sh
# Offline preview, including exact correction text and hashes:
python3 -B -m context_regression native-plan --scenario policy-revision --model gpt-6-astra
# One fixed model batch, only after arranging an exclusive measurement window:
python3 -B -m context_regression native-run --scenario policy-revision --allow-model
```

The runner fixes `gpt-6-astra`/low. The default scenario remains `fixed-policy` and keeps its original eight-phase plan. Revision is **4 prelude turns + 2 compactions + 4 continuations**, ten phases across six persistent experiment threads. Each prelude has 60 seconds/zero tools, compaction 90 seconds/zero tools, and continuation 180 seconds/16 tools: 1,140 seconds of phase limits. A→B runs control first; B→A runs native first. Both forks exist before either arm runs, and every arm starts from the same source bytes at the same neutral candidate path.

All continuations receive the identical request to implement the latest agreed decision, without repeating either policy. Native completion still requires a matching new turn, completed contextCompaction item and successful terminal. Unknown approvals, automatic compaction, failed boundaries or infrastructure failures stop the group. A behavioral failure remains an outcome and does not replace the sample. There are no retries.

The existing two visible-policy oracles and ten shared rules are unchanged. Each candidate is scored against both external oracles. `latest_policy` means only the final policy passes, `superseded_policy` means only the old policy passes, and `neither_policy` preserves all other failures. The old-policy reference passes shared rules while failing exactly the new policy discriminator. A control failure identifies a revision-following problem already present without manual compaction; a branch difference is reported as one observation, not a general effect estimate.

Before a live batch, the fake ten-phase graph, wrong-boundary/revision-failure/compaction-ack cases, old-policy discriminator and installed fixture loading must pass. Reports retain original phase snapshots with null/incomplete usage. The latest user message may itself survive compaction; correct code does not reveal the opaque summary's contents. Historical tasks, reports and public candidate hashes remain unchanged.

中文：此场景测试用户明确撤销先前有效政策后的更新语义。先真实完成旧政策 turn，再真实完成修订 turn，从修订终态建立两个分支；A→B、B→A 各一次。复用原源码 checkpoint、共享规则和双 oracle，区别最新政策、已撤销政策及其他错误。默认旧场景不变，不添加随机噪声，不因行为失败换样，usage 继续为 null/incomplete。
