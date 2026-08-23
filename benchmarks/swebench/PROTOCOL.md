# SWE-bench Verified — protocol, registered before any instance is run

## The question

Does an agent with jCodeMunch fix more real GitHub issues than the same agent
without it?

Every benchmark this project owns measures tokens saved or retrieval recall.
None measures whether the work got done. That gap is why the catalog moratorium
keeps grinding: `route` is judged on whether it picks the labelled action, when
the question a user has is whether the issue got fixed.

## What this pilot is, and what it may NOT conclude

**This is a 50-instance PRICING RUN. It publishes nothing, whatever it says.**

Registered here so a good-looking pilot cannot be quoted later. At n=50 the
design cannot resolve the effect it is looking for, in either direction:

    Paired design, McNemar exact, alpha=0.05, contested=30% (ASSUMED)

        n     +6pt    +10pt    +12pt
       50      7%     18%     27%
      100     16%     37%     52%
      150     22%     56%     73%
      200     29%     71%     86%
      300     43%     87%     96%
      500     67%     98%    100%

Printed by `power.py`, not typed. Re-run it if the design changes.

⚠⚠ **Read the top row before quoting anyone's 50-instance result, ours or a
competitor's: a real 12-point effect is detected 27% of the time.** A published
50-instance win is one draw from a distribution that hides three quarters of the
true effects, and a 50-instance NULL is nearly uninformative. That is the whole
reason this run is a pricing exercise and not a result.

⚠ `contested` is an assumption, not a measurement — the fraction of instances
where the arms could plausibly disagree at all. Measuring it is one of the four
outputs below, and it is what makes the real run's size a computed number rather
than a guess.

## What the pilot measures

Four things, none of them a solve rate:

1. **Dollars and wall-clock per instance**, per arm. The real run's size is a
   budget decision and there is currently no number under it.
2. **The contested fraction.** Replaces the assumption above.
3. **Per-instance index build time and cost.** Every SWE-bench instance sits at
   its own base commit, so this is hundreds of index builds across ~12 repos,
   not twelve.
4. **Peak disk.** See the blocker below.

## Design (fixed now, not after seeing results)

- **Two arms.** Claude Code cold, versus Claude Code + jCodeMunch. No third
  surface arm: `counter`-vs-`full` triples the cost to answer a question nobody
  outside this repo has asked.
- **Paired.** Both arms run the same instances. Pairing is what buys the power
  in the table; unpaired, every number above gets worse.
- **McNemar exact on discordant pairs.** Concordant pairs are not evidence.
- **k >= 2 repeats per instance per arm.** Agents are stochastic. A single pass
  reports one draw as if it were the value.
- **Grading is the official harness, unmodified.** `swebench eval verified`.
  That is the entire credibility of the number. We do not write a scorer.

## Setup cost is charged to us

Index build time and dollars count **against the jCodeMunch arm**, with the
figure reported separately beside the result.

⚠ The alternative — treating the index as pre-existing, like a warm cache — is
defensible for a returning user and is the first thing a skeptic reaches for.
Excluding our own setup cost is the kind of omission that gets found by someone
else later, and then the finding is about us rather than about the number.

## Pre-registration

The evidence of pre-registration is **commit order**: this file lands before any
instance is run and before any result file exists. See `git log` for this
directory. Nothing else can be evidence of it.

**We publish the result whichever way it goes.** A negative is a finding about
what jCodeMunch does not do, and this project has published one before
(`route_binary_pilot/RESULT.md`, H3 refuted).

⚠⚠ **The honesty gate that fired on `codex_surface` applies here unchanged**:
if the instrument cannot resolve the effect, we report that it could not, and we
do not report the arm numbers as though it had. That benchmark's arms differed
by 568,617 tokens against a baseline varying against ITSELF by 1,143,229, and
the arm numbers are still not quoted anywhere.

## Known blocker: storage

The harness documents **120 GB free storage, 16 GB RAM, 8 CPU cores** for
x86_64.

Measured on the dev box 2026-08-23: **24 cores, 34.1 GB RAM — both fine. Disk is
not: C: has 45 GB free of 952 (96% used), G: has 42 GB of 100.** Neither volume
fits the requirement, and no combination of them does.

⚠ The 120 GB figure covers the full 500-instance set. A 50-instance pilot pulls
a subset, so the pilot is likely to fit — that is a guess, and item 4 above is
what replaces it with a number.

⚠⚠ **The 200-to-300 instance run cannot happen on this machine.** Whatever the
pilot says about effect size, the real run needs a host with room. Deciding that
is cheaper before the pilot than after.
