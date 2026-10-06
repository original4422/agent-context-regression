# Native revision candidates / 政策修订候选

Exact byte copies of the four actual candidates from the [native revision batch](../native-revision.md), measured at `5c06db1`. Only these reviewed fictional `plan.py` files were released from the private run; logs, rollout files, identities and private measurement files remain private.

```sh
python3 -B scripts/recheck_native_candidates.py --scenario policy-revision
```

Run from the repository root with Python 3.11+. No Codex, credentials, network or extra dependencies are needed. The command verifies frozen candidate, task and verifier hashes before execution, then uses the existing trusted oracles and isolated Python JSON worker to recompute all eight results. Each check is compared by its full name/pass/error representation to the original result; mismatches exit nonzero. It does not rerun native compaction or reproduce the original OS sandbox/timing measurement.

| Candidate | Bytes | plan.py SHA-256 |
| --- | ---: | --- |
| A-to-B-control | 1909 | `b9ddbe2426c6370261ed96f546809aefa92193509c98682bc124b290d51bc076` |
| A-to-B-native-compact | 1897 | `e28004f54762df902c70d91f0e00af2511a308c43be70b2e391a071eac8a2620` |
| B-to-A-native-compact | 1867 | `17da3ec29514114fbf00abe66611a3a7714bda589b918d31eb0cc0bba58cd7d9` |
| B-to-A-control | 1889 | `9d00b2b5c0eac35f9f009d35e8d078c050472861b2630c16b24b7a9641e04f37` |

The report’s directory hash is SHA-256 over UTF-8 `json.dumps({"plan.py": file_sha256}, sort_keys=True, separators=(",", ":"))`. This README is outside the candidate directories. Expected results come from the existing measured report rather than a second verdict manifest. A→B candidates pass only B’s dependency policy; B→A candidates pass only A’s. All four pass the ten common rules.

中文：四份代码是该组真实用户修订实验的虚构任务产物，保持原字节。命令先校验候选、任务及验证器版本，再在独立 Python 子进程中重算 4 候选 × 2 oracle，与历史逐项判定比较。缺失、修改、交换文件或版本变化会在执行前失败。公开范围仅这四份源码，原日志、rollout、身份和私有结果不公开。行为复核不代表重跑原生压缩、原 OS sandbox 或计时。
