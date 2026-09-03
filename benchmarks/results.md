# jcodemunch-mcp -- Token Efficiency Benchmark

**Tokenizer:** `cl100k_base` (tiktoken)  
**Workflow:** `search_symbols` (top 5) + `get_symbol` x 3  
**Baseline A (read-all):** all source files concatenated  
**Baseline B (grep-top-3):** `rg -l` the query terms, then open the top 3 files whole  

## expressjs/express

| Metric | Value |
|--------|-------|
| Files indexed | **186** |
| Symbols extracted | **455** |
| Baseline tokens (all files) | **154,569** |
| Upstream commit | `1faf228935aa` (pinned) |
| Corpus complete | yes |

| Query | Read-all&nbsp;tokens | Grep-top-3&nbsp;tokens | jMunch&nbsp;tokens | Ratio&nbsp;vs&nbsp;read-all | **Ratio&nbsp;vs&nbsp;grep** |
|-------|---------------------:|----------------------:|-------------------:|--------------------------:|--------------------------:|
| `router route handler` | 154,569 | 9,890 | 1,209 | 127.8x | **8.18x** |
| `middleware` | 154,569 | 11,777 | 1,237 | 125.0x | **9.52x** |
| `error exception` | 154,569 | 18,961 | 1,135 | 136.2x | **16.71x** |
| `request response` | 154,569 | 21,620 | 1,158 | 133.5x | **18.67x** |
| `context bind` | 154,569 | 16,371 | 297 | 520.4x | **55.12x** |
| **Average** | — | — | — | 208.6x | **21.6x** |

<details><summary>Query detail (search + fetch tokens, latency)</summary>

| Query | Search&nbsp;tokens | Fetch&nbsp;tokens | Hits&nbsp;fetched | Search&nbsp;ms |
|-------|-----------------:|------------------:|------------------:|---------------:|
| `router route handler` | 500 | 709 | 3 | 37.1 |
| `middleware` | 360 | 877 | 3 | 1.4 |
| `error exception` | 470 | 665 | 3 | 2.0 |
| `request response` | 466 | 692 | 3 | 1.7 |
| `context bind` | 297 | 0 | 0 | 18.4 |

</details>

## fastapi/fastapi

| Metric | Value |
|--------|-------|
| Files indexed | **1,186** |
| Symbols extracted | **13,240** |
| Baseline tokens (all files) | **825,326** |
| Upstream commit | `a64dfbbd21a4` (pinned) |
| Corpus complete | yes |

| Query | Read-all&nbsp;tokens | Grep-top-3&nbsp;tokens | jMunch&nbsp;tokens | Ratio&nbsp;vs&nbsp;read-all | **Ratio&nbsp;vs&nbsp;grep** |
|-------|---------------------:|----------------------:|-------------------:|--------------------------:|--------------------------:|
| `router route handler` | 825,326 | 97,495 | 1,577 | 523.4x | **61.82x** |
| `middleware` | 825,326 | 36,575 | 1,844 | 447.6x | **19.83x** |
| `error exception` | 825,326 | 100,987 | 1,244 | 663.4x | **81.18x** |
| `request response` | 825,326 | 130,461 | 4,699 | 175.6x | **27.76x** |
| `context bind` | 825,326 | 60,963 | 1,383 | 596.8x | **44.08x** |
| **Average** | — | — | — | 481.4x | **46.9x** |

<details><summary>Query detail (search + fetch tokens, latency)</summary>

| Query | Search&nbsp;tokens | Fetch&nbsp;tokens | Hits&nbsp;fetched | Search&nbsp;ms |
|-------|-----------------:|------------------:|------------------:|---------------:|
| `router route handler` | 609 | 968 | 3 | 1252.6 |
| `middleware` | 557 | 1,287 | 3 | 2.2 |
| `error exception` | 521 | 723 | 3 | 3.1 |
| `request response` | 549 | 4,150 | 3 | 7.8 |
| `context bind` | 566 | 817 | 3 | 3.4 |

</details>

## gin-gonic/gin

| Metric | Value |
|--------|-------|
| Files indexed | **98** |
| Symbols extracted | **1,451** |
| Baseline tokens (all files) | **151,842** |
| Upstream commit | `75ccf94d605a` (pinned) |
| Corpus complete | yes |

| Query | Read-all&nbsp;tokens | Grep-top-3&nbsp;tokens | jMunch&nbsp;tokens | Ratio&nbsp;vs&nbsp;read-all | **Ratio&nbsp;vs&nbsp;grep** |
|-------|---------------------:|----------------------:|-------------------:|--------------------------:|--------------------------:|
| `router route handler` | 151,842 | 18,789 | 1,524 | 99.6x | **12.33x** |
| `middleware` | 151,842 | 13,190 | 1,733 | 87.6x | **7.61x** |
| `error exception` | 151,842 | 44,021 | 1,207 | 125.8x | **36.47x** |
| `request response` | 151,842 | 39,929 | 1,533 | 99.0x | **26.05x** |
| `context bind` | 151,842 | 43,946 | 1,687 | 90.0x | **26.05x** |
| **Average** | — | — | — | 100.4x | **21.7x** |

<details><summary>Query detail (search + fetch tokens, latency)</summary>

| Query | Search&nbsp;tokens | Fetch&nbsp;tokens | Hits&nbsp;fetched | Search&nbsp;ms |
|-------|-----------------:|------------------:|------------------:|---------------:|
| `router route handler` | 536 | 988 | 3 | 124.9 |
| `middleware` | 445 | 1,288 | 3 | 1.7 |
| `error exception` | 563 | 644 | 3 | 2.3 |
| `request response` | 662 | 871 | 3 | 2.6 |
| `context bind` | 495 | 1,192 | 3 | 4.3 |

</details>

---

## Grand Summary

| | Tokens |
|--|-------:|
| Baseline A total, read-all (15 task-runs) | 5,658,685 |
| Baseline B total, grep-top-3 | 664,975 |
| jMunch total | 23,467 |
| Reduction vs read-all | 99.6% |
| Ratio vs read-all | 241.1x |
| **Reduction vs grep-top-3** | **96.5%** |
| **Ratio vs grep-top-3** | **28.3x** |

> **Baseline B is the number to quote.** Read-all is a ceiling nobody pays: it assumes an agent opens every file in the repository before acting. Grep-then-read is what a competent agent without this tool actually does, and it is 11.8% of the read-all figure — so measuring against read-all overstates the advantage by about 9x.

> Measured with tiktoken `cl100k_base`. Read-all = every indexed source file. Grep-top-3 = `rg -l` the query terms, then open the top 3 matching files whole. jMunch = search_symbols (top 5) + get_symbol x 3 per query. Both baselines are measured in THIS run against THIS corpus.