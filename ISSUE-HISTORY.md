# jcodemunch-mcp — issue and PR history

Rotated out of `CLAUDE.md` on 2026-08-21 under Maintenance Practice 5, verbatim.
These entries are CLOSED history: every one names a date, and the tracker state
in them expired the moment it was written.

⚠⚠ **Never quote an open-issue or open-PR count from this file.** Run the query.
The block below already contained one internally contradictory count when it was
rotated (a `ZERO open issues` line dated 2026-07-28 sitting above a `#375 REOPENED`
entry dated 2026-07-26). That is the failure this warning exists for.

The standing lessons drawn from these entries live in `CLAUDE.md` under
**Standing lessons**; each names a date you can grep for here.

---

**2026-08-18: #488 DECIDED BY JJG — OPTION A, "explicit config outranks the
zero-config ONNX default", with disclosure.** NOT YET IMPLEMENTED; queued behind
#495. `_detect_provider` will check `embed_model` / `JCODEMUNCH_EMBED_MODEL` and
the cloud key pairs BEFORE returning `local_onnx` at priority 0, the result will
name the active provider and why, and the `config.jsonc` comment gets corrected.
⚠⚠ **This was only safe to decide because #500 shipped first.** Making explicit
config win makes provider changes MORE frequent, and before #500 each one left
the store holding two vector widths with the newer half silently excluded from
search. **The migration hazard that looked like a cost of option A was a
pre-existing defect option A would merely have made more likely to fire.**
⚠ **Option C (local-only per #302) was REJECTED on a factual error in the
report**: branches 1-3 are not vestigial, only SHADOWED, and only when
`[local-embed]` is ALSO installed. `[semantic]` without `[local-embed]` uses
branch 1 today and it works. **Say that to the reporter — their largest
suggestion rests on it.**
⚠ Disclosure is not optional in A: a caller whose provider changes needs to see
`model_changed_from` / `rebuild_reason` (#500's fields) rather than discover a
re-embed by watching the clock.

**2026-08-20: #447 (@elfrost) IMPLEMENTED BY US via PR #519 at timebox expiry;
#443 CLOSED with credit.** `install-pack`'s pre-scan rejected a leading separator
and `..`, which is necessary and not sufficient: `C:/Windows/Temp/evil.txt`
carries neither, and `base / relative` DISCARDS `base` when `relative` is
absolute. `mkdir(parents=True)` ran BEFORE the write, so a hostile member created
directories outside the install root before any content existed. Unreleased.
⚠⚠ **THE PROVENANCE IS THE FIRST THING TO SAY, EVERY TIME.** elfrost found it,
analysed it and wrote a correct fix. We shipped our own pre-existing
`_safe_content_path` pattern applied to the call site that lacked it — an
INDEPENDENT path, not a clean-room copy — and said exactly that on both threads.
⚠ **Confinement by RESOLUTION, never by pattern.** A string test cannot finish
enumerating separator and drive spellings; resolving and comparing does not have
to. The pre-scan stays as an EARLY ABORT with the per-member check as the
authority — two checks, one authoritative, recorded at the call site.
⚠⚠ **The rule had THREE spellings already** (`security.validate_path` + a private
copy on `IndexStore` + another on `SQLiteIndexStore`) **and the new call site
would have been a fourth.** `security.resolve_within()` is the one definition now;
`SQLiteIndexStore` keeps its resolved-base cache by PASSING IT IN, so the hot path
survives without duplicating the rule to preserve it. A ratchet fails on a
`commonpath` anywhere else in `src/`.
⚠⚠ **THE FIRST REGRESSION TEST PASSED AGAINST THE UNFIXED SOURCE, AND THE
NON-VACUITY PASS WROTE A REAL FILE INTO A REAL WINDOWS SYSTEM DIRECTORY.** It
named the reported path verbatim, so the escape went OUTSIDE the directory the
assertion searched — invisible to `tmp_path.rglob`. **A test for an
ARBITRARY-WRITE defect EXECUTES that defect every time you prove it is not
vacuous, so the target must be somewhere the test OWNS.** Rebuilt against a
`tmp_path` sentinel; the artifact was deleted.
⚠ **The refusal is deliberately NOT platform-pinned.** `C:/...` is absolute on
Windows and an ordinary relative name on POSIX, where resolving it under the base
is CORRECT. Assert confinement; asserting that a string is refused writes platform
trivia into a security test.
⚠ **A second test of mine asserted an OS ACCIDENT** — that an embedded NUL fails
to resolve — and **passed serially while failing under xdist**, where the longer
worker temp path takes the other branch. The rule is that a RAISING resolve
refuses; which inputs happen to raise is the OS's business. Same tell as
Maintenance Practice 9: it stated a mechanism instead of an outcome.
⚠ Suite: **8083 passed, 17 skipped, 0 failed** + ruff clean, all 12 CI checks
green. 3 red at the call site, 1 red on the one-definition guard.
⚠⚠ **#443 cost EIGHT DAYS and SEVEN of our own conflicts and bought nothing.**
See policy 3a, now absolute at 24 hours.

**2026-08-20: the licence identifier is MAJOR-ONLY, and jdoc/jdata are synced.**
@marcelruhf is a PLATFORM CUSTOMER operating an allowlist against this
identifier; jjg's standing instruction is top-tier consideration, bounded by no
harm to the rest of the user base. Unreleased (jcm PR #521).
⚠⚠ **His cheapest-looking option was the one worst FOR HIM and that is the
reusable half.** Dropping the version entirely means a substantive re-licence is
INVISIBLE to every allowlist — the identifier keeps matching while the terms
change. **It buys us zero churn by moving risk onto the licensee.** Keeping
`-1.1` churns him for a typo. Major-only says the thing he needs: minor is
editorial, major means read it again.
⚠⚠ **WE HAD ALREADY BROKEN THAT PROMISE ONCE, and checking is what found it.**
`f3c925c` (2026-07-10) ADDED a redistribution and attribution obligation to
LICENSE condition 2 while the header stayed at `Version 1.1`. **Nothing failed,
because a version line is a CONVENTION and conventions do not fail builds.** So
the terms text is pinned by DIGEST: any edit fails, and clearing it forces the
substantive-or-editorial choice AT the edit rather than downstream. **The test
cannot make that judgement and does not try — it makes the judgement happen.**
⚠ **Do it NOW was part of the answer, not a separate question.** .288 is the ONLY
release that ever carried an identifier, and PyPI metadata is immutable per
version, so every later release widens the transition. **Deferring a metadata
decision for discussion is not free when the cost grows monotonically.**
⚠⚠ **The digest was RED on all four Ubuntu legs and GREEN on all four Windows
legs**: it hashed RAW BYTES, and git rewrites line endings on checkout, so it
pinned a property of the CHECKOUT rather than of the terms. **A licence says the
same thing in either encoding.** Normalise before hashing. Second
platform-shaped self-inflicted test defect in two days (the other was xdist).
⚠ **jdoc #122 / jdata #4 (same reporter) MERGED, and BOTH had held CI.** Only
`license/cla` was reported — the matrices had runs sitting `action_required` and
had NEVER run: four on jdoc, two on jdata. `fork-pr-contributor-approval` was
`first_time_contributors` on both; relaxed to match jcm, which fixed it
2026-08-13. **A setting fixed in one repo of a suite is fixed in one repo.**
⚠ **He ported #518's ratchet into both siblings unasked and his version is
BETTER**: mine asserted a version suffix EXISTS, his makes a `Version` line and a
suffix imply each other BOTH WAYS — those LICENSE files state no version, where
mine would have demanded one. Adopted back into jcm as #520. **Ours was right
only about this repo's accident.**
⚠ Policy 3a/3b now present in jdoc and jdata CLAUDE.md; they carried policy 3 as
a single line and had neither the 24-hour ceiling nor the held-run diagnosis.

**2026-08-20: #517 (@marcelruhf) MERGED; #518 finished it.** PyPI published the
entire LICENSE text as `info.license` because `license = { file = "LICENSE" }`,
so a commercial user could not allowlist us BY IDENTIFIER — there was no
identifier to allowlist. PEP 639 now:
`license = "LicenseRef-jCodeMunch-Dual-Use-1.1"` + `license-files`, classifier
dropped. Unreleased.
⚠ **Verified on BUILT ARTIFACTS, not on the diff**: `License-Expression` +
`License-File` at `Metadata-Version: 2.5`, LICENSE still at
`dist-info/licenses/LICENSE`, `twine check` green on both.
⚠⚠ **He could see ONE surface and we declare the licence on THREE.**
`.claude-plugin/plugin.json` and the mcpb manifest both said `LicenseRef-Dual-Use`
— no product prefix, no version — so an allowlist keyed on the identifier still
needed two entries. **That is the reported defect one surface over**, the same
shape as #515 the day before. mcpb now DERIVES it from `pyproject.toml`.
⚠ **The version suffix is load-bearing.** LICENSE 1.2 must produce a NEW
identifier, or an allowlist that approved 1.1's terms keeps matching terms nobody
read. `test_license_identifier_agreement.py` pins the suffix to the file's own
`Version` line. **Raised the recurring-cost trade-off with the reporter rather
than deciding it for him** — he is the one operating an allowlist.
⚠ **PyPI metadata is IMMUTABLE per version**, so none of this reaches PyPI until
the next release and 1.108.287 keeps the full text. Said so on the thread; a
contributor who fixes packaging metadata needs to know when it takes effect.

**2026-08-19: #515 (@rknighton) FIXED BY US via PR #516 — the reference table
gave the wrong default.** `CONFIGURATION.md`'s Tools row read `[]` while
`DEFAULTS["disabled_tools"]` ships `["test_summarizer"]`, so a reader expected
91 canonical tools in the schema and found 90. Unreleased.
⚠⚠ **FOUR SURFACES DESCRIBE THIS DEFAULT AND THE THREE THAT AGREE ARE THE
POINT.** The generated config template, the `config --init` comment and
`test_guide_respects_disabled_tools.py`'s pin all state it correctly; only the
reference page disagreed, and it is the page a user opens when a tool they
expected is missing from the schema. **A value pinned by a test can still be
mis-documented — the pin guards the value, not every claim about it.**
⚠ **`tool_tier_bundles` was wrong the same way and he scoped it out**: documented
`{}`, ships populated. He was right that nothing observable changes (set-identical
to the `_TOOL_TIER_CORE` / `_TOOL_TIER_STANDARD` fallback the row already
described, verified). Fixed anyway — a cell that is accidentally harmless is still
a cell that will be read, and leaving it would have forced the ratchet to carry it
as an unexplained exception.
⚠⚠ **`tests/test_configuration_md_defaults.py` is the deliverable**, written over
the TABLE rather than the two reported rows: it parses every `| Key | Type |
Default | Description |` block and compares each cell against `config.DEFAULTS`,
so the next key someone documents is covered on the commit that documents it.
3 red pre-fix, 63 green after. The cross-check over all 60 documented keys found
exactly the two he named — his "every other documented default matches" held.
⚠ **The exemption is load-bearing, not a hole.** `tool_tier_bundles` cannot be
inlined so its cell is prose, and the test asserts its repr is genuinely too long
to fit — a small wrong value cannot hide behind the same escape hatch — plus it
asserts the claim the prose makes rather than trusting it. **An exemption that
does not police itself is how the ratchet becomes the next defect's cover.**
⚠ Suite: **8067 passed, 17 skipped, 0 failed** + ruff clean, all 12 CI checks
green on the merged SHA. Same-tree collect 8084 with the new file / 8021 without
= exactly its 63.
⚠⚠ **#443 conflicted for the SEVENTH time, on a DOCUMENTATION merge.** Policy 3b
governs order and was unavailable — #443 is CLA-BLOCKED, so it cannot go first —
so we shipped and owned the resolution. `license/cla` SURVIVED this push
(`pending`, count=1 on the new head), which is a genuinely unsigned state and not
an erasure. **Read the status; the tally is 3 erased / 3 returned now.**
⚠ **`gh pr checkout` sets the branch's upstream to the FORK but `git push origin`
still means OUR repo** — pushing the resolution with `origin` created a stray
branch in `jgravelle/jcodemunch-mcp` instead of updating theirs, and the PR stayed
`CONFLICTING`. Push to the FORK REMOTE by name (`git push elfrost HEAD:<branch>`);
the tell is the PR not changing state after an apparently successful push.

**2026-08-19: #506/#507/#508/#509 (@rknighton) FIXED BY US via PRs #510/#511/#512.**
All four were filed at 00:24-00:25 and every one probes a surface ADJACENT to
something we shipped the day before. Unreleased.
⚠⚠ **THE SAME SHAPE THREE TIMES IN THREE DAYS, and it is the reusable finding:
we keep fixing the reported call site and leaving the mechanism.** #495 was a
second GENERATOR carrying its own copy of the filter; #509 a second CALL SITE
with its own containment check; #507 a second DERIVATION of the tool set. In
each the fix is one sentence — **ask the authority instead of reproducing its
logic** — and in each we had applied it only where it was reported.
**#506** — v1.108.286 filtered `### All tools` and left `### Quick start` as six
fixed strings no filter reached, so the guide could still instruct a caller to
run a disabled tool. ⚠⚠ **The previous fix scoped to the reported SECTION, and
so did its test**: `_advertised()` split on `### All tools` and inspected only
what followed, so it could not observe this section and would not have observed
the next. Now scans the whole document. Steps are DATA now, dropped whole and
RENUMBERED, with the shared `index_folder`/`index_repo` continuation filtered
per-tool.
**#509** — `index_file` picked the deepest containing `source_root` with NO
identity check, so a file from a nested independent clone was WRITTEN into the
parent's index. ⚠ The check is **imported from `resolve_repo`, not copied** —
which is the lesson AND which inherited #492's submodule boundary for free, so a
submodule path still resolves to the parent (his Case 3, untouched). ⚠ The
refusal NAMES the repository; falling through to "no indexed folder contains
this path" was wrong on the facts and pointed at the wrong remedy.
**#508** — `index_file` passes `repo=` to three config reads and nothing on that
path ever called `load_project_config`, so the overlay was empty and all three
resolved to GLOBAL config. ⚠⚠ **v1.108.286 threaded that keyword through six
sites (#491) without checking anything loads what it reads. A parameter that is
present and does nothing is indistinguishable from the defect it was added to
fix.** ⚠ Fixed at the ENTRY POINT, not by lazy-loading inside `config.get()` —
`load_project_config` does not cache a MISS, so a lazy load re-stats on every
read for any repo without a project file, on the hottest function in the tree.
**#507** — `_get_active_tools` rebuilt the active set from `tool_profile` + the
baked `_PROFILE_TIERS`, missing three inputs `tools/list` reads: the SESSION tier
override, `tool_tier_bundles`, and the `languages` gate on `search_columns`.
Measured 70 / 15 / 1 unmounted names. ⚠⚠ **The session-override case needs NO
configuration** — `announce_model` writes the session tier via
`resolve_model_to_tier`, and `jcodemunch_guide` is in `_ALWAYS_PRESENT_TOOLS` so
it stays reachable at every tier. ⚠ **Filtering is a SUBTRACTION**, so an empty
or failed build returns `None` = do not filter: a policy naming a few
unavailable tools beats a policy with no workflow left in it.
⚠⚠ **`tests/test_path_entry_point_invariants.py` IS THE DELIVERABLE of that
batch.** Written over the ENTRY POINTS rather than the two reported functions,
with `resolve_repo` and `index_folder` as the PASSING CONTROLS in each pair —
which is what proves an invariant achievable rather than aspirational. It read
2 failed / 2 passed against the pre-fix tree. **Write the ratchet before
concluding the reported list is the list** (#489 found 5 sites for a 3-site
report the same way).
⚠ **Two of my own guards matched PROSE, not code**: #507's first version matched
the literal `_PROFILE_TIERS` and failed on the COMMENT explaining why the helper
must not use it. Walk the AST — it cannot see comments. Same fix the `src.`
twin-import guard needed.
⚠ Suite: **7999 passed, 17 skipped, 0 failed** on `main` + ruff clean.

**2026-08-18: #488 (@pnm-jgb) FIXED BY US via PR #505 — an explicit local model
now outranks the zero-config default, and the NARROWING is the entry.**
Unreleased.
⚠⚠ **JJG DECIDED "OPTION A"; WHAT SHIPPED IS A IN ONE BRANCH ONLY, AND HE
APPROVED THE NARROWING AFTER IT WAS SURFACED.** Full A turned
`tests/test_paid_embeddings_optin.py` RED, and that file is not incidental — it
exists because jdocmunch's resolver auto-selected OpenAI from an ambient
`OPENAI_API_KEY` and began **billing a remote account and shipping the indexed
corpus off the machine**. jcm's second line of defence IS that ONNX wins before
any cloud branch is reached. **A developer with `[local-embed]` and an exported
`OPENAI_APIKEY`+`OPENAI_EMBED_MODEL` would have silently started paying per call
and sending their source off the box.**
⚠⚠ **THE ASYMMETRY THE ISSUE NEVER ADDRESSED, and the reusable half:
`embed_model` is FREE and ON-MACHINE; Gemini and OpenAI are PAID and REMOTE.
Promoting the first costs a re-embed. Promoting the others costs money and
exfiltrates the corpus. A principle stated over a set ("explicit beats default")
can be right for part of the set and wrong for the rest — check what each member
costs before applying it uniformly.**
⚠ **A RED TEST IS SOMETIMES THE SPEC.** The instinct on 33 reds and one
money-safety red is to fix the tests. Here one of them was the design document
and the other 33 were reporting a real regression. **Read the docstring of a
failing test before assuming it is stale.**
⚠⚠ **The usability probe was WRONG on its first pass and 33 tests caught it.**
Probing `sentence_transformers` importability UNCONDITIONALLY meant that on any
machine without the package `JCODEMUNCH_EMBED_MODEL` selected nothing, so the
caller got a bare `None` instead of the actionable `pip install
'jcodemunch-mcp[semantic]'` error. **The probe now decides PRECEDENCE, never
SELECTION**: an uninstalled backend does not displace a WORKING ONNX install,
but with no ONNX the setting is selected as before.
⚠ `provider_reason` + `provider_skipped` added to `embed_repo`'s result: an
explicit setting we cannot honour is DISCLOSED, never dropped. Silently ignoring
it is the reported defect; silently failing on it at embed time is that defect
with a louder symptom.
⚠ **Option (4) from the report (remove branches 1-3 + the `[semantic]` extra +
~5 GB of torch) was DECLINED ON A FACTUAL ERROR IN THE REPORT** — those branches
are not vestigial, only SHADOWED, and only when `[local-embed]` is ALSO
installed. `[semantic]` without `[local-embed]` uses branch 1 today and it works.
**Said so on the thread; his largest suggestion rested on it.**
⚠ **This change was only possible because #500 shipped in .285.** Making explicit
config win makes provider changes more frequent, and before .285 each one split
the store silently. **The migration hazard was a pre-existing defect the change
would merely have made more likely to fire.**
⚠ `tests/test_explicit_embed_model_wins.py` (12), 6 red pre-fix **but only TWO
behavioural** — the other four fail because `_detect_provider_detailed` does not
exist there, which is a signature fact and not evidence. **Report that split;
"6 red" alone overstates it.** The 6 passing both sides are the money-safety
class and the wrapper-shape controls.
⚠ Suite: **7976 passed, 17 skipped, 0 failed** + ruff clean; +12 over .285's
7981-after-#495.

**2026-08-18: #504 (@lsg1103275794) VERIFIED, TIMEBOXED TO 2026-08-19, NOT YET
FIXED.** Repeat `index_folder` on a GIT ROOT never reaches the incremental
no-change path: the v1.96 collision guard at `index_folder.py:2224` is
`if _existing_source_root == _git_root:` with NO `walk_prefix` test, so a
full-root re-walk assigns `_merge_with_existing` and the incremental branch at
`:2402` (gated on `_merge_with_existing is None`) is unreachable. **Every
scheduled freshness check rebuilt the whole corpus.** Reproduced at .285.
⚠ **He offered to PR and sign the CLA; we said yes and posted the window with
the default (we implement + credit at expiry).** First-time contributor.
⚠⚠ **NOT a one-line fix and he said so BEFORE writing it** — `and walk_prefix`
alone breaks `test_full_root_walk_after_subdir_replaces_everything`, because a
full-corpus incremental diff cannot be layered onto a `source_roots` marker that
is still partial. His account: one full rebuild establishes `source_roots ==
[""]`, after which repeat root walks take the no-change path. **That is a
DISCLOSED MIGRATION and must reach the CHANGELOG, not be found by a user whose
first post-upgrade index is unexpectedly slow.**
⚠ **It makes `_refresh_git_head_if_advanced` fire MORE OFTEN** (no-change runs
finally happen), which is #493's ground from .285. Correct in `index_folder`
precisely because that path walks the whole corpus — **verify in review, do not
assume.**
⚠ Measured by him: 5.0-5.7s -> 1.58s on 1,132 files / 9,926 symbols. **His
machine, his number; do not transcribe as canonical.**
⚠ **Droppable from the release if it needs care.** It is a PERFORMANCE fix — the
index produced is correct, just rebuilt needlessly — and #447's SECURITY fix must
not wait behind it.

**2026-08-18: #495 (@rknighton) FIXED BY US via PR #503 — the guide advertised a
tool the same process refuses to run.** Unreleased.
⚠⚠ **AT SHIPPED DEFAULTS, no config file and no env overrides.**
`disabled_tools` ships `["test_summarizer"]` and
`_generate_claude_md_snippet` walked a static constant, so the guide named it,
`tools/list` omitted it, and `call_tool` rejected it before the handler ran.
**Reachable out of the box is what makes this worth a release rather than a
note.**
⚠⚠ **THE FILTERING ALREADY EXISTED AND A SECOND GENERATOR WALKED AROUND IT** —
`e086e9a` added it to `cli/init.py` for #242, and `server.py`'s generator never
got it. **Reused `_get_active_tools`; a third copy is how the first two
drifted.** Same shape as #491 (the guard existed, the call sites bypassed it) and
the `src.jcodemunch_mcp` twin sweep.
⚠ **Widened past the reporter's scope DELIBERATELY and said so on the PR**: they
scoped to `disabled_tools` correctly (a profile-hidden tool stays dispatchable,
so it costs context not failure), but the tool's own description promises to
match "surface, tier and disabled_tools", and `tier` IS the profile. Filtering
one and not the other leaves the description making a claim the code does not
keep.
⚠⚠ **`tests/test_config.py::test_generate_full_snippet` ASSERTED THAT EVERY
CANONICAL TOOL NAME APPEARS, so it could only pass WHILE THE BUG EXISTED.**
`test_summarizer` is canonical and disabled by default. **Third test this release
found asserting the behaviour it should have prevented** (after
`test_embed_drift.py`'s literal wording and my own two in #489). **When a fix
turns an old test red, read whether the test was encoding the defect before
"fixing" the code back.**
⚠ `tests/test_guide_respects_disabled_tools.py` (9), 5 red pre-fix; the four
constraints include a PIN ON `DEFAULTS["disabled_tools"]` so the issue's premise
cannot silently change out from under the case.
⚠ Suite: **7964 passed, 17 skipped, 0 failed** + ruff clean; +9 over .285's 7972.

**2026-08-18: #489 (@pnm-jgb) FIXED BY US via PR #502 — the tool schema
advertised three key-requiring providers and hid the free one.** Unreleased.
⚠⚠ **The `semantic` PARAMETER DESCRIPTION is the expensive site and the harm is
invisible from outside.** It is not documentation a human browses — it is the
tool schema, and the ONLY information an agent has when deciding whether to set
`semantic: true`. An agent reading "requires one of three env vars" against an
environment with none set correctly concludes semantic search is unavailable and
never tries it, **on a machine where it works for free**. No error, no warning,
no degraded result: **the inverse of a false positive, where the tool
under-reports its own function.**
⚠⚠ **THE REPORT NAMED THREE SITES; THE RATCHET FOUND FIVE.** The two extras were
only visible once a test asserted the PROPERTY instead of the instances: the
`embed_repo` TOOL DESCRIPTION in `server.py` (equally agent-facing, same
omission) and `retrieval/embed_drift.py`, whose own copy named the bundled
encoder **LAST**, behind the two that bill per call. **Write the ratchet before
concluding the reported list is the list.**
⚠ All five now derive from `embeddings/advice.py`; `_LOCAL_FIRST` leads both
strings, mirroring `_detect_provider`'s priority so advice and resolver cannot
disagree about which wins. Option (3) from the report — a schema stating the
RUNTIME fact rather than setup instructions — is NOT shipped; noted on the PR
rather than dropped.
⚠⚠ **MY BUDGET WARNING WAS WRONG AND MEASURING IS WHAT CAUGHT IT.** I told jjg to
watch the hard 4,000-token `core_compact` ceiling (10 tokens of headroom) and was
ready to trim a description. **`semantic` is in `_COMPACT_STRIP_PARAMS` and never
reaches the compact schema at all** — live `core_compact` is **3,990 before and
after**. A test pins that, so if `semantic` ever stops being stripped the budget
question returns visibly. **Measure the constraint before paying for it.**
⚠⚠ **`tests/test_embed_drift.py` PINNED THE LITERAL OLD WORDING, which is HOW
that site kept a stale copy** — a test keyed to one spelling of a sentence guards
the spelling, not the behaviour. **My own ratchet had the identical defect on its
first pass** (matched `"No embedding provider is configured"` WITH the `is`, and
caught `embed_drift` only by luck via a different clause), and **my site-2 test
asserted on the CONSTANT rather than on `search_symbols`** — true the moment the
constant exists, so it checked the fix instead of the site and passed against a
tree where that site was still stale. Corrected; it is now among the pre-fix
reds, and was not before. **Three instances of one mistake in one change.**
⚠ `tests/test_embedding_provider_advice.py` (10), 4 red against the pre-fix
CONSUMERS with `advice.py` present — stashing the module too only proves it is
new. **Keep the new module and revert the call sites; that is the pass that
means something.**
⚠ Suite: **7955 passed, 17 skipped, 0 failed** + ruff clean; +10 over .285's 7962.

**2026-08-18: #443 resolved a THIRD time, still ours.** v1.108.285 plus #489 both
touched the `[Unreleased]` block. Same resolution, suite **7961/17/0**, +6 =
exactly elfrost's tests, all 11 real CI checks green on the merge ref;
`license/cla` PENDING is the only blocker.
⚠⚠ **CLA erase-on-push tally, measured across five resolutions of #443: ERASED 3 times; RETURNED on its own twice; on 2026-08-19 it did NOT return within 5 minutes and was still absent when we stopped watching.** So the "our push provokes it back" note is a TENDENCY, not a remedy. ⚠ It does not block the CONTRIBUTOR — signing posts a fresh status against the current head — but the PR then shows eleven green checks and NO cla row, which reads as "done, waiting on them" and is the opposite. **Say so on the thread every time**; do not close+reopen to chase it (1 success / 2 failures, and it notifies them for nothing).
⚠ **A comment was posted BEFORE CI confirmed it** ("everything green except
license/cla"). It held, but it was a prediction at the time. Post the claim after
the run, or say it is expected rather than observed.

**2026-08-18: #491 (@rknighton) FIXED BY US via PR #499 — the two exclusion
opt-outs never read the project config that documents them.** `security.py` read
`exclude_skip_directories` / `exclude_secret_patterns` without `repo=`, so the
project overlay was skipped and the documented per-project opt-out did nothing.
Unreleased; see CHANGELOG `[Unreleased]`.
⚠⚠ **The COMMENTS are what make it a defect rather than a missing feature.** The
note above the skip list says these are ordinary English words that can name a
real package, "which is why `exclude_skip_directories` exists"; `is_secret_file`'s
docstring claims it applies the project overrides ONE LINE above the global-only
read. **Both described an intent the code did not implement** — same shape as
#500's promise-without-detection, found the same day.
⚠ Nothing surfaces it: `discovery_skip_counts` gives `skip_dir: 2` with no
directory or rule name, and the pruned path goes to `logger.debug`.
⚠ **FOURTH report of one shape** after #300 / #187 / #304, and **#301 audited
~40 call sites for exactly this, listed `get_extra_ignore_patterns` as fixed and
named neither of these**; v1.108.197 then fixed the three `max_*` resolvers and
left them too. **A fifth audit finds a fifth instance; the ratchet finds it on
the commit that introduces one.**
⚠ **Signature-only would have been a FALSE GREEN** — adding the parameter and
leaving callers bare changes nothing observable, so the call-site check walks the
AST, not the signature.
⚠ **`index_repo` is exempt BY NAME, not by omission**: a project config is found
by walking up from a LOCAL path and a GitHub tree has no checkout, so passing the
owner/repo id would imply a lookup that cannot succeed. This is a stated
DEVIATION from the reporter's acceptance criterion 5, said so on the PR.
⚠ `tests/test_security_exclusions_are_project_overridable.py` (13), all red at
`b85ef61` — but **three are constraints, red only because `repo=` is not a
parameter there**, so each also asserts the no-argument form. **Do not report
"all red" without that distinction; it overstates the evidence.**

**2026-08-18: #500 FILED AND FIXED BY US via PR #501 — a promise in a comment
with no code behind it, found while checking whether #488 was safe to ship.**
`embed_repo`'s `# Detect dimension mismatch — if the stored model differs, force
a rebuild` implemented NO detection: `stored_dim` only seeded `dim`, nothing
compared stored model to active, and `set_dimension` fired only when
`dim is None` (first-ever embed). A model change wrote new-width vectors beside
the old under a meta row naming the first.
⚠⚠ **THE CONSEQUENCE COMPOUNDS AND IS SILENT.** `EmbeddingMatrix` infers width
from the FIRST row and drops the rest, and the inferred width follows the
majority of PRE-EXISTING rows — so **every symbol embedded after the change is
excluded from semantic search, forever, and the gap grows with every new file.**
Measured `{384: 6, 768: 1}` with meta reporting 384. A recall failure that reads
as a finding.
⚠⚠ **THE READ PATH IS NOT THE DEFECT AND WAS LEFT ALONE.** `_build`'s exclusion
is a faithful port of what `_cosine_similarity` did before the matrix existed and
its comment says so. **Fixing the consumer would have HIDDEN the producer** —
the fix must go where the mixed store is CREATED. Same lesson as #493's write:
find what was proven, not what was written.
⚠ **Unknown is not a change**: a store with no persisted model name must NOT
force a rebuild, or every existing user is billed a full re-embed for a model
that may be identical.
⚠ **`stored_dim` is cleared inside the `force` branch, which REPAIRS A SECOND
BUG nobody reported**: the pre-existing `task_type` force path cleared the store
and left `dim` seeded, so the `dim is None` gate never re-fired and the meta kept
advertising the old dimension against fresh vectors.
⚠ **`skipped_dim_mismatch` was computed, stored on the object and read NOWHERE**
(`grep` found only its three defining lines). **A count that exists and is
discarded is the same defect as not counting.** Now surfaced as
`_meta.semantic_partial` + `channels.semantic: "partial"`, because the producer
fix does not heal stores already mixed.
⚠ **`evidence/capability.py` has called `get_model()` since v1.108.221 behind a
`type: ignore` and a bare `except`**, so the capability certificate reported
`model: "unknown"` for EVERY repo. **Found by adding the method, not by reading
the call site** — a bare except around a `type: ignore` is a permanent silent
failure by construction.
⚠⚠ **THIS IS THE BLOCKER ON #488 AND THAT IS WHY IT WAS FILED SEPARATELY.**
Making explicit config outrank the ONNX default makes provider changes MORE
frequent, and until now each one silently degraded the index. **The "migration
hazard" that looked like a cost of #488's option A was a pre-existing defect
option A would merely have made more likely to fire.** Check whether a hazard is
introduced or merely exposed before pricing it against a design choice.
⚠ `tests/test_embedding_model_change.py` (9), 8 red at pre-fix (2 of those are
signature-only reds); the same-model no-rebuild control passes both sides.

⚠⚠ **PROCESS, MEASURED THIS SESSION: a push is the RELIABLE way to re-provoke a
missing `license/cla`; close+reopen is NOT.** #499 opened with **zero** statuses
on its head (the #479 shape — the bot never fired, which reads identically to
our-push-erased-it). Close+reopen left `count=0`; `git commit --amend --no-edit`
+ force-push restored it `success` within a minute. **That is now 2 failures and
1 success for close+reopen and 2 successes for a push.** ⚠ It also blocks the
merge for real now that `license/cla` is required (3d), so an unfired bot on OUR
OWN PR presents as `BLOCKED` with 11 green checks.
⚠ **Batching worked**: #490/#491/#492/#493/#500 were all merged before touching
#443, and it was resolved ONCE instead of five times. That is the lever policy 3b
leaves when the contributor PR is BLOCKED and cannot go first. `license/cla`
SURVIVED this push — the opposite of the previous one, so **read the status, do
not predict it**.

**2026-08-18: #493 + #492 (@rknighton) FIXED BY US via PRs #496 / #498.**
Unreleased; see CHANGELOG `[Unreleased]`.

**#493 — `index_file` advanced the repo `git_head` after proving one file.**
`repo_is_stale` is "index SHA differs from live HEAD", so refreshing one file out
of a two-file commit CLEARED staleness for the file never refreshed, and
`get_file_content` served commit-A content reading `channels.index: fresh`
against a clean tree.
⚠⚠ **THE WRITE IS NOT THE DEFECT; WHAT HAS BEEN PROVEN BEFORE IT IS.**
`index_folder._refresh_git_head_if_advanced` makes the IDENTICAL write on a
no-change run (#330) and is CORRECT there, because that run walked the corpus.
**Two calls, one write, opposite correctness.** The reporter drew that
distinction himself and the fix is built on it — a diff of the two functions
would have shown nothing.
⚠ Fix is one `git diff --name-only --relative` against the stored head; advance
only if every other moved path is one the index neither carries nor would index.
`--relative` is load-bearing (a monorepo subtree must not be held back by a
sibling commit). **An ADDED source file blocks too** — not in the corpus, so not
"a file we carry that moved", but advancing would certify a complete index over
a corpus missing a file.
⚠ **`_paths_changed_between` returns None for "could not ask", NEVER an empty
set**, or a failed git call reads as a clean diff. Unknown → do not advance,
same asymmetry as .209.
⚠ **Branch-delta path deliberately UNCHANGED** (writes `branch_meta`, own
`base_head`); the reporter made no claim about it. Recorded, not swept.
⚠ `tests/test_index_file_head_advance.py` (10): **5 red at `b85ef61`, and the
other 5 pass on BOTH sides BY DESIGN** — they are the constraint tests (#330
must not regress, a single-file commit must still clear staleness). **A guard
that never advanced would satisfy every assertion about the bug and leave every
repo reading stale forever.** Say so, or a reviewer reads them as vacuous.

**#492 — `resolve_repo` answered a repository question with a filesystem fact.**
Fast path 1 matched `source_root` containment alone, so a path inside an
independent nested clone returned the PARENT index as `indexed: true`.
⚠⚠ **Whether it LOOKS wrong depends on something irrelevant to the defect.**
Gitignored nested repo → read fails, `absent`, indistinguishable from a normal
empty result. Absorbed into the parent walk → same wrong repo, read SUCCEEDS,
`state: ok`. **Two symptoms, one mis-resolution** — and only the second case
proves it without involving absence semantics at all.
⚠ Guard is a `.git` stat, **never a subprocess**: fast path 1 exists to avoid
the `resolve_index_identity` walk that can HANG (#303), so a correctness guard
that spawned a process would trade the reported bug for the one the fast path
was built to prevent. Asserted by monkeypatching `subprocess.run` to raise.
⚠⚠ **Classify by where `.git` POINTS, not by file-vs-directory.**
`.git/worktrees/` vs `.git/modules/` is #372's distinction; submodules still
resolve to the parent because their content IS indexed into it. **A
`--separate-git-dir` clone leaves a `.git` FILE pointing at neither, and a
file/directory test reads it as a submodule** — tested by name.
⚠ A file outside the parent's corpus (gitignored/oversize/skipped) still
resolves to the parent: being outside the corpus and belonging to another
repository are different conditions.
⚠ `tests/test_resolve_repo_nested_repo_boundary.py` (11): 7 red at `b85ef61`,
4 boundary tests pass both sides by design. Submodules and linked worktrees
tested against REAL git layouts (`git submodule add -c protocol.file.allow=always`,
`git worktree add`), not fabricated `.git` markers.
⚠ Suite: **7923 passed, 17 skipped, 0 failed** + ruff clean; +21 over #490's
7919 decomposes as 10 + 11.

⚠⚠ **PROCESS TRAP, NEW AND CHEAP TO REPEAT: `gh pr merge --delete-branch` on a
PR that is the BASE of a stacked PR CLOSES the stacked PR.** GitHub normally
retargets a stacked PR when its base merges; deleting the base branch in the
same operation closes it instead. **A closed PR's base cannot be changed and it
cannot be reopened while the base is gone** — `gh pr edit --base` returns
"Cannot change the base branch of a closed pull request", `gh pr reopen` returns
"Could not open the pull request". #497 died this way and was recovered as #498
from the same intact head branch. **Merge a stacked base WITHOUT
`--delete-branch`**, or retarget the child first.
⚠⚠ **A PR stacked on a branch base GETS NO TEST MATRIX AND LOOKS CLEAN.**
`test.yml` is `pull_request: branches: [main]`, so #497 showed 3 green checks
(radar / retrieval gate / CLA) and `mergeStateStatus: CLEAN` with the matrix
never run — **the fork-PR "only license/cla ran" hazard wearing a different
costume, and `CLEAN` is the part that sells it.** Remedy is the workflow's own
escape hatch: `gh workflow run test.yml --ref <branch>` (all 9 jobs green,
run `32092744385`). **Count the checks; a green rollup is not a run matrix.**

**2026-08-18: #443's conflict was OURS for the SIXTH time, resolved on their
branch.** Three of our merges (#490, #492, #493) landed in the same
`[Unreleased]` block, and a CONFLICTING fork PR has no `refs/pull/N/merge` and
therefore NO CI. Merged `main` in, resolved to one `## [Unreleased]` with
elfrost's `#447` section first, pushed to their fork. Suite on the merged tree
**7929 / 17 / 0**, +6 = exactly their tests; all 11 CI checks green on the merge
ref; `license/cla` PENDING is the only blocker.
⚠⚠ **Six is not six incidents, it is one wrong merge order repeated** — and
this round it was avoidable in a way the earlier ones were not: **all three of
our merges happened while their PR sat blocked, and we batched none of them.**
Policy 3b governs ORDER when we have a choice; when the contributor PR is
BLOCKED and we ship anyway, the remaining lever is **how many separate
`[Unreleased]` merges we make before resolving once**. Resolve after the LAST
one, not after each.
⚠ **The CLA status was erased by our push and came back within ~2 minutes as
`pending`** — both halves of the documented hazard fired in one push (erases an
existing status, provokes a missing one). `count=0` was observed and is NOT
"cleared". Said so on the thread so eleven green checks are not read as done.

**2026-08-17: #490 (@rknighton) FIXED BY US via PR #494 — a cache that
announced readiness one key early.** The BM25 corpus cache publishes FOUR keys
behind a check-then-build guarded on `idf` alone, and
`cache["idf"], cache["avgdl"], cache["inverted"] = _compute_bm25(...)` is THREE
`__setitem__` calls, with `centrality` a fourth statement after a whole pass
over the corpus. A second caller passed the readiness check and raised
`KeyError: 'centrality'` — through the dispatcher, `Internal error processing
search_symbols`. Unreleased; see CHANGELOG `[Unreleased]`.
⚠⚠ **The window is the entire runtime of `_compute_centrality`, so it WIDENS
with corpus size** — the installs most likely to hit it are the ones where the
rebuild is most expensive. Do not file this shape as "a narrow race".
⚠ **The lock was real and correctly held; the build WAS single-flight** as #370
intended. What leaked is the readiness SIGNAL, which is read outside the lock by
design and therefore must not become true early. **Diagnose which of the two the
defect is before reaching for the lock.**
⚠⚠ **THREE modules carried the identical block** (`search_symbols`,
`get_ranked_context`, `plan_turn`), so fixing the reported one leaves two —
[[feedback_guard_every_path_that_shares_the_hazard]] again. One
`ensure_bm25_cache()` helper now serves all three; the fast path checks ALL FOUR
keys, not the sentinel, so a future reorder costs a lock acquisition instead of
a KeyError.
⚠ **`pagerank` and `name_map` were CHECKED and deliberately LEFT** — each writes
the one key it also checks, atomic by construction. Their
`getattr(index, "_bm25_lock", None) or threading.Lock()` fallback is a separate,
milder weakness (a fresh lock per caller guards NOTHING, so a lockless index
would duplicate work rather than crash); unreachable today because both
`CodeIndex` and `SelectiveIndexView` carry the lock. **Recorded rather than
swept**, same treatment as #473's module-level `perf_db_path()`.
⚠⚠ **THE FIRST SHIPPED-PATH TEST PASSED AGAINST THE BROKEN SOURCE.** Signalling
from inside the build and letting the second thread race is not enough on a
two-file corpus: the builder finishes before the racer arrives. Only when the
build is held open until the second caller is demonstrably INSIDE its call does
it go red. **A concurrency test that does not pin the interleaving is testing
its own machine's scheduler**, and the tell is the non-vacuity pass: 7 of 8 red
first time, 8 of 8 after. [[a-concurrency-test-must-pin-the-interleaving]]
⚠ His `Event` framing said this in the issue body — "it does not create a
window" — and the first test ignored it. **Read the reporter's note about their
own harness; it is usually load-bearing.**
⚠ Suite: **7902 passed, 17 skipped, 0 failed** + ruff clean. Total 7919 against
.284's 7911 = exactly the 8 new tests, so nothing else moved.

**2026-08-17: #476 (@rknighton) FIXED BY US — one telemetry db spent another's
trim.** `_perf_rows_since_trim` was one int on the `_State` process singleton
while the trim runs on `conn`, so with two stores alternating one `tool_calls`
was never trimmed. Now a dict. Unreleased; see CHANGELOG `[Unreleased]`.
⚠ **Low severity and the REPORT said so** — opt-in, local-only, single-store
installs cannot reach it, cost is disk. He rates his own findings honestly; the
standing note that he understates still holds, but check each time.
⚠⚠ **Keyed by the SAME `str(path)` the connection cache uses, and that IS the
fix.** Keyed on the raw `base_path` instead, two spellings of one directory each
get their own budget toward a trim on one shared table — the same defect wearing
a new key. v1.108.280 resolved that spelling problem for the cache after #465;
this inherits it rather than re-opening it. [[feedback_guard_every_path_that_shares_the_hazard]]
⚠ **Added `_ensure_perf_db_locked_with_key` rather than calling `_perf_db_path`
twice** — re-deriving the key at the trim site repeats that helper's `mkdir` on
every write, and #442 exists because per-write cost on this exact path was the
whole problem. Two callers keep the old connection-only signature.
⚠ `close_perf_dbs()` clears the counters with the connections so a key cannot
outlive its store; the bounded cost is ~1000 rows of slack for a database whose
connection is dropped mid-cycle, against a cap that is already an
every-1000-writes approximation.
⚠ Nothing is backfilled: an already-oversized `tool_calls` trims on its own next
cycle.
⚠ `tests/test_perf_trim_is_per_database.py` (4) asserts on the COUNTER MAP, not
row counts after 1000 writes — 2000 rows across two databases would be slow and
would pin the trim interval. **All 4 red against a restored single counter.**

**2026-08-17: #443's conflict was OURS and we resolved it on their branch.**
elfrost's PR sat `CONFLICTING/DIRTY` since 2026-08-12 — and **a conflicting fork
PR has no `refs/pull/N/merge`, so it gets NO CI AT ALL**, which is why it read as
stalled contributor work when it was our CHANGELOG merges. Merged `main` in,
resolved to one `## [Unreleased]` heading with their section first, pushed to
their fork, said on the thread that the conflict was ours. `MERGEABLE` again,
suite green (7856/17, +6 = their tests).
⚠ **Checked before promising: elfrost is a User, not an Organization**, so the
`maintainerCanModify`-lies trap did not apply and the push worked.
⚠ **The CLA status SURVIVED this push** — the documented erase-on-push hazard did
not fire here. Do not treat either outcome as the rule; read the status.
⚠⚠ **#447 was NOT implemented, deliberately.** Its window is posted publicly to
**2026-08-20** and jjg reaffirmed it stands as posted. Resolving the conflict is
the move that respects the promise AND unblocks them — it removes the reason the
PR was dark without shortening anything.

**Merged 2026-08-16: #479 (@mikemikimike) closes #475** — `IndexStore` /
`SQLiteIndexStore` keyed their init caches on the SPELLING of `base_path`, so a
relative `storage_path` skipped `mkdir` and schema setup for the second store
after a chdir. Two source lines. Unreleased; see CHANGELOG `[Unreleased]`.
⚠ **The mock cleanup is the larger half.** `patch("...Path.resolve",
return_value=X)` replaces `resolve` on the `Path` CLASS, so it answered for every
path in the process — including the storage path `IndexStore` resolves at
construction. Four `test_tools.py` tests then CREATED their index directory at
the faked location (a stray `C:\work\project` locally; `mkdir` death at
`/workspaces/myrepo` and `\\server\share\` in CI). ⚠⚠ **Nothing in the suite
could have reported it, because the writes landed where no assertion was
looking** — same family as #439's blanket `os.path.exists` mock. `_resolve_only`
in `tests/__init__.py` is narrow, and needs `autospec=True` so `self` reaches the
side effect. All 19 patch sites converted; the other 15 were wrong too, just
inert. ⚠ The `expanduser()` half MOVES an existing case (a literal `~` in
`storage_path` built a directory named `~`); disclosed, not migrated.

**2026-08-16: the suite runs in PARALLEL, and that surfaced a test living on file
ordering.** `pytest-xdist` at `-n 4 --dist loadfile`, wired into `test.yml`.
Measured on a 24-core box: **599s serial vs 183s parallel**, same 7,859
collected; CI's exact command (with coverage) is 258s locally. Test-only + CI, no
version bump; rides the next release.
⚠ **`--dist loadfile` is load-bearing.** Whole file per worker preserves
within-file order; the default `--dist load` spreads individual tests and breaks
any file sharing module-level state.
⚠ **Worker isolation is STRONGER, not weaker** — everything conftest resets
(`_GLOBAL_CONFIG`, index cache, perf-DB handles) is process-global and each
worker is its own process. What parallelism removes is the accidental
cross-FILE ordering the serial run gave for free.
⚠⚠ **The two failures it produced were NOT caused by parallelism — they
reproduce serially in isolation.** `test_css.py` and `test_json.py` imported via
`src.jcodemunch_mcp`, a **different module object** from `jcodemunch_mcp` (`is`
→ `False`) carrying its own `config._GLOBAL_CONFIG` that conftest never resets.
The twin lazily read the developer's real `~/.code-index/config.jsonc`,
`is_language_enabled` gated the language out of the `languages` allowlist, and
`parse_file` returned `[]` against a direct extractor's 10 symbols.
⚠ **Which half failed is the proof of mechanism**: `test_css.py` drives BOTH
`css` and `scss` through `parse_file` and only `scss` broke — `css` is in the
allowlist, `scss` is not. They passed serially only because `test_config.py`
(also `src.`-prefixed) overwrote the twin earlier in alphabetical order.
⚠ **Maintenance Practice #8 in a spelling its guard cannot see** —
`test_config_isolation_guard.py` knows nothing of the `src.` prefix. **14 files
still import through the twin**, and `test_al.py` / `test_blade.py` are the same
defect UNFIRED, passing only because `al` and `blade` sit in this box's config.
**Not fixed; the two live failures are.** Next sweep starts there. **DONE — see
the sweep entry immediately below.**

**2026-08-17: the package twin is RETIRED and the guard now sees the spelling.**
All 140 `src.jcodemunch_mcp` references across 14 test modules converted, and
`tests/test_config_isolation_guard.py` gained the check. Test-only, no version
bump; rides the next release.
⚠⚠ **The guard already existed and a different IMPORT PATH walked around it** —
the same shape as the defect that file was written for, where the guard existed
and the CALL SITES walked around the reset. That is why the check went INTO that
file rather than a new one.
⚠ **Two of the fourteen were live, twelve were unfired.** `test_al.py` and
`test_blade.py` are the identical `parse_file` defect and passed only because
`al` and `blade` sit in this box's `languages` allowlist.
⚠⚠ **The `patch("src.jcodemunch_mcp...")` form fails the OTHER way and is the
worse half**: it patches the twin's attribute while the test drives the canonical
module, so the patch does nothing and the test passes **without testing what it
names**. Two existed (`test_config.py:351`, `test_git_sha_verification.py:159`).
**Converting imports without converting these would have left a false green.**
⚠ Detector matches a string only when it STARTS with the twin root (the shape of
a patch target) and skips docstrings, so prose naming the hazard is not a
violation — asserted by name. ⚠ **`_TWIN_ROOT` is assembled from two literals so
the guard does not exempt ITSELF**; as one string it flags its own source line,
and exempting the file or special-casing its name both stop it policing itself.
⚠ **Non-vacuity proven against the REAL pre-fix tree**, not just synthetic
fixtures: restoring `tests/test_al.py` from `HEAD` turns it red naming lines 6-7.
`TWIN_EXEMPT` is EMPTY and its parametrize-over-nothing SKIP is the ratchet at
rest.
⚠ Suite: Windows **7850 passed, 17 skipped, 0 failed**, coverage 79.66%, ruff
clean. Delta from 7864 is EXACTLY **+3** and decomposes as +2 passing guard tests
and +1 skip (the empty parametrize) — the skip count moving 16 → 17 is the
ratchet arriving, not a lost test.
⚠ **CI pinned to `-n 4`, deliberately not `-n auto`** — GitHub runners are
4-core so `auto` matches today and would jump silently on a resize, and extra
workers contend on the same `~/.code-index` process-lock scopes that caused
.261's 47m outlier.
⚠⚠ **The local-uv lock hazard fired in its THIRD direction on a change that only
added a test runner.** Local uv 0.12.1 vs the CI pin 0.9.5 gave 76 insertions /
52 deletions, and beyond the known nvidia widening it **stripped
`python_full_version` guards off the google-api deps and `typing-extensions`**,
changing what installs on 3.10 vs 3.14. Re-locked with `uvx --from uv==0.9.5 uv
lock`: 24 insertions, 0 deletions. **Diff the lock after EVERY `uv lock`, not
just version bumps.**
⚠⚠ **It went RED on CI and the failure was a REAL production defect the serial
runner had never exercised — `call_tool` ate its caller's `format` argument.**
`arguments.pop("format")` popped from the CALLER's dict, so a caller reusing one
args object got JSON first and `server_output`'s default after. Fixed at the
dispatcher (`arguments = dict(arguments)`), not in the tests, because the Counter
front door re-dispatches through the same path. Over the wire it is unreachable —
every request arrives as a fresh dict — so only in-process callers are exposed.
⚠⚠ **It presented as an environment quirk and that is the reusable part.** The
second call falls back to `auto`, where the **15% encoding gate decides per
response**, and the response carries `timing_ms`. Coverage instrumentation slows
the call, moves that number, moves the byte count, tips the gate. Red on ubuntu
3.10/3.11/3.12, GREEN on ubuntu 3.13, green on all four Windows legs, green
locally without `--cov`, red locally with it. **Chasing the platform matrix would
have found nothing.**
⚠ **Reproduced on a WSL Ubuntu 3.12 copy, which is what made it cheap** — Windows
cannot produce it at all, and a CI cycle is 4 minutes against WSL's 3. Docker
Desktop was not running; `wsl -d Ubuntu` with a `tar`-copied tree and its own uv
was enough. ⚠ WSL interop expands `$PATH` into the command string and the Windows
PATH contains parens, so `bash -lc` dies on a syntax error — use absolute paths
and no variables.
⚠ `tests/test_dispatcher_arg_mutation.py` (3) asserts on the ARGUMENT DICT, never
on the response encoding, so it does not inherit the gate's environment
sensitivity. Reverting turns 2 of 3 red; the third is the control.
⚠ Suite with the fix: WSL Linux 3.12 **7833 passed, 0 failed** (+9 sdist errors
that are an artifact of copying without `.git`); Windows **see release line**.
Delta decomposes as 7828 + 2 fixed + 3 new = 7833. **Fold into the `Tests:` line
at release, not before.**

**2026-08-15: #428's remaining four languages IMPLEMENTED BY US (Rust, Go, Java,
PHP), closing it.** Shipped as 1.108.281 via PR #478; see Current State.
⚠⚠ **This is a REVERSAL of an open handoff, not a timebox expiring, and it was
jjg's call.** The half was @mussonking's by an offer with **no date on it** — the
standing rule is that every handoff names a date AND the default that fires on
it, and this one named neither, which is exactly how it sat seven days. Credit
for the report and for the plural-helper design stays his in the CHANGELOG.
**The process lesson is the open-ended offer, not the reversal.**
[[feedback_never_hand_off_without_a_timebox]]
⚠⚠ **Java needed more than a branch and the gate was the real defect.** The
constant walk was `parent_symbol is None`, which keeps function locals out — and
a Java constant is a class member, so `field_declaration` sat in
`constant_patterns` **unreachable by construction**. The gate now also accepts a
CONTAINER parent for `_CLASS_SCOPED_CONSTANT_LANGUAGES` (`{"java"}`), never a
function parent. ⚠ **Relaxing it for every language was DECLINED**: Python class
bodies, JS class fields and PHP class constants would all start emitting
constants they never have, moving symbol counts in every index and **every
published dead-code grade**. One named set, one sample per member, asserted by
name in `test_only_named_languages_reach_constants_through_a_container`.
⚠ **Scala looked like a counter-example and is not** — its `val_definition` is in
`symbol_node_types`, so it never touches the constant gate at all. Checking that
before copying its shape is what kept the widening narrow.
⚠ **The exclusions are the careful half**: Rust `static mut` (a
`mutable_specifier` says the binding changes), Java bare `final` (per-instance)
and bare `static` (mutable shared state). **A missing constant is a recall bug
the reporter could see; an ordinary field arriving as `kind="constant"` is a
precision bug nobody goes looking for.**
⚠ **Grammar shapes were DUMPED, not assumed** — the TOML left-recursion defect
came from assuming. Go binds N names two ways at once (`const ( ... )` groups
plus `const A, B = 1, 2`), which is what `_extract_constants` being plural is
for. ⚠ No case heuristic anywhere: `const` IS the declaration, and filtering on
case would silently drop Go's unexported lowercase constants.
⚠ `tests/test_v1_108_281.py` (10), **9 fail against `d10490e`**; the 1 passing
both sides is the control that Java function locals are still not constants.
`EXEMPT` in `test_constant_extraction_guard.py` is now **EMPTY** — the ratchet
forced its own deletion, and its parametrize-over-nothing SKIP is the ratchet at
rest, not a lost test.

**Merged 2026-08-14: #473 (@rknighton) closes #465** — the perf-db connection
cache keyed on the caller's SPELLING, not the resolved path, so a relative
`storage_path` wrote one store's telemetry rows into another's after a chdir.
Two source lines, three tests, unreleased; see CHANGELOG `[Unreleased]`.
⚠⚠ **The reusable half is where the fix went.** `_perf_db_path` has one caller
and all three telemetry sinks reach the cache through it, so resolving where the
path is BUILT fixes every consumer including the one the issue left open. Fixing
it at the cache would have covered the sinks that were reported and missed that
one ([[feedback_guard_every_path_that_shares_the_hazard]]).
⚠ **The module-level `perf_db_path()` helper is still unresolved ON PURPOSE**,
checked rather than assumed: it never touches the cache, and an unresolved
spelling opens the same file on disk. Recorded here so a later sweep does not
"finish the job" and call it a fix.
⚠ **Both exits needed the change and only one is covered by the row-level
tests** — they all pass an explicit `base_path`, so the no-argument exit carries
its own assertion. Reverting either `.resolve()` alone turns the file red, which
is the non-vacuity pass done per-edit rather than per-file.
⚠ **First timebox to expire in the contributor's favour under policy 3a**: #465
was handed off with a 2026-08-21 default, and the PR arrived in a day. The
window decides whose commit it is, and here it was his.
⚠ **His verification note is worth copying: he reported a DELTA, not totals.**
Ten test modules `importorskip` at module level, so a missing optional dep costs
a whole module as ONE skip and no per-test trace — two correct runs of the same
commit can differ by a hundred. Same class as the `--extra watch` under-collect
in the Tests line above, found independently from the other side.

**In flight 2026-08-13: #441 + #442 (@rknighton), ranking-ledger write path.**
Same path .272 touched. Unreleased; see CHANGELOG `[Unreleased]`.
⚠⚠ **The reusable lesson is that measuring the SAFE fix first is what chose the
risky one.** #442 has an obvious low-risk shape — remember the schema is ready,
skip the eight `IF NOT EXISTS` statements, keep the per-write open/close, no
connection lifetime to manage. **Measured: it captures 2% of the available
saving.** The other 98% is the open/close itself. Had that not been measured, the
cheap fix would have shipped, looked principled, and delivered nothing.
⚠ Shipped path is **3.455ms vs 16.615ms**, a **79%** cut, agreeing with his 82%
(absolutes are machine-local; the ratio transfers). ⚠ `check_same_thread=False` is
REQUIRED (searches dispatch via `asyncio.to_thread`, so a cached connection
outlives its opening thread) and SAFE only because every caller holds
`_State._lock` — recorded at the call site because a future edit could quietly
invalidate it.
⚠⚠ **Caching a connection introduces TWO silent failure modes the report did not
name, and the benchmark found the first by crashing**: a stray `close()` poisons
the cache so every later caller gets a dead handle (telemetry off, every write
still reporting success), and a DELETED db file gets written into an unlinked
inode forever (pre-caching, the next event just recreated it). A liveness probe
catches only the first; the `exists()` check is what catches the second. Together
**0.344ms, 2.1%** of the pre-fix write. ⚠ **Windows cannot produce the orphan case
at all** (it refuses to unlink a file with an open handle) — the end-to-end test
is POSIX-only and says so, with a portable unit test for the predicate. **Do not
read that skip as cross-platform coverage.**
⚠ Suite at this point: **7763 passed, 9 skipped, 0 failed** + `ruff check src/`
clean. Reconciled by same-tree collect: 7772 total, 7753 with
`test_v1_108_276.py` ignored (= its 19), so nothing else moved. The 9th skip is
the POSIX-only orphan test. **Fold this into the `Tests:` line at release**, not
before — it is not a released count yet.
⚠ #441 pre-existing rows keep `NULL` = UNKNOWN and are NOT backfilled; inferring
`count == len(returned_ids)` is the defect itself. ⚠ **He filed it against his own
earlier claim** in Discussion #430 and caught it on re-verification. ⚠ Severity
checked and it is genuinely analysis-only: `regret` and `ledger_trust` read
`returned_ids` only for emptiness/>1, and truncation starts above 50.

**Merged 2026-08-13: #439 (@JayceeB1) Windows drive-root child Git repos, closing
#438** — plus **#453 fixed on top, test-only.** Both ride the next release; no
version bump. ⚠⚠ **The reusable lesson is one sentence and it cost most of a day:
a mock broad enough to satisfy an assertion can be broad enough to bypass what the
assertion is about.** It fired three times in three different costumes.

⚠⚠ **My own review advice on #439 was WRONG and nearly shipped a hole.** I told
them `_path_safety_part_count(path) == 2` subsumed `not drive.startswith("\\\\")`.
It does not: the helper is a **DEPTH** rule and the UNC clause is a **SCOPE** rule.
A UNC share root has ONE real part and the helper adds one for the
`\\server\share` anchor, so it computes to **exactly 2 — the same as `C:\repo`**.
With the clause gone, `\\server\share` holding a `.git` is admitted, handing the
indexer a whole file server through the guard that exists to stop that (#321/#322).
⚠ **`len(path.parts)` genuinely WAS a redundant depth notion — that half was
right.** The error was concluding that a second condition mentioning the same
variable must therefore be redundant too. **Check what a predicate is FOR, not what
it reads.** Restored with both clauses, the reason recorded in the docstring, and
the bad advice corrected in the CHANGELOG rather than deleted
([[feedback_a_fix_comment_is_not_evidence_about_its_siblings]] — same reason).

⚠⚠ **The regression test for it was ALSO wrong, in a way that PASSED.** It patched
`os.path.exists` to a blanket `True`, which also answers `_is_container()`'s
`/.dockerenv` probe — that drops `_MIN_PATH_PARTS` from three to two, so `2 < 2`
skips the guard entirely and `_is_shallow_windows_git_root` **was never called**
(proven by spying on it: zero invocations). ⚠ **The tell was that it failed
IDENTICALLY with and without the fix.** A test failing on both sides is as
uninformative as one passing on both sides, and it is the cheaper tell to notice
because you are already looking at a red. **Run the non-vacuity pass even when the
test is currently failing.**

⚠⚠ **#453's tripwire had the same disease a third time: it could not fire.**
`_no_real_access_under` raised `AssertionError`, and every read site it guards is
wrapped in a bare `except Exception` in production, so a deliberately re-broadened
mock **passed cleanly with the guard installed**. Now derives from
`BaseException`. **A guard that cannot fire is worse than no guard, because it
reads as coverage.** Always prove a new guard fires by breaking the thing it
watches.

⚠ **#453's actual root cause was NOT the one I inferred**, and the difference
mattered. I traced seven network `read_text` calls (`detect_framework` probing
manifests under a blanket `Path.exists=True`) and took them for the culprit; they
are real network I/O in a unit test but are **swallowed by production's
`except Exception` and never failed anything**. The failure was
`resolve_index_identity` → `folder_path.is_file()` (`storage/git_root.py:160`),
never patched. **Only pulling the real CI traceback settled it** — attempt 1 of a
rerun run, via `gh api .../runs/<id>/attempts/1/jobs`, because **a rerun flips the
run's conclusion to success and hides the failure from `gh run list`**.
`Path.is_file()` swallows ENOENT-class errors (a box with no such share) but
propagates `WinError 64` (a runner with live-but-failing networking) — same test,
opposite outcomes, decided by whose network answered.

⚠ **Process note: `git checkout -- <file>` destroyed uncommitted work TWICE**
during the non-vacuity passes, because the falsification edit and the fix lived in
the same file. Copy the fixed file to the scratchpad first and restore from that.

**Merged 2026-07-25: #379 (@oderwat) Gleam import extraction** — Gleam was already
in `LANGUAGE_REGISTRY`, so symbols extracted but the import graph stayed EMPTY,
leaving `find_importers`/`get_blast_radius`/`get_dependency_graph` silently blind
on Gleam projects. Same shape as the week's verdict work: capability present,
wiring absent. Verified against a TRIAL MERGE onto current main (branch-green is
not merged-green), 210 neighbouring import/language tests green. Landed AFTER the
1.108.170 release commit, so it rides the NEXT release, not that one.

**Merged 2026-07-25: #378 (@zuoYu-zzz) TOML symbol extraction** — tables → `type`,
array tables → `class`, key-value pairs → `constant`. Merged rather than
review-round-tripped, then fixed on top in **`f0eda7b`**. ⚠ **The defect worth
remembering: `_extract_key` scanned a `dotted_key`'s DIRECT children for
`bare_key`/`quoted_key`, but tree-sitter-toml nests `dotted_key`
LEFT-RECURSIVELY** (`[tool.ruff.lint]` = `dotted_key(dotted_key(tool, ruff),
lint)`), so every segment but the last was dropped. **Two-level paths worked,
which is exactly why it read as correct** — the bug only shows at three-plus, and
on jcm's OWN pyproject.toml `[tool.hatch.build.targets.wheel]` came back as
`wheel` with signature `[wheel]`, **a header that appears nowhere in the file**
(search_symbols would have handed an agent fabricated source text). Fix returns
path SEGMENTS and recurses; building from segments also fixed `name`/
`qualified_name`, which the PR set to the same value (now leaf / full dotted path,
matching every other extractor). New test asserts three- AND five-deep tables plus
a signature-occurs-in-source check, proven non-vacuous. **The PR's own test used
only single-segment headers, so nothing in the suite could have caught it** — the
general lesson for any new nested-grammar walker. Rides the next release with #379.

**Closed 2026-07-25: #380 Atlas Cloud summarizer** (@binyangzhu000-sudo). Closed on
DEMAND, not quality: CLA unsigned (hard blocker), and the capability is fully
reachable today via `OPENAI_API_BASE` + `SUMMARIZER_PROVIDER=openai` since Atlas
Cloud is OpenAI-compatible. Cost of merging was **8** permanent env-var spellings
(`ATLASCLOUD_`/`ATLAS_CLOUD_` × `API_KEY`/`API_BASE`/`BASE_URL`/`MODEL`) plus 3
aliases, permanent under the 1.x no-removal contract. ⚠ **Do NOT re-close a future
one of these "we don't take branded providers"** — MiniMax/GLM/OpenRouter are
exactly this shape and already merged; the comment concedes that on the record.
The bar is a user asking, same as platform installers. It correctly added
atlascloud to `_PAID_CLOUD_PROVIDERS`, so the money-safety guard was respected.
**Tracker state 2026-07-28: ZERO open issues, ZERO open PRs.** Verified against
`gh issue list --state open` / `gh pr list --state open`, with an
`--state all` query alongside to prove the empty result was not a failed query
([[feedback_empty_cli_query_is_not_evidence]]).

⚠⚠ **DO NOT quote a tracker count from this file — re-run the query.** The line
that used to live here said "Open issues: #375, #377. Open PRs: #387 and #388"
while a paragraph twelve lines below it recorded #388's own close. **It was
internally contradictory and it was believed anyway**, which is how a stale
"#375 ONLY" got written into this file on 2026-07-28 for an issue closed the day
before. A count is the one fact here with a guaranteed expiry date.

**Closed 2026-08-05: #414 (@MotoMato85) byte offsets slicing a decoded str in
16 extractors** — shipped as 1.108.244, see Current State. ⚠ **The report is the
best-instrumented one this project has received**: an AST audit finding exactly
35 `source` subscripts and classifying 34 as byte-offset plus the ONE correct
character-domain case, a per-symbol drift table proving the shift EQUALS the
extra UTF-8 byte count, a 118-function whole-repo measurement (105 wrong before,
1 after — and he diagnosed the survivor as an unrelated tree-sitter `ERROR`
node), and a fix proposal with an AST argument for why substituting `source` is
behaviour-preserving. **Every claim I checked reproduced byte-identically.**
⚠ **His proposed helper had one flaw worth remembering**: its
`for cut in range(4)` decode loop trims trailing bytes until a decode succeeds,
which for a slice containing an INVALID byte in the middle silently returns the
prefix and DROPS the rest. Shipped version only trims when the bad run reaches
the END of the chunk. **A test I wrote for the degradation path caught it**;
neither of us would have caught it by reading. ⚠⚠ **The reusable lesson is that
fixing the producer left the DATA wrong and the obvious remedy did not work**:
"re-index" is a no-op here, because the corrupt rows sit in files that never
changed ([[feedback_fixing_a_producer_does_not_fix_its_history]]). Hence
`PARSER_GENERATION`, and it must be checked BEFORE every early-returning fast
path. ⚠ A pure-ASCII fixture cannot fail on this class at all, which is why it
survived every existing parser test.

**Closed 2026-08-05: #413 (@LuigiNicaPRO) a silent full rebuild replacing a
requested incremental** — shipped as 1.108.243, see Current State. ⚠ **The
reusable lesson is that the READ side and the WRITE side of one store drifted.**
`inspect_index` was built in PR #291 specifically to discriminate the causes
`load_index` collapses into `None`, four read-path tools adopted it, and the two
INDEXING tools kept a hand-written branch that named one cause for seven. His
own grep is the diagnostic worth copying: `loadab` / `load_error` /
`index_status` / `sqlite_corrupt` / `index_present` returned **zero** hits in
`index_folder.py` while `existing_index is None` was present. ⚠ **He measured
the harm honestly and DOWN**: on his repos the substituted rebuild costs about a
second, and he said so unprompted rather than inflating it. The defect is the
undiagnosability, not the time. ⚠ **We shipped his options (1) and (2) and NOT
(3)** — an `on_unloadable_index="error"` parameter is permanent surface under the
1.x no-removal contract, and he stated (1)+(2) covers his case. Demand-driven, as
with platform installers.

**Closed 2026-08-04: #412 (@rknighton) git_sha verification accepted a truncated
cache** — shipped as 1.108.235, see Current State. ⚠ **The reusable lesson is
about WHERE it was measured, not about the comparison.** His repro exercised
`_slice_matches` directly, which is the layer his own #401 patch had edited. At
`get_symbol_source`'s entry point the sibling `content_verified` already returned
`False` on those caches, so the served response was contradictory rather than
uniformly wrong. **Neither view alone is the whole answer, and the tool response
is the one that describes what a caller experiences**
([[feedback_verify_at_the_users_entry_point]]). ⚠ **This is the first finding of
his that got LESS severe on inspection** — the standing note says he understates,
and #411 was the first time verifying upward came back neutral. Two in a row now
land off that pattern: **check every time, report whichever way it lands, and do
not reach for the expected direction.**

**Closed 2026-08-04: #411 (@rknighton) test config isolation** — `_run_config`
in `tests/test_v1_108_194.py` scrubbed `JCODEMUNCH_MAX_FILE_SIZE` but left the
subprocess reading the developer's real `~/.code-index/config.jsonc`, so both
`max_file_size` assertions failed on any box with the key set. Reported WITH a
`git apply --check`-verified patch; applied as written in `5a3ee39`.
⚠ **`TemporaryDirectory`, not the `mkdtemp` used elsewhere in that file** — the
config reporter WRITES a `config.jsonc` into the directory it is pointed at, so
an uncleaned temp dir per call accumulates. That is the whole reason the patch
costs a reindent, and it is the part a later "simplification" would undo.
⚠ **His severity framing was checked upward and HELD, which is the notable
part** — the standing note on this reporter is that he understates, so both
larger readings were tested and came back NEGATIVE. (1) Not a production
precedence bug: config beats env for `max_file_size` and the resolver agrees,
but `max_folder_files` / `max_index_files` behave identically, so .193's key
follows its siblings. (2) Not wider than one file: `test_surface_cli.py` is the
only other CLI-shelling test without `CODE_INDEX_PATH` isolation and it PASSES
under a hostile config because its assertions are shape-based, not value-based
(latently exposed if anyone adds a value-based one); `test_watch_all.py` is
isolated by argument (`watch_all.py:48` honours `storage_path`).
⚠ **The observation worth keeping: the file's docstring says it guards the #375
failure mode, so the test protecting the large-file escape hatch was broken by
USING the large-file escape hatch.** Reaching it at all required being exactly
the user it was written for, which is why it went unseen on every dev box that
had not capped out on a large repo. Same family as jdata's `test_v1_15_0` /
`test_v1_16_0` false-greens reading the real `~/.data-index`. Test-only, no
version bump; rides the next release.

Closed this session: **#390** (@lazy-geeek, its own repro already fixed by
`.194`), **#391** (@amarakramali, rewritten as 1.108.197), **#387** (@nyxst4ck,
rewritten wider), **#377** (P3 remainder + P4 to `ROADMAP.md` with close
conditions and @mightydanp's credit, same treatment as #385/#386). **#375** and
**#388** were already closed 2026-07-27.

⚠⚠ **PROCESS FAILURE WORTH NOT REPEATING: #388 fixed #384 and was opened
2026-07-27 06:51 UTC. We shipped our own .189 fix and closed #384 at 12:56 UTC
having NEVER LOOKED AT OPEN PRs — the cross-reference sat on #384's timeline the
whole time. CHECK `gh pr list` BEFORE WRITING CODE ON AN ISSUE.** Their fix then
went `CONFLICTING/DIRTY` because .189 rewrote the same functions. Resolved by
PORTING the gap they covered and we missed (`maybe_takeover`) in **v1.108.190**
with credit in the CHANGELOG, release notes and close comment, rather than
asking a pre-empted first-time contributor to both rebase onto our version of
their fix AND sign a CLA. **#388 closed 2026-07-27.** Cleaned up in
v1.108.189 on a standing rule jjg set: **an issue opens when work STARTS or when
a USER is BLOCKED** — an issue is a problem to fix or a feature to build, not a
to-do list. **#383 and #384 are FIXED** (see Current State); **#385/#386 (evidence
Phases 5 and 6) were CLOSED and moved to `ROADMAP.md`** — accepted design with no
start date and an unmet dependency is a plan, not an issue. ⚠ **Closing them is
NOT a rejection of @mightydanp's design and the close comments say so explicitly;
credit and close conditions moved verbatim.** ⚠ **The convention that GENERATED
the clutter was our own — "new scope gets its own close condition", cited in
#385's body. It is right for scope being WORKED and wrong for scope PARKED.**
Remaining: **#375** (needs a re-run from @dkiaulakis at >=1.108.182, not code) and
**#377** (down to two concrete Phase 2 P3 edges @mightydanp pinned 2026-07-27:
an absence receipt still links a MUTABLE `absent:<sha>` key `note_absence` can
overwrite across snapshots, and validation vs rendering do two SEPARATE receipt
lookups instead of one atomic snapshot).

**#375 (index_folder silent 1800s+ on Linux) — REOPENED 2026-07-26, and the
blocker is a RE-RUN, not code.** Closed 2026-07-26 on our own measurement after
five releases; @dkiaulakis re-ran at 1.108.176 and the SAME `tools/eidos` subtree
took **268s SIGTERM'd vs a 240s baseline at .169 — no improvement**, which is
exactly the condition the close comment said would reopen it. ⚠ **No py-spy this
round: ptrace is restricted in his sandbox and his agent correctly declined to
grant itself CAP_SYS_PTRACE mid-task.** ⚠ **The 5400s full-repo number is a
CLIENT-side MCP timeout and does NOT prove the server job stopped** — he flagged
that himself; he runs 10+ concurrent stdio servers and had no safe way to
identify his own process. What .176 DID deliver, in his words: "we can now see
the problem we could not previously see" — `index_coverage` read ABSENT before
and now reports a number plus `index_stale: true (git_head_lag)`. **The freshness
half stands; the stall is a separate axis.** v1.108.182 shipped three bounds in
response (provider-discovery budget, walk pruning at `iter_source_files`,
per-file `parse_file_budgeted`), two of them his own twice-proposed suggestions.
⚠ **STATED LIMIT, do not overclaim it: a watchdog stops the CALLER waiting, it
cannot stop the WORK** — Python cannot preempt a thread and tree-sitter is C, so
an abandoned parse keeps burning CPU. It makes the index finish and the gap
visible; it does not cap CPU. Sub-problems: **A -> #383, FIXED in .189. B closed
not-a-defect** (default `log_level` is WARNING, so a healthy run emits nothing).
**C fixed in .176** (a partial index no longer reports itself fresh; `complete`
is TRI-state and pre-.176 indexes report `null`, NEVER `true` — re-index or the
signal is not there to see). **D near-ruled-out** (every `indexwrite` acquire
passes `wait_seconds=60.0` and RAISES naming the holder, so it cannot present as
unbounded silence). **The double-index finding -> #384, FIXED in .189.**
⚠ **Next action is a PING, not a patch.**

**Closed 2026-07-26: #382 "Old tree sitter dependency?" (@kecsap)** — asked why we
pin `tree-sitter-language-pack>=0.7.0,<1.0.0` when "other code parser MCP tools
happily use >= 1.0.0". Tested 1.13.3 against the full suite before answering;
the pin STAYS, and the rationale now lives as a comment on the dep itself so this
is not re-derived. ⚠ **The load-bearing reason: 1.x STOPPED BUNDLING GRAMMARS.**
The wheel ships a single `_native.pyd` and an empty bindings dir; `get_parser`
downloads the grammar from a remote manifest into `%LOCALAPPDATA%\tree-sitter-
language-pack\v<ver>\libs` on first use (proven by watching that cache go 0 -> 67
shared libs while walking our language list). **That is runtime network access plus
executable-writes-to-disk in a tool that advertises itself as read-only and local,
and it breaks airgapped installs outright** — i.e. exactly the class of undisclosed
persistent/network behavior that caused the PyPI quarantine, so it could never ride
a dependency-housekeeping commit anyway. Two smaller blockers: **`autohotkey`,
`ejs`, `verse` do not exist in 1.x** (`DownloadError: not available for download`),
so bumping silently drops three languages; and **the nim grammar was swapped for a
different upstream** (`source_file/proc_declaration/identifier` ->
`module/stmt/routine/symbol/ident`), so our nim extractor returns zero symbols.
Suite on 1.13.3: **5812 passed, 12 skipped, 1 failed** (`test_nim_parsing`, and
only that). ⚠ **There is NO API incompatibility to cite — we use exactly one symbol
from this package, `get_parser`** — so do not argue the pin on API grounds; the
blockers are all behavioral. ⚠ **Unrelated pre-existing pathology found while
testing, NOT a 1.x regression and NOT filed: `get_parser("cobol").parse(b"x")`
hangs indefinitely on BOTH 0.13.0 and 1.13.3.** A 1-byte input, no timeout.
Unreachable today (we only feed it real `.cbl` files) but it invalidated the first
version of the compatibility harness, so any future per-language sweep must resolve
parsers WITHOUT parsing pathological input.

**Closed 2026-08-15: #480 `neuforge-pay` metering pitch, at jjg's direction** —
a mass-mailed vendor solicitation, not a feature request. The same text sits in
**84 issues across GitHub**, including `Snailclimb/JavaGuide`, a Java reading
list with no endpoints and no LLM calls, so nothing about this repo was read
before filing. ⚠ **Three independent reasons, and the spam is the weakest one.**
It decorates `@app.get("/v1/query")` and jcm is a local stdio server with no
endpoint, no per-call price and no hosted session, so there is nothing to attach
to. A payment SDK is third-party **network egress plus a Merchant of Record
relationship** inside a tool that advertises itself as read-only and local — the
#382 objection exactly, and the class that caused the PyPI quarantine. And it
fails #380's demand bar: **branded providers get in when a USER asks**
(MiniMax/GLM/OpenRouter did), and one vendor pitching its own SDK to 84 repos is
not a user asking. ⚠ `neuforge-pay` itself was deliberately NOT fetched or
inspected; the decision rests on none of it.

**#381 (MCP Toplist badge) CLOSED by jjg** — 120 identical drive-by PRs from that
author; the badge renders "Top 1% of 81,432", not the rank the PR body promised,
and it is live third-party-controlled content in a README that also renders on PyPI.

---

## Appendix: rotated release entries

Rotated out of `CLAUDE.md` **Current State** under Maintenance Practice 5
(3 newest releases), verbatim. Newest first.

- **Prior (1.108.295):** **What the guard could not see.** Four items, three of them a check that could not observe the thing it claimed to check. **(1) `_build`.** We skipped `build` and `.build` and NOT the underscore spelling — what Elixir/Mix, Sphinx and Dune use. ⚠⚠ **`mix` copies dependency SOURCES into `_build`, so an Elixir project indexed EVERY dependency symbol twice** and the copies competed with the originals in ranking: the v1.108.234 duplicate-source-tree defect wearing a third name. ⚠ Bounded by gitignore, listed anyway — `build/` is in that same gitignore. **(2) The strict deny (#541).** `_bash_targets_outside_roots` reads path tokens out of the RAW command string, so `grep ~/x.md` was ALLOWED and `grep $HOME/x.md` was DENIED — same destination, opposite verdicts. **A deny now requires a RESOLVABLE target**, the caution already applied to `find`, pipelines and `../`; it downgrades to a nudge, never to silence. ⚠⚠ **The detector is deliberately NOT a bare `\$`** — a trailing `$` is a regex end-anchor and `grep "foo$" src/` is idiomatic, so suppressing on any `$` would silently weaken the enforcement a strict user opted into. ⚠⚠ **A SECOND blindness surfaced FROM that test**: `_BASH_PATH_TOKEN_RE` matched only POSIX roots, so `/c/Users/j/x.md` was seen and **`C:/Users/j/x.md` was not** — a strict deny on a path outside every root, **on the platform most users are on**, with the verdict depending on how the drive was spelled. Genuinely resolvable, so a real fix not a downgrade. **(3) The cache hit-rate.** `analyze_perf` published `hit_rate` bare, where a hit is KEY-PRESENCE in the session LRU. arXiv:2608.20280 measured raw 51-60% falling to **1.1-2.2%** once validity was checked. ⚠⚠ **The system already knew the difference and the metric did not** — #377 item 3 revalidates cached ABSENCES, #404 re-annotates row freshness. Raw rate KEPT with `hit_rate_basis`, three buckets beside it, `hit_rate_revalidated` **None not 0.0** when nothing was validated. ⚠ Only `search_symbols` revalidates, so `hits_unvalidated` is non-empty BY CONSTRUCTION. **(4) Docs**: the `mcp_toolset` `default_config` defer path, and the vendor's **30-50 tools** degradation threshold against our 91. [[a-ratchet-can-pass-against-the-defect-it-names]]

- **Prior (1.108.288):** **The reported surface was never the only one.** Four fixes; in three of them the report named one site and the tree held several — which is .287's own finding ("we fix the reported call site and leave the mechanism") acted on BEFORE shipping rather than after. **#447** (@elfrost) — `install-pack`'s pre-scan rejected a leading separator and `..`, necessary and NOT sufficient: `C:/Windows/Temp/evil.txt` carries neither, and `base / relative` **DISCARDS `base`** when `relative` is absolute, with `mkdir(parents=True)` running BEFORE the write. Confinement is by RESOLUTION now; the pre-scan stays as an early abort. ⚠⚠ **The rule had THREE spellings already** (`security.validate_path` + a private copy on each index store) **and the new call site would have been a fourth** — one definition in `security.resolve_within()`, both stores delegating, ratchet on a stray `commonpath`. ⚠⚠ **THE FIRST REGRESSION TEST PASSED AGAINST THE UNFIXED SOURCE AND ITS NON-VACUITY PASS WROTE A REAL FILE INTO A REAL WINDOWS SYSTEM DIRECTORY**: it named the reported path verbatim, so the escape went OUTSIDE the directory the assertion searched. **A test for an ARBITRARY-WRITE defect EXECUTES that defect every time you prove it is not vacuous — the target must be somewhere the test OWNS.** ⚠ Refusal deliberately NOT platform-pinned: `C:/...` is absolute on Windows and an ordinary name on POSIX. ⚠ **Implemented BY US at timebox expiry; elfrost found it, analysed it and wrote a correct fix #443 could not merge for CLA reasons — provenance stated on both threads.** **#517** (@marcelruhf) — `license = { file = "LICENSE" }` made PyPI publish the whole licence TEXT as `info.license`, so a commercial user had no identifier to allowlist. PEP 639 expression now. ⚠⚠ **He could see ONE surface; we declared it on THREE** — plugin.json and the mcpb manifest both said `LicenseRef-Dual-Use`, so an allowlist still needed two entries. ⚠ **The version suffix is load-bearing**: LICENSE 1.2 must produce a NEW identifier or consent to 1.1's terms is inherited by terms nobody read; the ratchet pins the suffix to the file's own `Version` line. ⚠ PyPI metadata is IMMUTABLE per version, so it starts HERE and 1.108.287 keeps the full text. **#515** (@rknighton) — `CONFIGURATION.md` documented `disabled_tools` as `[]` against a shipped `["test_summarizer"]`. ⚠⚠ **FOUR surfaces describe that default and the THREE that agree are the point** — template, `config --init` comment, and a TEST PINNING THE VALUE. **A value pinned by a test can still be mis-documented; the pin guards the value, not every claim about it.** Ratchet compares EVERY `Default` cell in the document. **#504** (@lsg1103275794, his PR) — the v1.96 collision guard assigned `_merge_with_existing` on a matching `git_root` with NO `walk_prefix` test, so a full-root re-walk could never reach the incremental branch and every scheduled freshness check rebuilt the corpus. ⚠ **DISCLOSED MIGRATION**: one rebuild per index to establish `source_roots == [""]`. [[push-to-the-fork-remote-by-name]]

---

## Appendix: `Tests:` line history (rotated 2026-08-21)

Per-release suite counts for 1.108.286 and earlier, verbatim from `CLAUDE.md`.
The standing warnings drawn from these runs stayed in `CLAUDE.md`; what is here
is the per-release evidence behind them.

⚠ Prior (1.108.286): 7976 passed, 17 skipped, **0 failed**; ⚠ Prior (1.108.285): 7945 passed, 17 skipped, **0 failed**; ⚠ Prior (1.108.284): 7894 passed, 17 skipped, **0 failed** **+ `uv run ruff check src/` clean**. ⚠ Reconciled by same-tree collect: **7911 with `test_code_index_path_is_honoured.py`, 7902 without = exactly its 9**, and 7902 is .283's total, so nothing else moved. ⚠⚠ **This release also measured the REAL STORE, which no pass count can show**: a full run now CREATES nothing under `~/.code-index` and emits no `_watcher_*.signal`, so the process-lock scopes are isolated. `_savings.json` and `session_stats.json` still move, because `token_tracker` was deliberately left on the home default (see Current State). **Assert the side effect, not just the exit code.** ⚠ Prior (1.108.283): 7883 passed, 17 skipped, **0 failed**, and the 3.13 CI-env reproduce returned the SAME totals AND the same skip split — stronger than the usual same-total-different-split. ⚠⚠ **TWO INDEPENDENT FALSE-GREEN MECHANISMS were found across these two releases and BOTH reported `exit code 0`.** (1) `PYTHONPATH=src python -m pytest tests/ -n 4 --dist loadfile` — **pytest-xdist lives in the dev group inside `.venv` and is INVISIBLE to a bare `python -m pytest`**, so pytest rejected the flags, collected NOTHING, and exited 0 while the harness reported success. **Use `uv run pytest` whenever xdist flags are passed.** (2) **A trailing `| tail` swallows pytest's exit status** — a run with one real failure was reported as "exit code 0", because the pipeline's status is tail's. **Write to a log and echo the exit code BEFORE any pipe**; every number in this line was obtained that way. ⚠ Local suite is `uv run pytest tests/ -n 4 --dist loadfile` at ~200-300s against ~600s serial; CI pins `-n 4`, deliberately not `-n auto`. Prior (1.108.282): 7849 passed, 10 skipped, **0 failed** **+ `uv run ruff check src/` clean**. Prior (1.108.281): 7848 passed, 10 skipped, **0 failed**. ⚠⚠ **Reconciled by a SAME-TREE COLLECT against `origin/main`, and arithmetic against the previous release line would have been wrong by 16** — `main` moved twice between .280 and this bump (#474's 14 tests, #477's 2), so the usual "delta from the last release" method had two unrelated merges inside it. **Pick the method that matches how the work landed.** Measured: **7858 collected on the branch vs 7847 on `d10490e`, +11.** Decomposition: `test_v1_108_281.py` **10**, plus a net **+1** from the ratchet rearranging — four languages leave `EXEMPT` and join `test_declared_constant_pattern_extracts_a_constant` (+4) while the four `test_exemptions_are_not_stale` cases collapse into ONE empty-parametrize item (-3). ⚠ **The 10th skip is that empty parametrize** and is the ratchet AT REST, not a lost test; it re-arms the moment anyone adds an exemption (same shape as `_JS_VARIANT_EXEMPT` in .273). ⚠ The release commit adds no tests, so the post-bump run reproduces the pre-bump 7848/10 exactly. ⚠ 3.13 CI-env reproduce **7842 passed / 16 skipped, the SAME 7858 TOTAL**, different skip split, via `uv run --python 3.13 --group dev --extra watch python -m pytest tests/ -q`. ⚠ Run SEQUENTIALLY after the local suite, never alongside it — two full runs share `~/.code-index` process-lock scopes and contention is the documented cause of .261's 47m outlier (.280 records the reversal). Prior (1.108.280): 7822 passed, 9 skipped, **0 failed** **+ `uv run ruff check src/` clean**. ⚠ Delta from .279's 7828 total is EXACTLY the 3 new `test_perf_db_path_resolution.py` tests, and that release carried no other code, so nothing else could have moved. ⚠⚠ **The two suites were run in SEQUENCE, not in parallel, and that was a deliberate reversal mid-release.** Both were started together, then the 3.13 arm was killed before it produced anything: two full runs on one box contend for the same `~/.code-index` process-lock scopes, and **contention is the documented cause of .261's 47m outlier**. A false red costs a re-run and, worse, a few minutes of reading a real-looking failure. **Sequence them; the wall-clock saving was never worth the ambiguity.** ⚠ 3.13 CI-env reproduce **7816 passed / 15 skipped, the SAME 7831 TOTAL**, different skip split, via `uv run --python 3.13 --group dev --extra watch python -m pytest tests/ -q` — without `--extra watch` it collects 105 fewer and reports a clean pass (see .278 below). Prior (1.108.279): 7819 passed, 9 skipped, **0 failed** **+ `uv run ruff check src/` clean**. ⚠ Delta from .278's 7808 total is EXACTLY the 20 new `test_schtasks_locale.py` tests; the release's other half is docs-only, so nothing else could have moved. ⚠ 3.13 CI-env reproduce **7813 passed / 15 skipped, the SAME 7828 TOTAL**, different skip split. Prior (1.108.278): 7799 passed, 9 skipped, **0 failed** **+ `uv run ruff check src/` clean**. ⚠ Reconciled by DECOMPOSITION against .277's 7797 total: `test_identity_normalized_tier.py` 10 (#458) + `test_schema_baseline_transcription.py` 2 (#467) **- 1 REMOVED** (`test_the_core_compact_schema_budget_is_unchanged`) = **+11**, and 7797 + 11 = 7808 exactly. **A removal is part of the delta and the usual add-only arithmetic hides it.** ⚠⚠ **THE DOCUMENTED 3.13 REPRODUCE COMMAND UNDER-COLLECTS BY 105 TESTS, and it reports a clean pass while doing it.** `uv run --python 3.13 python -m pytest tests/ -q` collected **7703** against the local 7808. The missing 105 are ENTIRELY three watcher files (`test_watcher_serve.py` 49, `test_watcher_lock.py` 40, `test_watcher_dynamic.py` 16), each gated on `pytest.importorskip("watchfiles")` — and `watchfiles` is an OPTIONAL extra. **CI installs it** (`uv sync --locked --group dev --extra watch`, `test.yml:84`); the documented command does not. **Use `uv run --python 3.13 --group dev --extra watch python -m pytest tests/ -q`** — that run is **7793 passed / 15 skipped, the SAME 7808 TOTAL**, different skip split. ⚠ **The totals convention is what caught it**: passed counts alone read as a plausible pass either way, and a whole subsystem being absent is invisible from `N passed`. ⚠ **Do NOT read this as .277's number being wrong** — 7782 + 15 = 7797 is internally consistent, so that run DID collect the watcher tests. `uv run` reuses an already-synced environment, so the same command can collect differently depending on what last synced it. **The command is unreliable, not that record.** Prior (1.108.277): 7788 passed, 9 skipped, **0 failed** **+ `uv run ruff check src/` clean**. ⚠⚠ **This release adds NO test file of its own and a flat delta would have been the RED flag on any other release** — every prior one ships a `test_v1_108_NNN.py`, so "no new tests" normally means the bump outran the work. Here the work landed across the day in #459/#462/#463/#464 and the release commit is version metadata + changelog + rotation only. **Reconciled by DECOMPOSITION rather than a same-tree collect**, because the collect diff has nothing to subtract: `test_html_file_class.py` 4 (#459) + `test_v1_108_277.py` 6 (#462) + `test_pid_reuse_identity.py` 10 (#451 via #464) + `test_claude_md_rotation.py` 4→9 = +5 (#463) = **25**, and .276's 7763 + 25 = 7788 exactly. ⚠ **Pick the reconciliation method that matches how the work landed**; applying the usual one here yields a zero and proves nothing. ⚠ 3.13 CI-env reproduce: **7782 passed / 15 skipped**, same 7797 TOTAL, different skip split — compare totals across interpreters, never passed counts. Prior (1.108.276) **+ `uv run ruff check src/` clean**. ⚠ Reconciled by same-tree collect: 7772 total, 7753 with `test_v1_108_276.py` ignored (= its 19); the **+5 over .275's 7748 is five new `def test_` functions in `test_tools.py`** from the #438/#439 drive-root work — COUNTED in `git diff v1.108.275..HEAD`, not inferred, because "nothing else moved" was not true this release and asserting it would have been the same shape of error the count notes below are about. ⚠⚠ **The 3.13 CI-env reproduce totals the SAME 7772 but splits 7757 passed / 15 skipped** — six tests that RUN on 3.10 SKIP there. **A passed-count comparison ACROSS interpreters is meaningless; compare TOTALS.** ⚠ **The 9th skip is the POSIX-only orphaned-inode test for #442** — Windows refuses to unlink a file with an open handle, so this box CANNOT produce that case. **Do not read that skip as cross-platform coverage**; it is a real local gap covered only by the portable unit test for the predicate. Prior (1.108.275) **+ `uv run ruff check src/` clean**. ⚠ Reconciled by same-tree collect: 7748 total, 7734 with `test_v1_108_275.py` ignored (= its 14), and 7734 is exactly .274's total, so nothing else moved. Prior (1.108.274) **+ `uv run ruff check src/` clean**. ⚠ Reconciled by same-tree collect: 7734 total, 7728 with `test_security_disclosure.py` ignored (= its 6), and 7728 is exactly .273's total, so nothing else moved. ⚠⚠ **This line was briefly written with a GUESSED number before the run finished, and the guess (7734) was the TOTAL rather than the passed count — it would have read as a plausible, wrong figure.** Never pre-write a count; the run is the only source. Prior (1.108.273) **+ `uv run ruff check src/` clean**. ⚠ Reconciled by same-tree collect: 7728 total, 7717 with `test_v1_108_273.py` ignored (= its 11), and the +1 over .272's 7717 is `next` ENTERING the #435 sweep now that its exemption is gone. ⚠ **The 8th skip is EXPECTED and is not a lost test**: `_JS_VARIANT_EXEMPT` is empty, so the ratchet parametrizes over an empty set and pytest skips it ("got empty parameter set"). That is the end state of a ratchet that did its job; it re-arms the moment anyone adds an exemption. ⚠⚠ **A version bump MID-RUN voids the run** — the rotation gate compares CLAUDE.md to `pyproject.toml`, so a suite spanning the bump is not evidence. Bump and rotate FIRST, then run once. (Done wrong on .273 and the run was discarded.) Prior (1.108.272) **+ `uv run ruff check src/` clean**. ⚠ Delta is EXACTLY the 9 new `test_v1_108_272.py` tests, reconciled by COLLECTING the same tree twice (7716 with the file, 7707 with it `--ignore`d) rather than by arithmetic against this line. ⚠⚠ **That method was forced, because this line was STALE by ~239 for two releases** — it read "7470 (1.108.269)" while .270's 31 and .271's 124 were never folded in, so the documented baseline was unusable as one. **A count that is only ever appended to during a release rots the moment a release skips it**; prefer a same-tree collect diff, which cannot go stale, and treat this number as a report rather than a baseline. ⚠⚠ **The count was mis-reported once during this release and the ARITHMETIC caught it, not the reading** — an intermediate run was quoted as "7469 passed, 0 failed", a combination that never happened: it was 7469 passed WITH 1 failed, totalling 7470. **Always reconcile passed+failed against the prior release's total plus the new test count**; eyeballing `N passed` at the end of a 17-minute run is how a red run gets read as green. ⚠ The failure was the CLAUDE.md rotation gate correctly refusing a Current State naming 1.108.269 while `pyproject.toml` still read .268 — **the gate fires BEFORE the version bump lands, so a red rotation test mid-release is expected and must not be waved through as "just the gate"**; it clears only when every pin site agrees. **Prior (1.108.268):** 7436 passed, 7 skipped, **0 failed** **+ `uv run ruff check src/` clean**. ⚠ Delta from .267's 7428 is EXACTLY the 8 new `test_stdio_guard.py` tests; nothing else moved. ⚠⚠ **The CLAUDE.md rotation gate caught a real mistake this release** — a 4th entry was added without demoting .267 or moving the `Older releases` boundary, and the gate failed the build rather than letting the history drift. **Prior (1.108.267):** 7428 passed, 7 skipped, **0 failed** **+ `uv run ruff check src/` clean**. ⚠ Delta from .266's 7404 is EXACTLY the 24 new `test_constant_extraction_guard.py` tests; nothing else moved. **Prior (1.108.266):** 7404 passed, 7 skipped, **0 failed** (isolated worktree run) **+ `uv run ruff check src/` clean + CI all 9 jobs green on the pushed SHA**. ⚠ The delta from .265's 7394 is EXACTLY the 10 new `test_format.py` cases; nothing else moved. ⚠⚠ **Nothing moving is itself the finding** — not one existing test pinned a fusion or semantic confidence value, which is precisely why a ~5x mis-scaling shipped and survived. ⚠ **+17 after .264 shipped**: the file-IO scanner needed TWO MORE iterations (see below), test-only, no bump. ⚠⚠ **A green suite is NOT a green build** — lint was RED for four releases while this line said 0 failed. Quote ALL THREE (suite, ruff, CI) from now on. ⚠⚠ **A green suite is NOT a green build** — lint was RED for four releases while this line said 0 failed. Quote BOTH numbers here from now on, and read the CI run for the pushed SHA. ⚠ **.261's run took 47m45s against ~16-17m before and after it on the same tree** — same counts, same result, so it was machine contention and NOT a signal. Do not treat a wall-clock outlier as a regression. ⚠⚠ **A config change is the one edit whose blast radius is the whole suite** - 128 test files touch `_GLOBAL_CONFIG` directly, so a "small" resolver change is never a small run. ⚠ **The "KNOWN 12 local-ONNX `test_semantic_search` env failures" are GONE** — .207's autouse `no_local_onnx` fixture fixed them, so a local run is now fully green and **any** red is a real signal. Do not carry that 12-failure allowance forward; it papered over a real failure once already (.197 had one hiding inside it). ⚠ **Still do not eyeball the COUNT** — diff the FAILED names against the same tree with your changes stashed; for .199 and .205 that diff was empty, and for .209 the failure set was empty outright, which is the one case that needs no baseline. ⚠ **Stashing is the wrong tool when the change is already committed and pushed** — for .205 the comparison ran in a throwaway `git worktree add --detach <pre-release-sha>`, which also survives a concurrent writer in the main tree.

## Rotated from CLAUDE.md Current State at 1.108.301 (2026-08-26)

- **Prior (1.108.298):** **A campaign that saw nothing must not certify everything.** `refresh`'s pre-stamp discovery asked only whether the corpus had GROWN (`current - known`) and for its whole life could not see the opposite failure: a source root that has MOVED, been UNMOUNTED, or been CLEANED makes discovery return `[]`, so `current` and `known` are both empty, nothing drifts, nothing errors, and the campaign stamps the target generation having re-parsed **ZERO files**. ⚠⚠ **UNREPAIRABLE, which is what lifts it above a wrong number** — a stamp EQUAL to the constant is indistinguishable from a genuine one, so **the tool built to drain the exempt bucket was filling it**, and the way in was running the documented command. Found on the three pinned benchmark corpora: bare `.git` dirs, 8,220 pre-`.246` symbols, all three stamped `2` in under a second each. Now refuses on `corpus_unreadable`; ⚠ `_index_files` returning `None` refuses too (`index_unreadable`) — UNKNOWN blocks, same rule as `has_any()`. ⚠ **EMPTY-vs-NON-EMPTY deliberately, NOT a shrink threshold**: a repo may legitimately lose most of its files, so the partial case is DISCLOSED as `indexed_files_not_reparsed` rather than guessed at. Also **re-measured the benchmark reference, stale 22 days**: 27.9x -> **27.4x** vs grep-top-3, 237.3x -> **233.4x** vs read-all — our side moving AGAINST us, which is the failure Practice 4 exists for. ⚠ gin is the clean parser signal (+81 symbols from `#428`, identical corpus); express/fastapi each gained 4 files at the SAME commit, which is COVERAGE not parsing, and fastapi's symbol count did not move at all. ⚠⚠ **EIGHT artifacts mirror one run, not four** — both sync tests passed with FIVE still on August-3 figures, including README's line-3 tagline and a table whose grand total and per-repo rows were 22 days apart.  **Also ships Racket (`.rkt`/`.rktl`/`.rktd`), #548 by @otherjoel** — a custom head-symbol walker, because the tree-sitter grammar is fully HOMOICONIC (no named `define`/`struct` nodes; `(...)` and `[...]` share the `list` type), same shape as the three Lisps already here. ⚠⚠ **The PR's own point is the MEASUREMENT, not the feature**: `benchmarks/racket_fidelity/` scores the extractor against Racket's own expander over 211 files / 3,526 definitions, with `extra` and `wrong_span` **BOTH 0** and gated in CI off frozen oracle data so the check runs with no Racket installed. `syntax-original?` separates human-typed names from macro-introduced ones — without it the gap looks several times worse than it is. ⚠ `missing` (485, 86.2% coverage, **152 of 211 files completely clean**) and `callable_unknowable` (212) are REPORTED not gated, because neither is reachable by parsing more carefully. ⚠ **No `PARSER_GENERATION` bump and the reasoning is theirs, verified independently**: that counter re-parses files ALREADY in an index; `.rkt` was `wrong_extension` everywhere, so Racket arrives through DISCOVERY. Coverage, not extraction. ⚠⚠ **Known and pre-existing, disclosed by them, affects EVERY language ever added**: an explicit `languages` list — which `jcodemunch-mcp init` WRITES — never picks up a new language, and `config --upgrade` only injects missing KEYS so it cannot repair a list. ⚠ `.scrbl` deliberately unsupported ON A MEASUREMENT: it parses with `has_error: False` and yields garbage, and a green parse with an empty result is worse than no support. [[a-one-directional-check-certifies-its-blind-side]] [[a-sync-ratchet-that-checks-the-total-misses-the-rows]]

## Rotated from CLAUDE.md at 1.108.302-dev (2026-08-27)

Section: 'Open threads — verify, do not quote'. Rotated because it named
two issues whose state it could not vouch for and pointed at the live
surfaces anyway, which is the rule it was restating.

### Open threads — verify, do not quote

`#375` (Linux stall, needs a re-run not a patch) and `#377` (Phase 2 P3 edges)
were the last two carried here. Both may have moved. The catalog moratorium is
tracked in `Current State` and `ROADMAP.md`, which are the live surfaces.

