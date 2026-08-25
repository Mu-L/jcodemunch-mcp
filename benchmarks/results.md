# jcodemunch-mcp -- Token Efficiency Benchmark

**Tokenizer:** `cl100k_base` (tiktoken)  
**Workflow:** `search_symbols` (top 5) + `get_symbol` x 3  
**Baseline A (read-all):** all source files concatenated  
**Baseline B (grep-top-3):** `rg -l` the query terms, then open the top 3 files whole  

## expressjs/express

| Metric | Value |
|--------|-------|
| Files indexed | **186** |
| Symbols extracted | **200** |
| Baseline tokens (all files) | **154,569** |
| Upstream commit | `1faf228935aa` (pinned) |
| Corpus complete | yes |

| Query | Read-all&nbsp;tokens | Grep-top-3&nbsp;tokens | jMunch&nbsp;tokens | Ratio&nbsp;vs&nbsp;read-all | **Ratio&nbsp;vs&nbsp;grep** |
|-------|---------------------:|----------------------:|-------------------:|--------------------------:|--------------------------:|
| `router route handler` | 154,569 | 9,890 | 1,135 | 136.2x | **8.71x** |
| `middleware` | 154,569 | 11,777 | 1,259 | 122.8x | **9.35x** |
| `error exception` | 154,569 | 18,961 | 1,155 | 133.8x | **16.42x** |
| `request response` | 154,569 | 21,620 | 1,161 | 133.1x | **18.62x** |
| `context bind` | 154,569 | 16,371 | 299 | 517.0x | **54.75x** |
| **Average** | — | — | — | 208.6x | **21.6x** |

<details><summary>Query detail (search + fetch tokens, latency)</summary>

| Query | Search&nbsp;tokens | Fetch&nbsp;tokens | Hits&nbsp;fetched | Search&nbsp;ms |
|-------|-----------------:|------------------:|------------------:|---------------:|
| `router route handler` | 424 | 711 | 3 | 65.2 |
| `middleware` | 362 | 897 | 3 | 14.3 |
| `error exception` | 472 | 683 | 3 | 16.2 |
| `request response` | 470 | 691 | 3 | 6.4 |
| `context bind` | 299 | 0 | 0 | 53.3 |

</details>

## fastapi/fastapi

| Metric | Value |
|--------|-------|
| Files indexed | **1,186** |
| Symbols extracted | **6,841** |
| Baseline tokens (all files) | **825,326** |
| Upstream commit | `a64dfbbd21a4` (pinned) |
| Corpus complete | yes |

| Query | Read-all&nbsp;tokens | Grep-top-3&nbsp;tokens | jMunch&nbsp;tokens | Ratio&nbsp;vs&nbsp;read-all | **Ratio&nbsp;vs&nbsp;grep** |
|-------|---------------------:|----------------------:|-------------------:|--------------------------:|--------------------------:|
| `router route handler` | 825,326 | 97,495 | 1,657 | 498.1x | **58.84x** |
| `middleware` | 825,326 | 36,575 | 1,963 | 420.4x | **18.63x** |
| `error exception` | 825,326 | 100,987 | 1,265 | 652.4x | **79.83x** |
| `request response` | 825,326 | 130,461 | 5,078 | 162.5x | **25.69x** |
| `context bind` | 825,326 | 60,963 | 1,390 | 593.8x | **43.86x** |
| **Average** | — | — | — | 465.4x | **45.4x** |

<details><summary>Query detail (search + fetch tokens, latency)</summary>

| Query | Search&nbsp;tokens | Fetch&nbsp;tokens | Hits&nbsp;fetched | Search&nbsp;ms |
|-------|-----------------:|------------------:|------------------:|---------------:|
| `router route handler` | 610 | 1,047 | 3 | 455.4 |
| `middleware` | 569 | 1,394 | 3 | 8.4 |
| `error exception` | 525 | 740 | 3 | 8.1 |
| `request response` | 539 | 4,539 | 3 | 22.0 |
| `context bind` | 547 | 843 | 3 | 10.0 |

</details>

## gin-gonic/gin

| Metric | Value |
|--------|-------|
| Files indexed | **98** |
| Symbols extracted | **1,260** |
| Baseline tokens (all files) | **151,842** |
| Upstream commit | `75ccf94d605a` (pinned) |
| Corpus complete | yes |

| Query | Read-all&nbsp;tokens | Grep-top-3&nbsp;tokens | jMunch&nbsp;tokens | Ratio&nbsp;vs&nbsp;read-all | **Ratio&nbsp;vs&nbsp;grep** |
|-------|---------------------:|----------------------:|-------------------:|--------------------------:|--------------------------:|
| `router route handler` | 151,842 | 18,789 | 1,563 | 97.1x | **12.02x** |
| `middleware` | 151,842 | 13,190 | 1,798 | 84.5x | **7.34x** |
| `error exception` | 151,842 | 44,021 | 1,233 | 123.1x | **35.7x** |
| `request response` | 151,842 | 39,929 | 1,568 | 96.8x | **25.46x** |
| `context bind` | 151,842 | 43,946 | 1,725 | 88.0x | **25.48x** |
| **Average** | — | — | — | 97.9x | **21.2x** |

<details><summary>Query detail (search + fetch tokens, latency)</summary>

| Query | Search&nbsp;tokens | Fetch&nbsp;tokens | Hits&nbsp;fetched | Search&nbsp;ms |
|-------|-----------------:|------------------:|------------------:|---------------:|
| `router route handler` | 537 | 1,026 | 3 | 136.6 |
| `middleware` | 444 | 1,354 | 3 | 33.4 |
| `error exception` | 576 | 657 | 3 | 14.3 |
| `request response` | 687 | 881 | 3 | 9.8 |
| `context bind` | 496 | 1,229 | 3 | 23.6 |

</details>

---

## Grand Summary

| | Tokens |
|--|-------:|
| Baseline A total, read-all (15 task-runs) | 5,658,685 |
| Baseline B total, grep-top-3 | 664,975 |
| jMunch total | 24,249 |
| Reduction vs read-all | 99.6% |
| Ratio vs read-all | 233.4x |
| **Reduction vs grep-top-3** | **96.4%** |
| **Ratio vs grep-top-3** | **27.4x** |

> **Baseline B is the number to quote.** Read-all is a ceiling nobody pays: it assumes an agent opens every file in the repository before acting. Grep-then-read is what a competent agent without this tool actually does, and it is 11.8% of the read-all figure — so measuring against read-all overstates the advantage by about 9x.

> Measured with tiktoken `cl100k_base`. Read-all = every indexed source file. Grep-top-3 = `rg -l` the query terms, then open the top 3 matching files whole. jMunch = search_symbols (top 5) + get_symbol x 3 per query. Both baselines are measured in THIS run against THIS corpus.