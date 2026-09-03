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
| `router route handler` | 154,569 | 9,890 | 1,224 | 126.3x | **8.08x** |
| `middleware` | 154,569 | 11,777 | 1,255 | 123.2x | **9.38x** |
| `error exception` | 154,569 | 18,961 | 1,151 | 134.3x | **16.47x** |
| `request response` | 154,569 | 21,620 | 1,157 | 133.6x | **18.69x** |
| `context bind` | 154,569 | 16,371 | 298 | 518.7x | **54.94x** |
| **Average** | — | — | — | 207.2x | **21.5x** |

<details><summary>Query detail (search + fetch tokens, latency)</summary>

| Query | Search&nbsp;tokens | Fetch&nbsp;tokens | Hits&nbsp;fetched | Search&nbsp;ms |
|-------|-----------------:|------------------:|------------------:|---------------:|
| `router route handler` | 501 | 723 | 3 | 70.9 |
| `middleware` | 361 | 894 | 3 | 6.6 |
| `error exception` | 471 | 680 | 3 | 14.1 |
| `request response` | 469 | 688 | 3 | 2.4 |
| `context bind` | 298 | 0 | 0 | 59.9 |

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
| `router route handler` | 825,326 | 97,495 | 1,653 | 499.3x | **58.98x** |
| `middleware` | 825,326 | 36,575 | 1,959 | 421.3x | **18.67x** |
| `error exception` | 825,326 | 100,987 | 1,194 | 691.2x | **84.58x** |
| `request response` | 825,326 | 130,461 | 5,074 | 162.7x | **25.71x** |
| `context bind` | 825,326 | 60,963 | 1,212 | 681.0x | **50.3x** |
| **Average** | — | — | — | 491.1x | **47.6x** |

<details><summary>Query detail (search + fetch tokens, latency)</summary>

| Query | Search&nbsp;tokens | Fetch&nbsp;tokens | Hits&nbsp;fetched | Search&nbsp;ms |
|-------|-----------------:|------------------:|------------------:|---------------:|
| `router route handler` | 609 | 1,044 | 3 | 672.7 |
| `middleware` | 568 | 1,391 | 3 | 2.8 |
| `error exception` | 524 | 670 | 3 | 3.0 |
| `request response` | 538 | 4,536 | 3 | 12.1 |
| `context bind` | 558 | 654 | 3 | 3.6 |

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
| `router route handler` | 151,842 | 18,789 | 1,559 | 97.4x | **12.05x** |
| `middleware` | 151,842 | 13,190 | 1,794 | 84.6x | **7.35x** |
| `error exception` | 151,842 | 44,021 | 1,229 | 123.5x | **35.82x** |
| `request response` | 151,842 | 39,929 | 1,564 | 97.1x | **25.53x** |
| `context bind` | 151,842 | 43,946 | 1,721 | 88.2x | **25.54x** |
| **Average** | — | — | — | 98.2x | **21.3x** |

<details><summary>Query detail (search + fetch tokens, latency)</summary>

| Query | Search&nbsp;tokens | Fetch&nbsp;tokens | Hits&nbsp;fetched | Search&nbsp;ms |
|-------|-----------------:|------------------:|------------------:|---------------:|
| `router route handler` | 536 | 1,023 | 3 | 100.2 |
| `middleware` | 443 | 1,351 | 3 | 11.5 |
| `error exception` | 575 | 654 | 3 | 2.5 |
| `request response` | 686 | 878 | 3 | 3.0 |
| `context bind` | 495 | 1,226 | 3 | 15.3 |

</details>

---

## Grand Summary

| | Tokens |
|--|-------:|
| Baseline A total, read-all (15 task-runs) | 5,658,685 |
| Baseline B total, grep-top-3 | 664,975 |
| jMunch total | 24,044 |
| Reduction vs read-all | 99.6% |
| Ratio vs read-all | 235.3x |
| **Reduction vs grep-top-3** | **96.4%** |
| **Ratio vs grep-top-3** | **27.7x** |

> **Baseline B is the number to quote.** Read-all is a ceiling nobody pays: it assumes an agent opens every file in the repository before acting. Grep-then-read is what a competent agent without this tool actually does, and it is 11.8% of the read-all figure — so measuring against read-all overstates the advantage by about 9x.

> Measured with tiktoken `cl100k_base`. Read-all = every indexed source file. Grep-top-3 = `rg -l` the query terms, then open the top 3 matching files whole. jMunch = search_symbols (top 5) + get_symbol x 3 per query. Both baselines are measured in THIS run against THIS corpus.