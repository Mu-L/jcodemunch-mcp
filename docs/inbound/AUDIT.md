# AUDIT — the inbound surface of jcodemunch-mcp (2026-09-04)

Phase 1 of the inbound layer: read only. Every number here was computed on
2026-09-04 from `gh issue list --state all --limit 1000` (310 issues, #4 to
#574) and `gh pr list --state all --limit 1000` (267 PRs) against
`jgravelle/jcodemunch-mcp`, plus the repository settings API and the files in
`.github/`. The raw pulls are in the session scratchpad, not the repo. The
repository became public in March 2026, so "the last year" is six months and
one week; there is no earlier history to compare against.

Method lines are given so each block can be recomputed. Nothing here is a
Floor; anything the policy needs as a threshold is derived in `POLICY.md`
from these figures and cited back to the block that produced it.

## 1. Issue history

### 1.1 Volume

| month | issues opened | of which by the maintainer | by everyone else |
|---|---|---|---|
| 2026-03 | 86 | 4 | 82 |
| 2026-04 | 44 | 6 | 38 |
| 2026-05 | 40 | 10 | 30 |
| 2026-06 | 25 | 0 | 25 |
| 2026-07 | 25 | 9 | 16 |
| 2026-08 | 83 | 24 | 59 |
| 2026-09 (4 days) | 7 | 4 | 3 |

310 issues, 112 distinct authors, 83 of whom filed exactly one. The
maintainer filed 57 (audits, design records, roadmap phases). One reporter
(@rknighton) filed 48, the next four between 12 and 17. The August spike is
two QA campaigns (#556 by @otherjoel, thirteen findings split per policy 1;
the #559 to #572 series) plus the maintainer's own audit issues.

Method: `createdAt[:7]` over the issue pull; author split by
`author.login == "jgravelle"`.

### 1.2 Categories

Labels are too sparse to classify from: `bug` 20, `enhancement` 10, `design`
2, `question` 1, `documentation` 1, and 276 issues carry no label at all. The
table is a keyword classification over title and body (bug: traceback, error,
crash, fails, regression, KeyError; feature: "feature request", "add
support", proposal; question: a title ending in `?` or "how do I"), read
against the labels where they exist and spot-checked. Treat the counts as
±10%; the representative numbers are exact.

| category | approx. count | representative issues |
|---|---|---|
| bug, reproducible from the report | ~100 | #572 (cache returned its stored dict; reporter's own argument shaped the fix), #557 (Windows watcher 10 s reindex, measured), #559 (count taken after the page cut), #566 (dead-code confidence 1.0 on a stale index), #553 (`search_ast` served empty tables) |
| bug, not reproducible as filed | ~15 | #536 (a conformance tool's seven "violations", closed not-planned with measurements), #341 (client-side config problem, not ours), #574 (open: two ABI versions of a native dependency, no reproduction yet) |
| feature request | ~37 | #452 (Markdown as a first-class index target), #383 (progress without a client token), #371 (process identity), #289/#288 (CLI ergonomics), #480 (paid API metering; closed not-planned, no comment) |
| question or support | ~16 | #382 ("old tree-sitter dependency?", answered with a tested reason), #573, #283 (NestJS coupling reading), #87 (licensing question) |
| QA pass or multi-finding report | 8 | #556 (thirteen findings), #444 (@elfrost, archive guard), #128 (A/B results), #332 (budget-context design) |
| design or roadmap record | ~20 | #385/#386 (moved to ROADMAP.md), #377 (handoff/v2), #332 |
| duplicate or wrong-repo | ~5 | #265 (Markdown indexing belongs to jdocmunch), #312 (PyPI quarantine notice, a status not a bug) |
| spam or off-topic | 2 | #481 (awesome-list listing invitation), #480 |
| security-shaped, filed PUBLICLY | 6 | #447 and #444 (drive-absolute archive member escapes the install-pack guard), #509 (`index_file` writes into another repository's index), #508 (`index_file` ignores the project's secret patterns), #449 and #448 (SECURITY.md accuracy) |
| licensing or client relationship | 4 | #87, #364 (license key evaluation window), #418 (licensed starter pack download), #90 (CLA outreach) |

The security row is the one that matters for this layer: **zero reports have
ever come through the advisory form** (`security-advisories` returns 0),
and every security-shaped finding arrived as a public issue, four of them
inside QA passes that also carried ordinary bugs. The disclosure path in
`SECURITY.md` §"Reporting a vulnerability" is asserted by
`tests/test_security_md_policy.py` but has never been exercised by a
reporter.

### 1.3 Time to first response and to close

| measure | n | median | p75 | p90 |
|---|---|---|---|---|
| first comment by someone other than the author | 218 | 3.1 h | 7.6 h | |
| open to close | 309 | 4.6 h | 13.0 h | 28.1 h |

92 issues have no comment from anyone but the author: 54 are the
maintainer's own records (audits, roadmap phases) and 42 of the rest were
closed by a linked PR without a comment. One issue is open (#574, 0 comments,
opened 2026-09-03).

Method: first `comments[]` entry whose `author.login` differs from the issue
author; `closedAt - createdAt`.

### 1.4 Resolved with a code change or without

- 106 issues are referenced by number in a PR title or body; 98 commit
  messages since March carry a `Closes/Fixes/Resolves #N` trailer. Of the
  253 issues filed by someone other than the maintainer, 91 are PR-linked.
  Many bugs were fixed in a release commit that names the issue in
  `CHANGELOG.md` rather than in a PR, so the true code-change share is
  higher than 106/310; the CHANGELOG is the record and this audit did not
  parse it.
- 10 closed `NOT_PLANNED`, each with a stated reason: #536 (the conformance
  tool was wrong, measured), #481 (listing spam), #480 (no comment: the one
  silent close in the set), #386 and #385 (design moved to ROADMAP.md),
  #382 (dependency pin is deliberate, tested), #341 (not our bug), #332
  (design accepted, not tracker work), #312 (status, not a bug), #265
  (belongs to jdocmunch).
- 299 `COMPLETED`.

### 1.5 In hindsight: what an agent could have handled

Read against the workflows that exist today (`/fix-issue`, `/triage-issue`,
the reviewer subagent, the harness tiers), not against an imagined agent.

**Fully handleable by an agent (about a third of the external bugs).** The
report names a tool, an input and an observed output, and the failing test
writes itself: #572 (two calls, second raises `KeyError: '_meta'`), #559
(two page sizes disagree), #553 (declared key vs emitted key), #557 (a
measured 10 s reindex with a named directory), #550, #566. `/fix-issue`
already reproduced #572 from the report alone (VERIFICATION §3). The
constraint is not capability but the review: several of these fixes went
one layer down from the reported site (#572's cache, #566's
`check_delete_safe`), which is the reviewer subagent's job to demand and a
human's job to accept.

**Needed a human decision.** #382 (keep a deliberate pin, with a tested
reason a user can read), #385/#386 and #332 (what is roadmap versus
tracker), #265 and #312 (product boundary and a status notice), #480
(pricing), #536 (declaring an external tool wrong in public), every
`design`-labelled issue, and every timebox posted to a contributor (policy
3a). An agent can draft each of these; none should post unattended.

**Should never have been touched by an agent.** #447/#444 and #509/#508
(a path-escape and a cross-repository write: these are vulnerability
reports and would have been advisories under the policy this layer
adopts), #87/#364/#418 (licensing and a paying user's install), #90 (CLA
outreach, a legal step), #341 (a stranger's Claude Desktop configuration,
i.e. someone else's client relationship). The security four are the case
that decides the design: an agent that classified #509 as "reproducible
bug" and opened a public PR with a failing test would have published the
exploit before the fix.

### 1.6 Who files

Account age at the time of the author's first issue, from `users/<login>
.created_at` for all 112 authors: 96 accounts older than a year, 16 between
30 days and a year, **none younger than 30 days**. The "young account" rule
the brief asks for has no historical case to calibrate against; it costs
nothing today and is written as a guard against a shape that has not
appeared yet.

## 2. Dependency updates

### 2.1 Configuration

`.github/dependabot.yml`: security updates weekly for `uv` and
`github-actions`, grouped into one PR each (`open-pull-requests-limit: 0`
suppresses version-update noise); since 2026-09-04 (cicd DESIGN §4) also a
MONTHLY minor-and-patch group for each ecosystem, majors ignored. Every
Dependabot PR runs the full PR gate.

### 2.2 History

14 Dependabot PRs since March: 10 merged, median 4.8 h from open to merge,
maximum 11.5 h; 4 closed unmerged (#347 to #350, superseded the same day by a
hand bump `b888aee` that combined them). One hand-authored security bump
outside Dependabot (`4ccb799`, httplib2, GHSA-j5g9-f88f-gfj3). Zero open
Dependabot alerts on 2026-09-04.

**Breakage attributable to a dependency update: none found.** A grep of
`CHANGELOG.md` and `ISSUE-HISTORY.md` for `dependabot`, `bump` and grammar
names finds no release note blaming a merged bump. The dependency incidents
on record are the other direction: the PyPI quarantine (#312, June) and the
`packaging` ceiling that broke the global `twine` (release skill).

### 2.3 Grammar and parser updates

`tree-sitter-language-pack` is pinned `>=0.7.0,<1.0.0` on purpose. #382
records the test: 1.x fetches grammars over the network at first use and
wrote 67 shared libraries into a user cache on a clean install, which is a
change in the product's security posture, not a version bump. **No grammar
update has changed indexing behaviour since March**; every indexing change
on record was OUR parser edit, stamped by `PARSER_GENERATION` (2→7 across
Racket, Rust and the impl-block fix) and by `racket_config_digest`. So the
"grammar or parser change" category in the policy has one live trigger
today: a Dependabot PR that moves `tree-sitter` or
`tree-sitter-language-pack`, which the monthly minor-and-patch group can
now produce. The mandatory full-corpus `/benchmark-compare` the brief asks
for has never run on a real grammar update because there has never been
one.

## 3. Existing surface

### 3.1 Templates, labels, ownership

- `.github/ISSUE_TEMPLATE/bug_report.md` (label `bug`),
  `multi_finding_report.md` (label `qa`), `config.yml` (blank issues ON;
  contact links to Discussions "Ideas" and to ROADMAP.md).
  ⚠ **The `qa` label does not exist in the repository**, so GitHub drops it
  silently and multi-finding reports arrive unlabelled. Finding for Phase 4.
- No pull request template. No `CODEOWNERS`. `AGENTS.md` exists at the root
  (a policy paste for coding agents that read it).
- 19 labels. Human-applied: `bug`, `enhancement`, `design`, `question`,
  `documentation`, `duplicate`, `wontfix`, `invalid`, `good first issue`,
  `help wanted`. CI-owned: `regression` (main.yml), `drift` (nightly.yml),
  `P0` and `release` (release.yml), `harness-results` (weekly results PR),
  `bypass` (RUNBOOK §6), `no-changelog` (a PR-gate signal). Dependabot:
  `dependencies`, `python:uv`. None of the labels this layer needs exist
  (`agent-authored`, `agent-fix`, `needs-human`, `security`, and so on).

### 3.2 Disclosure path

`SECURITY.md` §"Reporting a vulnerability": the GitHub advisory form, a
3-day acknowledgement and a 14-day verdict, scope stated, both windows
asserted by `tests/test_security_md_policy.py` in the fast tier. Private
vulnerability reporting must be enabled in repository settings for the form
to work; the API this audit can reach returns `security_and_analysis` with
`secret_scanning` and `secret_scanning_push_protection` enabled and
`dependabot_security_updates` enabled, but does not expose the
private-reporting toggle. ⚠ **Not verified from here**; Phase 6 requires a
test submission. Zero advisories exist, so the path has never been used.

### 3.3 Automation already touching issues and PRs

| workflow | event | writes | note |
|---|---|---|---|
| `main.yml` | push to main, weekly | opens a `regression` issue per failing Floor; opens the weekly `harness-results` PR (`pull-requests: write`) | our own numbers, no external text |
| `nightly.yml` | schedule | opens `drift` issues | same |
| `release.yml` | dispatch | opens `P0`/`release` issues on a failed post-publish check | same |
| `pr-gate.yml` stage 4 | `pull_request` | bench delta comment (`pull-requests: write`) | on a fork PR the token is read-only and the comment step skips |
| `health-radar.yml` + `health-radar-comment.yml` | `pull_request`, then `workflow_run` | the radar comment, posted from the trusted context using an artifact the untrusted run uploaded | ⚠ the only place external-run output is posted with a write token; the payload is rendered by our script from our numbers, and the comment step reads it as text. Pre-existing; noted, not changed by this layer |
| CLA Assistant | webhook (`pull_request`, `merge_group`) | `license/cla` status | a legacy status, required on `main` |
| CodeQL (`security.yml`) | `pull_request`, schedule | check runs | |
| Dependabot | schedule | PRs | |

No workflow uses `pull_request_target`. `health-radar-comment.yml` uses
`workflow_run`, the pattern the Claude action's security notes also
recommend for fork input.

### 3.4 Headless invocation: what exists and what is official

**Nothing is configured.** No workflow references `anthropics/claude-code-
action`, the repository has **zero Actions secrets** (no `ANTHROPIC_API_KEY`,
no `CLAUDE_CODE_OAUTH_TOKEN`), and the Claude GitHub App is not installed
as far as the API shows (the installation endpoint needs an app token; the
repository settings page is the place to confirm). An environment named
`copilot` exists with no reviewers; nothing in the tree references it, and
its origin is unknown. Finding: name it or delete it before this layer adds
environments of its own.

**What is official, verified 2026-09-04 against
`code.claude.com/docs/en/github-actions`, the action's `docs/security.md`,
and `code.claude.com/docs/en/headless`:**

- The mechanism is `anthropics/claude-code-action@v1`. The `v1` tag pointed
  at commit `ef8bb1e43bf303cff727a1dd0b8837029fe982a2` (= `v1.0.215`, tagged
  2026-09-03) when read; the tag moves with every release, so
  `tests/test_workflows_pinned.py`'s 40-hex rule applies and the pin will be
  a commit, bumped on purpose.
- Two modes: interactive (`@claude` mention) and **automation** (a `prompt`
  input; runs on any event including `schedule`). Automation is the mode
  this layer uses. Results go to the run log unless the prompt has a tool
  that posts.
- `prompt` accepts a skill or custom-command invocation (`/name`), which is
  how the brief's "invoke `/fix-issue`, `/triage-issue`" maps, provided
  `actions/checkout` ran first so `.claude/` is on the runner. When the
  action runs against a PR it **restores `.claude/`, `CLAUDE.md`,
  `.mcp.json` and a fixed list of config paths from the base branch** before
  starting, so a PR cannot bring its own commands, hooks or policy. That is
  a property the design relies on and must test.
- `claude_args` carries CLI flags: `--max-turns`, `--model`,
  `--allowedTools` (permission-rule syntax, e.g. `Bash(gh issue view:*)`),
  `--append-system-prompt`; `settings` takes a settings JSON with
  `permissions.allow`/`deny`. A plain-text prompt has **no shell and no
  GitHub access until granted**; a skill's `allowed-tools` frontmatter can
  grant them.
- **Who can trigger**: on issue and PR events the triggering actor must have
  write access, or be listed in `allowed_non_write_users` (which then
  requires passing `github_token: ${{ secrets.GITHUB_TOKEN }}` and
  restricting tools). **This means a triage-on-open job for issues filed by
  the public does not run through the action's own trigger unless
  `allowed_non_write_users` is used, or the job is decoupled from the actor
  (a `schedule` or `workflow_dispatch` run, which skip the actor check, or a
  `workflow_run` chained from a read-only first stage).** The design must
  choose one and say why. Bots are rejected unless named in `allowed_bots`,
  and **allowed bots are not permission-checked**, which matters for
  Dependabot-triggered evaluation.
- Authentication: `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` as a
  repository secret, or OIDC workload-identity federation (no long-lived
  secret; needs `id-token: write`). GitHub access defaults to the Claude
  GitHub App's short-lived, repo-scoped token; the App's permission set is
  broad (**Actions, Checks, Contents, Discussions, Issues, Pull requests,
  Repository hooks, Workflows: all read and write**), cannot be accepted in
  part, and the documented narrow alternative is a **custom GitHub App with
  Contents, Issues and Pull requests only**. Given principle 2 (nothing
  headless modifies workflows or secrets), the audit's reading is that the
  shared App's token is over-privileged for this repo and the custom-App or
  `GITHUB_TOKEN` route is the one to design for; Phase 3 decides.
- On a public repository, `pull_request` runs from forks get no secrets, so
  no fix or evaluation job can run on a fork PR by construction; the
  action's own guidance for fork input is `workflow_run` with an actor check
  on the upstream run, and "do not check out an untrusted ref into the
  workspace root".
- The action strips HTML comments, invisible characters, image alt text and
  hidden attributes from inbound text and says plainly that "new bypass
  techniques may emerge"; `include_comments_by_actor` allowlists whose
  comments reach the model. Neither replaces the policy's own preamble.
- The CLI route for anything not wrapped by the action: `claude -p` with
  `--permission-mode dontAsk` (deny everything not allow-listed),
  `--permission-prompts none` (unattended; denies instead of waiting),
  `--allowedTools`, `--max-turns`, `--output-format json` (carries
  `total_cost_usd` per run, the audit trail's cost field), `--json-schema`
  for a structured verdict, `--append-system-prompt-file` for the
  policy preamble. ⚠ `--bare` (recommended for CI) **skips
  `.claude/commands/`, `.claude/agents/`, hooks and CLAUDE.md**, i.e. exactly
  the workflow layer; a headless run of `/fix-issue` must run non-bare in a
  checkout whose `.claude/` came from `main`.

### 3.5 Permissions model for Actions in this repository

| setting | value | consequence |
|---|---|---|
| `actions/permissions` | enabled, `allowed_actions: all`, `sha_pinning_required: false` | SHA pinning is enforced by our test, not by GitHub; Phase 4 may turn the GitHub setting on as well |
| default `GITHUB_TOKEN` permissions | **read** | every write is opted into per job, which is already the repo's practice |
| `can_approve_pull_request_reviews` | false | a workflow token cannot approve a PR; required reviews (none configured today) could not be satisfied by an agent |
| fork PR approval | `first_time_contributors_new_to_github` | first-time-to-GitHub fork authors need a maintainer click before any workflow runs on their PR |
| secrets | none | the API key this layer needs does not exist yet; it is the first thing Phase 4 item 1 adds, and it is the only secret |
| environments | `pypi` (2 reviewers), `testpypi` (1), `github-pages` (1), `copilot` (0) | the release path is behind human approval; the agent must never be granted an environment with publish scope |
| branch protection on `main` | strict, `enforce_admins`, required conversation resolution, required checks = every PR-gate job by name + `license/cla` | ⚠ **an agent-authored PR must carry a `license/cla` status.** CLA Assistant posts it for the PR author's account; whether it signs for the Claude GitHub App or a bot account is unverified and is a Phase 4 item 1 question, because without it no agent PR can merge even by a human's click |

**Forks cannot trigger a write-capable job**: `pull_request` from a fork
runs with a read-only token and no secrets on a public repo, and the repo
uses no `pull_request_target`. The one `workflow_run` consumer
(`health-radar-comment.yml`) gates on `workflow_run.event == 'pull_request'`
and posts only its own rendered artifact. This must stay true after Phase 4:
every new job that has write permission must trigger on `issues`,
`schedule`, `workflow_dispatch`, `workflow_run` with an actor check, or a
same-repo `pull_request`, and never on a fork ref checked out at the root.

## 4. What this audit changes about the brief's assumptions

1. **Volume is small and bursty.** Median 40 issues a month, two bursts of 80+
   driven by QA campaigns. A daily sweep and a per-job cap of a handful of
   fix attempts covers the steady state; the budget design should be shaped
   for the burst (thirteen findings in one issue, split at triage).
2. **Response time is already hours.** A first response at median 3.1 h and a
   close at 4.6 h leaves the agent little to win on latency; what it wins is
   the maintainer's time per item, not the reporter's wait. The digest
   should measure maintainer minutes, not time-to-first-response.
3. **Security reports come in public, inside QA passes.** The classification
   rule "anything mentioning a vulnerability, exploit, credential or data
   exposure is security regardless of other signals" is the one rule that
   would have changed an outcome on the record (#509, #508, #447, #444),
   and it must fire on a single finding inside a multi-finding report.
4. **There has never been a grammar update.** The grammar path is designed
   from #382's reasoning, not from an incident, and its verification in
   Phase 5 must be a simulation.
5. **The trigger model is the design's first decision.** The official action
   refuses issue events from actors without write access; every reporter in
   the history is such an actor. Triage-on-open therefore runs either
   through `allowed_non_write_users` (a list, which does not scale to 112
   authors) or through a decoupled trigger. The audit recommends the
   decoupled form: an `issues` event with a read-only job that records the
   item, and a `schedule`/`workflow_dispatch` runner that processes the
   queue with no external actor in its context.
6. **Two things must exist before item 1 of Phase 4 can run**: an API
   credential (there are no secrets), and an answer to the `license/cla`
   question for agent-authored PRs.

## 5. Findings carried to `docs/inbound/FINDINGS.md` when it exists

- IN-1: the `qa` label named by `multi_finding_report.md` does not exist.
- IN-2: the `copilot` environment has no owner and no reference in the tree.
- IN-3: `license/cla` is required on `main` and it is unknown whether an
  agent-authored PR can receive it.
- IN-4: private vulnerability reporting could not be verified enabled from
  the API; zero advisories have ever been filed while six security-shaped
  issues were filed in public.
- IN-5: `health-radar-comment.yml` posts an artifact from an untrusted run
  with a write token (pre-existing; the payload is our own rendering).
- IN-6: `sha_pinning_required` is off at the repository level; the test
  enforces it, GitHub does not.
