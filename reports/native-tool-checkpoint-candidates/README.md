# Tool-checkpoint source artifacts / 工具中间产物

Exact byte copies of the actual work checkpoint and two final candidates from the [native tool-checkpoint batch](../native-tool-checkpoint.md), measured at `782a107`. Only these three individually reviewed fictional `retry.py` files are released from the private artifacts. Logs, rollout files, real identities and private measurement files remain private.

```sh
python3 -I -B scripts/recheck_native_candidates.py --scenario tool-checkpoint
```

Python 3.11+ is sufficient; no Codex, credentials, network or dependencies are needed. All three candidate hashes, the original task and executable verifier hashes are checked before any candidate runs. The existing trusted oracle and isolated Python JSON worker recalculate three verdicts, including the expected four-pass/two-fail intermediate outcome. Every name/pass/error result is compared to the unmodified measured report. Missing/changed inputs or result differences exit nonzero. This is ordinary Python behavior verification, not replay of the original native lifecycle, OS sandbox or timings.

| Artifact | Bytes | retry.py SHA-256 |
| --- | ---: | --- |
| work-checkpoint | 121 | `905871cca8295c273add5670d77233320ff8cfa40c4a7b3341c318009517d30a` |
| retry-work-control | 126 | `4271f70d5826b663d622f3b58c55d6855d7ab32348fcffcbe1d68d6139cecf85` |
| retry-work-native-compact | 126 | `4271f70d5826b663d622f3b58c55d6855d7ab32348fcffcbe1d68d6139cecf85` |

The report's directory hash is SHA-256 over UTF-8 `json.dumps({"retry.py": file_sha256}, sort_keys=True, separators=(",", ":"))`. Expected verdicts come from that report, not a second manifest. The final files happen to be identical; exchanging them makes no byte change. Replacing a final file with the partial checkpoint is rejected before execution.

中文：公开范围仅真实 work 中间产物与两个最终产物这三份 `retry.py` 原字节。脚本先校验全部候选、原任务和验证器，再独立重算三份完整 oracle 结果，与原报告逐项比较；中间态预定四过两失败也必须一致。输入保持，缺失、修改或用中间态替换最终文件在执行前失败。两个最终文件本来字节相同，不能靠 hash 区分互换。复核不需要 Codex、凭据或网络，也不重跑原生压缩；`native-accept` 仍只支持旧两个政策场景。
