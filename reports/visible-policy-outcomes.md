# Context regression results

Controlled reconstructed contexts; not native Codex compaction. Hand-authored coding tasks.

Batch: **completed**; 12/12 attempted.

| Strategy | Passed / attempted | Regression rows | Total tokens¹ | Median end-to-end seconds² |
| --- | ---: | ---: | ---: | ---: |
| full | 4/4 | 0 | 402402 | 33.71 |
| recent | 2/4 | 2 | 396578 | 34.06 |
| structured | 4/4 | 0 | 460968 | 48.73 |

¹ Input + output tokens; summary generation is included. Cached input is a subset of input, not an extra charge. These are CLI-reported tokens, not dollars or subscription quota units.

² Includes summary generation, continuation, and independent verification. All attempted rows remain in the report; aborted batches are not complete comparisons.

## Per-task outcomes

| Task | Repeat | Strategy | Passed | Failed checks |
| --- | ---: | --- | --- | --- |
| visible-policy-a | 2 | structured | True |  |
| visible-policy-a | 2 | recent | False | dependency_policy |
| visible-policy-a | 2 | full | True |  |
| visible-policy-a | 1 | recent | False | dependency_policy |
| visible-policy-a | 1 | structured | True |  |
| visible-policy-a | 1 | full | True |  |
| visible-policy-b | 1 | structured | True |  |
| visible-policy-b | 1 | full | True |  |
| visible-policy-b | 1 | recent | True |  |
| visible-policy-b | 2 | structured | True |  |
| visible-policy-b | 2 | recent | True |  |
| visible-policy-b | 2 | full | True |  |
