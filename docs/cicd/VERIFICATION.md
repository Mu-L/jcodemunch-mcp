# CI/CD VERIFICATION (2026-09-03/04)

Every claim below names a run. Check summaries are quoted as the Checks tab
shows them (the annotation the reader sees without opening a log); the
underlying step summary carries the same lines as a table.

## 1. The gate runs and passes on a clean PR

PR #575 (`cicd/pr-gate-1` → `main`, the stage 1-3 workflow itself), final
head after the fixes in §4:

| stage | check | result | wall |
|---|---|---|---|
| 1 | `fast: harness fast tier` | pass | 1m07s (fast tier pytest 45 s, `suite.fast_seconds` observed 55-60 s) |
| 1 | `fast: format` | pass | 10 s |
| 1 | `fast: types` | pass | 26 s (`types.error_max` observed 369) |
| 1 | `fast: dependency audit` | pass | 24 s (`deps.vuln_max` observed 0 after the click bump) |
| 1 | `fast: secret scan` | pass | 18 s |
| 2 | `full: test (ubuntu-latest, 3.10-3.13)` | pass x4 | 2m43s-4m20s per leg |
| 2 | `full: test (windows-latest, 3.10-3.13)` | pass x4 | 8-10 min per leg; see C-9 |
| 3 | `package: install and handshake (ubuntu-latest)` | pass | 26 s; wheel AND sdist installed into clean venvs, `HANDSHAKE PASS`, fixture indexed 9 files in python/typescript/javascript/go |
| 3 | `package: install and handshake (windows-latest)` | pass after the venv-path fix (§4) | |

PR #579 (stages 4-5) and #582/#583/#584 (main, nightly+security, release)
ran the same gate green on their heads, plus `bench: harness bench tier`,
`bench: token benchmark` (cached corpora; the PR comment posted), `done:
changelog`, `done: version pins`, `done: tool surface documented`.

## 2. The gate blocks on each deliberate failure

Each probe is a one-commit branch off the gate branch, opened as a PR into
it so the gate runs on the probe's merge ref.

| probe | PR | expected block | what the Checks tab shows |
|---|---|---|---|
| `ruff` F821 appended to `src/jcodemunch_mcp/install_layout.py` | #576 | stage 1 | `fast: harness fast tier` FAIL — annotation `fast tier: ruff check src/ :: Found 1 error.` with the offending line; stages 2-3 skipped (run 33819672929) |
| a failing test appended to `tests/test_hardening.py` (not in the fast tier) | #577 | stage 2 | stage 1 all pass; every `full: test (<os>, <py>)` leg FAIL — annotation `full tier: pytest :: FAILED tests/test_hardening.py::test_ci_probe_deliberate_failure - AssertionError: deliberate failure to prove stage 2 blocks`; stage 3 skipped (check-run 100863289192) |
| console-script entry point renamed to a missing symbol in `pyproject.toml` | #578 | stage 3 | first runs: every windows `full:` leg failed on `suite.full_seconds` (the C-9 finding, not the probe); after the platform Floor, stages 1-2 pass and `package: install and handshake (<os>)` FAIL on both OSes (`jcodemunch-mcp` cannot start: the handshake never completes) |
| a `src/` change with no CHANGELOG line and no label | #580 | stage 5 | `done: changelog` FAIL — annotation `changelog :: src/ changed without a CHANGELOG entry (Definition of Done 3)`; summary names the changed file (check-run 100860109576) |
| one tool renamed, README/CLAUDE.md/CHANGELOG untouched | #581 | stage 5 | `done: tool surface documented` FAIL — `tool surface :: the tool surface changed without the documentation Practice 1 requires`, summary lists `added ['get_decorator_census_probe'], removed ['get_decorator_census']` and the three missing docs; also `done: changelog` FAIL and `fast: harness fast tier` FAIL (the surface pins: `test_route_recall_artifacts_are_fresh`), which is why the `done:` jobs do not depend on stage 1 (check-runs 100861938810, 100861938515) |

A secret-scan probe was NOT run: committing a live-looking credential to a
public branch to prove gitleaks fires is the leak it exists to prevent;
gitleaks' own test corpus covers it and the job ran (18 s) on every PR.

## 3. Legibility

The first probes showed only `Process completed with exit code 1` for a
lint or test failure, because only Floor verdicts were annotated. The
harness now emits `::error title=<what>::<first failing ids>` for pytest,
ruff and corpus-checksum failures under `GITHUB_ACTIONS`, and every job
appends its verdict table to the step summary. Quoted above.

## 4. Failures found by building, fixed in the same series

| # | what CI saw | fix |
|---|---|---|
| 1 | `fast: format` failed on every stacked PR: the stage 4-5 scripts were written after the format pass | formatted; the gate caught its own author |
| 2 | `fast: harness fast tier` failed on `tests/test_subprocess_encoding_guard.py` for `pr_bench_comment.py` | `encoding="utf-8", errors="replace"` on three calls |
| 3 | every windows `full:` leg failed `suite.full_seconds` at 479-554 s against a 360 s Floor | C-9: platform-scoped Floor `suite.full_seconds_ci_windows` = 1033 |
| 4 | `package: install and handshake (windows-latest)`: `No virtual environment ... for path D:\a\_temp/pkg/Scripts/python` | `uv pip install --python <venv dir>`; `$B/python` has no `.exe` on windows and uv does not resolve it (bash does) |
| 5 | the `done:` jobs were skipped whenever stage 1 failed, so a surface probe that also breaks a pin test never reached them | `done:` jobs have no `needs` |
| 6 | `.github/actions/health-radar/action.yml` used `actions/setup-python@v5` by tag | pinned (C-7; tagging the action is jjg's) |
| 7 | `gh workflow run release.yml --ref cicd/release` → HTTP 422 | C-8: dispatchable only from the default branch; the dry run is the first act after the merge |

## 5. Merge-to-main, nightly, security, release

- `main.yml` and `nightly.yml` cannot run on a PR (their triggers are push
  to main and schedule). Both were exercised by `workflow_dispatch` from
  their branch heads where the trigger allows it, and their gating command
  lines are identical to the PR gate's, which did run. See §6 for what ran
  after the merge.
- `security.yml` (CodeQL python + actions) ran on the PRs that carry it.
- `release.yml`: dry run after the merge, §6.

## 6. After the merge (filled in as it happens)

- Merge order: #575 → #579 → #582 → #583 → #584 (each retargeted to `main`
  after its base merged).
- Branch protection: the 12 old contexts replaced by the 17 new names in one
  call; `enforce_admins` on; `strict` on; conversation resolution on;
  auto-merge and delete-branch-on-merge on.
- Direct push to `main` attempted and rejected: see the transcript below.
- Release dry run dispatched with `version=1.108.316 dry_run=true` from
  `main`: see the run link below.

### 6.1 What actually happened

- Merges: #575 (stages 1-3) and #583 (nightly + security, whose branch was
  stacked on the stage 4-5 and main-workflow branches, so #579 and #582
  landed with it and were closed without a separate merge); then branch
  protection; then #585 (retire the five old workflows: the first PR to
  pass with `enforce_admins` and `strict` on, 25 checks, CLEAN) and #584
  (release workflow), which needed `update-branch` twice under `strict`,
  three CodeQL review threads answered (C-10) and one CLA webhook redelivery
  (C-12) before it read CLEAN. No `--admin` merge was used at any point.
- Protection (`gh api .../branches/main/protection`): 21 required
  contexts (`license/cla` + the 20 PR-gate job names), `strict: true`,
  `enforce_admins: true`, `required_conversation_resolution: true`,
  `allow_force_pushes: false`, `allow_deletions: false`. Repo:
  `allow_auto_merge: true`, `delete_branch_on_merge: true`. Environments
  `testpypi` and `pypi` (protected branches only; `pypi` has a 5-minute
  wait timer).
- Direct push to `main`, attempted from a one-line commit on a probe branch:

  ```
  remote: error: GH006: Protected branch update failed for refs/heads/main.
  remote: - 21 of 21 required status checks are expected.
   ! [remote rejected] HEAD -> main (protected branch hook declined)
  ```

- `main.yml` ran green on every merge commit (f497e2f, 06e7d5e, 6c1e485):
  full witness + online bench, artifacts uploaded, no regression issue.
- Release dry run from `main` (run 33826479351, `version=1.108.316
  dry_run=true`): pre-flight, build, test pypi (listed, not uploaded), smoke
  from the built wheel on ubuntu and windows (`HANDSHAKE PASS`, fixture
  indexed, tool count 90 == pre-flight 90), tag (printed, not created),
  pypi SKIPPED by the `dry_run` condition, post-publish smoke on both OSes,
  github release (notes rendered from the CHANGELOG block, sigstore signing
  ran), mcp registry (`mcp-publisher login github-oidc` succeeded on the
  runner; `validate` ran; nothing published). The pre-flight table showed
  `tag` and `pypi` as FAIL-not-blocking (1.108.316 exists, as expected for
  a dry run of a released version) and `ci` as FAIL-not-blocking for the
  reason recorded as C-13, fixed in the follow-up PR and re-proven there.

### 6.2 Runtime against the DESIGN budget

| event | budget | measured |
|---|---|---|
| PR, stage 1 failure | ~2 min | 1-2 min (lint probe: 1m07s to FAIL) |
| PR, all stages, wall | ~15 min | 25-30 min under queue pressure from 10 concurrent PRs; the long pole is the windows full-tier legs at 8-10 min each, then packaging and bench behind them |
| Merge to main | ~12 min | 6-8 min (`main.yml`) |
| Release dry run | ~8 min | 7 min |
| Nightly | ~20 min | not yet run (04:00Z) |

The PR budget is revised to ~25 min wall when windows legs are queued; the
runner-minute estimate (~95) held. Two levers exist if that matters: stage
3-5 already start after the ubuntu 3.12 leg, and the windows matrix could
drop to two Python versions on PRs and keep four on the nightly.

### 6.3 Second and third dry runs

- Run 33827504322 (after #586): every job green again; the pre-flight's
  `ci` line read `gate jobs absent on HEAD` — the C-13 fallback was asking a
  PR-ref question of a main commit (C-14).
- Third dry run (after the C-14 fix): the `ci` line is expected to read
  `check-runs on HEAD concluded success, including ['main: harness full
  (ubuntu, 3.12)', 'main: harness bench (online)']` and PASS; recorded below
  by the session that dispatches it.
