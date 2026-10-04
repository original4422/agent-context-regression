# Published native-smoke candidates / 原生压缩候选离线复核

These four `plan.py` files are exact byte copies of the actual candidates from the [bounded native smoke](../native-smoke.md), measured with runner `ec67f5d`. They implement a fictional release planner. Only these four reviewed candidate source files were published from the private run; protocol logs, rollout files, identities and private result files remain private. The original [public measurement JSON](../native-smoke.json) is unchanged.

From the repository root, using Python 3.11+:

```sh
python3 -B scripts/recheck_native_candidates.py
```

No Codex, login, API key, network or package installation is needed. The script first checks all four candidate directories, both task fingerprints and the frozen verifier/worker/shared-check source hashes against the measurement JSON. It then runs the existing trusted oracle against each candidate through a separate `python -I -B` JSON worker, with a 15-second deadline per oracle evaluation. Candidate code is not imported into the oracle process.

The output contains four directory hashes, all eight oracle results with each check's name/pass/error fields, and an exact comparison to the recorded results. All candidates pass the ten shared rules; A candidates pass only A's dependency policy, and B candidates pass only B's. A missing, modified or exchanged file or changed verifier/task stops execution before any candidate runs. A recomputed result difference exits nonzero and shows expected and actual oracle results.

This rechecks the published functions' behavior using ordinary Python subprocesses. The native lifecycle, Codex read-only sandbox and timings remain evidence from the original experiment; this command does not run them again.

## File identity / 文件身份

| Candidate | Bytes | `plan.py` SHA-256 |
| --- | ---: | --- |
| A-control | 1881 | `ef1ecb77e6c342d3d7190da9bcf20c4dbc7149ffe27b385ba356b8f714265d9f` |
| A-native-compact | 1897 | `a90c64b3885cb7a6e33f18b0ad41ce5ad27d5067693a9091a70f4e827ea1fd0e` |
| B-native-compact | 1898 | `c5b335db22ad732c67add47cf0d06e4be9da2d122198d4505d431010b4da3f1d` |
| B-control | 1900 | `42868b4b6ce8cb96ddece8002b3053d33feab390ac1dca20c806b664e447e691` |

The report's `candidate_sha256` hashes the **directory**, not the single file. For these one-file directories, hash the UTF-8 encoding of `json.dumps({"plan.py": file_sha256}, sort_keys=True, separators=(",", ":"))` with SHA-256. This README stays outside those directories so their original hashes remain valid. Expected oracle verdicts are read from the existing report; there is no second verdict manifest.

## 中文说明

这四份 `plan.py` 是真实原生压缩实验产生的虚构发布规划代码，按原始字节公开，未改格式、注释或换行。此次发布范围仅为这四份经过检查的源码；原始日志、rollout、真实身份及私有结果文件仍不公开，已有测量 JSON 字节保持不变。

在仓库根目录执行上面的命令即可用 Python 3.11+ 离线重算，不需要 Codex、登录、凭据、网络或安装依赖。入口先核对全部四个候选、两个任务及验证器源码的 hash，再通过独立 Python JSON worker 执行 4 候选 × 2 oracle。可信 oracle 留在父进程，候选不会被直接导入其中。每份判定的检查名称、通过状态和错误字段均与历史结果逐项比较。

四份代码均通过共同的 10 项规则；A 的两份仅通过 A 政策，B 的两份仅通过 B 政策。缺失、修改、交换候选或更改 oracle/worker 会在候选执行前明确失败；实际结果变化也会非零退出并输出差异。目录 hash 与单文件 hash 定义不同，算法如上。

此次复核对象是公开纯函数的行为。普通 Python 子进程不会重新验证原生压缩生命周期、Codex 的只读 sandbox 或历史耗时。
