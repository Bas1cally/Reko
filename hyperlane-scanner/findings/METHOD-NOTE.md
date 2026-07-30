## Aim for the kill

The one-line version of everything below: don't stop at "plausible," stop at "undeniable."
Tare's NFT-nonce bug was true and stayed in a duplicate cluster because reading-and-reasoning
was where it stopped. Push Chain's two Criticals stood alone because they didn't stop there — one
survived killing its own first hypothesis with a measurement, the other survived only once it
produced an actual kernel OOM-kill instead of "heap grew a lot." A finding that's merely correct
gets split with everyone else who was also merely correct. A finding driven to the kill — a
passing test, a crashed process, a quantified number nobody can argue with — doesn't.

# Method note — reachability before maths

Learned the hard way on the Kamino order-bonus finding: a wrong formula is not
a bug until an attacker can supply the input that triggers it.

That finding was fully proven at the maths level (unit test against production
types, 25% bonus vs a validated 10% cap) and still died, because
`get_liquidation_params` evaluates `check_liquidate_obligation` before the
order path and short-circuits on exactly the state the overshoot requires.

## The order of work, from now on

1. **Who can call this, and what do they control?** If the answer is "the
   owner" or "only in staging", stop — it is a hardening note at best.
2. **What state does the bug need, and can that state coexist with reaching
   the code?** Walk the control flow *backwards* from the buggy line to the
   instruction entry point. Short-circuiting `or_else`/early-return chains and
   feature flags are where candidate findings die.
3. **Only then** prove the maths.

## Where reachability is free

Prefer surfaces where an untrusted party is an intended actor, so step 2 is
satisfied by construction:

- permissionless liquidation
- oracle refresh / price ingestion
- flash loans
- anything a "public"/third-party instruction exposes

Prefer those over owner-configured features, where the attacker has to rely on
someone else's mistake.

---

# Lesson 2 — contests over live bounties, and the real reason why

Recorded 28 Jul 2026, after Tare (Sherlock contest, submitted and accepted as valid format) and
Vesu (Sherlock live bounty, real defect proven, no payable category).

## The strategic conclusion

**Prefer audit contests over live bug bounties.** Four reasons, all of them observed in this
engagement rather than assumed:

1. **No "already known to the team" exclusion.** Contest code is pre-deployment and nobody has
   reported anything yet. On the live-bounty side this killed the Vesu bad-debt finding outright:
   it had been emailed to `security@vesu.xyz` before the programme opened, and Sherlock's rules
   exclude prior-reported bugs from *both* payout and deposit reimbursement.
2. **No stake at risk.** Contests are free to submit on every platform. Sherlock's live bounties
   require 250 USDC per report, refundable only if the judge rules it valid.
3. **Severity gates are wider.** Contests accept Medium and High on impact categories like
   bricking, unfair distribution and accounting errors. Vesu's live bounty recognises only theft
   (≥1% / ≥10% of TVL), freezing and insolvency — which is why a proven, PoC-backed 21% interest
   distortion has nowhere to land.
4. **The team publishes its own threat model.** This is the one that actually produces findings —
   see below.

## The correction to "fresh code hides more bugs"

Tempting, and not what happened. Tare shipped `SECURITY.md` with 31 numbered known issues, T-1..T-10
trust assumptions, D-1..D-9 design tradeoffs, a formal `invariants.md`, and links to prior audit
reports. That is a *more* mature posture than most million-dollar programmes publish. Three findings
died on it: `Rescuable` → known issue #2, the `LoansNFT` lock path → #1, NAV freshness → tradeoff D-9.

So maturity was not the obstacle and inexperience was not the opportunity. What worked was the
method, and it works *because* the team documents itself well:

**Read the project's own security documentation first. Then hunt in the dimension it does not cover.**

For Tare that dimension was concrete: `SECURITY.md` discusses NAV *correctness* exhaustively (#7, #8,
#9, #16, #28, D-9, T-3) and NAV *liveness* almost not at all. The finding lives exactly there —
`navStart` is a one-way flag that gates every privileged function and has no reset.

> **[CORRECTED 30 Jul 2026 — see "The Tare NFT issue was ruled Invalid" at the bottom.]** This claim
> is wrong on two counts the judge later exposed: (a) the liveness/griefing behavior *is* documented
> — in `specs/vault.md`, not `SECURITY.md` — so I looked at one threat-model doc and missed another;
> (b) `navStart` is **not** no-reset: `updateNav()` completing clears it, so it is a *re-triggerable
> restart*, not a permanent one-way lock. Both errors are exactly what sank the submission.

## The reusable bug shape

The same shape found the Tare finding and the Vesu lead, in two different languages:

> **Monotonic or one-way state that gates everything, whose trip condition an unprivileged party
> controls, with no reset path.**

- Tare: `navStart` set by `updateNav`, cleared only on finalisation, restart forced by
  `ownershipNonce` which any NFT holder can bump.
  **[CORRECTED — this is the mis-application. "cleared only on finalisation" means it CLEARS: the
  manager completes `updateNav()` between transfers, so there IS a reset. It is re-triggerable
  griefing, not a no-reset lock. The shape was matched on a criterion the target didn't actually
  satisfy. See bottom.]**
- Vesu: `last_rate_accumulator`, monotonic, hard ceiling at `18 × SCALE` in
  `assert_security_invariants`, no setter anywhere.

Ask of any candidate: *what state only ever moves one way, what does it gate, and who can move it?*

## Target-selection checklist

1. Contest, not live bounty — unless a finding is genuinely undisclosed and clears the programme's
   own severity definitions.
2. Repo publicly clonable, and the toolchain reconstructible offline. `scarbs.xyz` and
   `binaries.soliditylang.org` are egress-blocked here; forge and scarb both work from GitHub
   releases, OZ has to come from GitHub as a path dependency.
3. The project publishes a `SECURITY.md` / known-issues list / invariants doc. Counter-intuitively
   this is a **positive** signal: it tells you precisely which dimension to avoid and which to attack.
4. Codebase between roughly 1k and 5k nSLOC — large enough to have liveness gaps, small enough to
   hold the whole state machine in mind.
5. Read the Q&A / scope answers for the trust model *before* the code. Tare's carve-out
   ("if they can hurt other loans/users, this can be considered valid issue") and its
   untrusted-input clause both ended up in the submission as pre-empted objections.

## And the discipline that made it submittable

Four findings were written up and then invalidated by me in this engagement — three as documented
known issues, one (the residual ERC-721 approval) as simply wrong once two contracts were read
together. Each retraction is kept in place with its reasoning rather than deleted.

That is not overhead, it is the product. The one finding that survived survived *because* the
others were killed honestly, and the submission that went out states its own weakest points
(the portfolio-size precondition, the partial exchange exit) instead of hiding them. Judges punish
overclaiming harder than understatement, and an objection you have already answered cannot be used
against you.

## Prefer the time-boxed contest over the open bounty

Learned after Push Chain (Tare-style contest + two HackenProof FlashBounty programs, all with a
fixed audit window and a competing pool of researchers, vs. the standing/open bug bounties that
exist alongside them): a **deadline + competition** is what actually ends the hunt. It forces
"good enough, ship it" the moment a real, provable Critical is in hand, because every hour spent
gold-plating one finding is an hour a competing researcher could use to find and submit a
different one first.

An **open bounty with no time limit and no visible competition** has no natural stopping point.
Every codebase has more doors (a fresh commit, a module not yet read, a message type not yet
traced) — without external pressure forcing a cutoff, the hunt has no reason to ever call itself
done, and effort stops being effort-per-dollar-of-expected-value and starts being pure sunk cost.

Consequence for target selection: when offered a choice between a running contest/FlashBounty
(fixed window, visible submission count) and a standing open-scope bounty on the same protocol,
prefer the contest — not because the bug density is different, but because the contest supplies
the discipline an open bounty leaves entirely to us.

## A rejected Tare finding, and why — two independent kill shots

Seen after judging: a Servicer `createLedgerEntries` NAV-inflation finding, well-quantified
(146k-gas PoC, exact NAV-doubling numbers), ruled **Invalid** by the lead judge on two separate
grounds. Both are checks our own rule #1 already asks, sharpened by seeing them fail in practice:

1. **The "attacker" was the role the docs name as trusted for that exact function.**
   `SECURITY.md` (T-4) states the Servicer is trusted "to use `createLedgerEntries` only for
   legitimate accounting." The submission's entire attack *is* that trust assumption being
   violated. No PoC rigor rescues a finding whose premise is "the explicitly-trusted role
   stops being honest" — that is a rogue-privileged-user scenario, out of scope everywhere we've
   seen this rule stated. Check every function you plan to abuse against the project's own named
   trust list before investing in the PoC, not after.

2. **The cross-user-harm escalation was pre-empted by a *different* doc.** The submission tried
   the same carve-out that saved our own finding ("if they can hurt other loans/users, valid
   issue") — reasonable in principle, since it's literally the scope's own words. It still failed,
   because `specs/vault.md`'s "Single Entity Assumption" defines all vault shareholders as the
   same entity and explicitly excludes adversarial shareholder-vs-shareholder scenarios from the
   threat model. "Attacker redeems at an inflated price, diluting other shareholders" is a
   **wealth transfer between members of a group the spec already assumes is non-adversarial** —
   not cross-user harm in the sense the carve-out means.

   Contrast with why ours held: our finding froze deposits/redemptions/guardian-repair for
   *everyone*, with no winner — a systemic DoS, not a redistribution between shareholders. The
   carve-out survives when the harm is outside the assumed-single-entity group, or benefits no
   one (DoS); it dies when the harm is "one shareholder gains what another loses," because the
   spec has already defined that pair as non-adversarial by assumption.

   Before relying on a scope carve-out to escalate severity: search *every* spec/threat-model doc
   in the repo (not just the one governing the contract you're attacking) for a clause that
   quietly assumes away the exact victims your escalation depends on.

## Reading is not enough — the Tare NFT-nonce lesson

Checked the public Sherlock findings after the Tare contest opened up: many other reports
independently found the exact same bug we submitted (`LoansNFT._update` bumping
`ownershipNonce` unconditionally → `updateNav`'s restart branch never converges), down to the
same three cited lines and the same fix. Real bug, correctly reasoned — and still landed in a
large duplicate cluster, because it was reachable by reading the code carefully and connecting
two functions. That is exactly the class of bug an LLM-assisted reviewer converges on from static
reading alone, so every other researcher running Claude (or similar) over the same two files
found the same thing. Careful reading alone does not produce a differentiated finding; it
produces the median finding.

Push Chain's two Criticals were different in kind, not just in target: both survived an attempt
to *disprove* them (the first hypothesis on the derived-call bug was wrong and got killed by a
measurement before the real bug turned up on the failure path; the stream-flood claim wasn't
accepted until it produced an actual kernel OOM-kill, not just heap growth). That extra step —
build a real harness, try to break your own hypothesis, escalate until the result is undeniable —
is exactly what a reading-only pass skips, and skipping it is what most other researchers
(AI-assisted or not) also do under contest time pressure. It is the differentiator, not the
initial spot.

Consequence: treat "I found something by reading" as a hypothesis, not a finding. The bar for
"submit" should be "I ran something that proves it," not "I can explain why it should be true."

A second duplicate seen after the first (same bug, independent write-up) was sharper than ours in
one specific way worth copying regardless of duplicate status: it quantified attacker cost vs.
victim cost as a table (7x / 19x / 37x amplification at three portfolio sizes, extrapolated to
~31,000x at the spec's target scale) instead of just asserting the asymmetry. Reachability proof
answers "can this happen"; a cost-amplification number answers "why does anyone care," and it's
the second question a judge actually weighs severity on. Add it whenever the finding is a
griefing/DoS-by-cost-asymmetry shape, not just a reachability one.

**The cluster, counted.** Pulled the full 1,200-issue Tare judging list and counted: 46 of 1,200
submissions (~3.8%) are the exact same bug shape as ours (NFT transfer bumps `ownershipNonce` →
`updateNav` restart never converges → deposits/redemptions frozen), not just the 147 that merely
mention "NFT" for unrelated reasons (theft, lock-griefing, marketplace bugs). 46 independent
researchers — reading the same two functions — converged on the identical root cause and mostly
the identical wording ("any loan-NFT holder will [freeze/block/stall] deposits and redemptions").
That is the quantified version of "reading alone produces the median finding, not a differentiated
one": a bug this reachable by static reading gets found by ~4% of an entire contest's researcher
pool independently, every time, regardless of tooling.

**Fazit:** the two Push Chain Criticals never had this problem, and now there's a number to explain
why. Neither survived on "I read the code and it looks wrong" — one lived because its first
hypothesis was wrong and got killed by a measurement before the real bug turned up on the failure
path; the other lived because "the heap grew" was rejected as insufficient and pushed all the way
to a kernel OOM-kill with a PID in a dmesg log. Tare's finding was real, reachable, and *still*
landed in a 46-wide duplicate cluster because reachability-by-reading was the entire method. The
takeaway isn't "read more carefully" — 46 other people did that too. It's: once a bug is provable
by reading two functions, assume it is not differentiated, and the only way to find out is to try
to break it (build a harness, disprove your own first hypothesis, escalate the proof past
"plausible" to "undeniable") before deciding it's worth the write-up time.

## Don't turn away — the StarkNet lesson

Recorded 30 Jul 2026 after the StarkNet HackenProof contest, where the user had to push me back to
the target **twice** before I did the actual work. This is the mistake to not repeat.

What went wrong, in order:
1. **Misclassified the target and let the misclassification make the decision.** Called a running
   contest (69 days, 36 submissions) an "open standing bounty" and recommended turning away on that
   basis — inverting our own rule (we *prefer* contests). The label did the reasoning; I didn't
   check the label.
2. **Dressed up an early exit as discipline.** "It's formally verified / most-audited / caps at
   High / not our lane" all felt like rigor. They were reasons to *not start*, asserted before the
   reachability walk, the harness, and the hypothesis tests — i.e. before I had earned any verdict.
   A negative is only real *after* the full pass. Before it, "it's probably clean" is a guess
   wearing discipline's clothes.
3. **Treated "not our language" as a stop.** Cairo/zk wasn't Solidity, so I flinched — after we had
   already gone into Go/libp2p/cosmos on Push Chain and killed. Not-our-language is never the bar;
   **not-reachable** and **not-PoC-able** are, and both must be *tested*, not assumed.

What actually worked, once pushed: clone → build and **prove** the full OS prover harness →
read the Critical-tier source (both syscall paths, both class-hash impls, commitment, DA) → form a
specific hypothesis per path → test each. Every hypothesis died honestly, most for one structural
reason. That is a *real* negative, and it produced a reusable weapon (the harness) as a by-product.

The rule, for next time:

> **On a legitimate contest, go all the way in before forming any verdict. Do the reachability
> walk, stand up the harness, and test a specific hypothesis on the reachable Critical surface —
> THEN decide. Never let "audited / verified / caps low / not my language" trigger a turn-away
> before that work is done. Bank only from the far side of the full pass, never from the near side.**

This does **not** license fabricating a finding to avoid "turning away" — the no-fantasy ethic is
absolute. The two are compatible: go all the way in *and* report the honest result. The failure
mode being corrected is stopping *before* the work, not stopping *after* it with an honest negative.
The tell to catch in myself: if I'm recommending "bank / hold pulver dry" and I have **not** yet
built the harness and tested a hypothesis, I'm turning away early — push in instead.

## The Tare NFT issue was ruled Invalid — the judge's exact grounds

Recorded 30 Jul 2026. The lead judge ruled our `ownershipNonce`/NAV-restart finding **Invalid**
(not merely duplicate — *invalid*). The full reasoning, because every sentence is a reusable lesson:

> "Explicitly documented in `specs/vault.md`. Unsolicited loanNFT transfers are expected to increment
> the vault's ownership nonce and restart an active NAV computation. The spec describes this as
> intentional and acknowledges that a griefer may trigger repeated restarts. **Each transfer causes
> only one restart.** The manager can call `updateNav()` again and complete the computation unless
> the attacker keeps sending a new NFT before every batch. For a DoS to qualify as Medium, a single
> occurrence should generally lock funds for **more than a week** or affect a **time-sensitive
> function**. Neither is demonstrated. NAV-dependent approvals are **discretionary** operations
> performed by the Investor Manager…"

Three distinct, reusable kill-criteria, each of which alone was fatal:

1. **It was documented — in a doc I didn't fully read.** The behavior is in `specs/vault.md`,
   explicitly called intentional, *with the griefer scenario acknowledged*. My METHOD-NOTE claimed
   this finding lived in an "undocumented dimension." It didn't. Lesson, sharpened: "read the
   project's own docs" means **every** threat-model/spec doc in the repo, and grep them for the
   exact mechanism (here: "ownership nonce", "restart", "NAV") *before* writing up — a hit in any one
   of them is an instant kill. I checked `SECURITY.md` and stopped; `specs/vault.md` had it.

2. **Re-triggerable restart ≠ permanent freeze — and I claimed permanent.** The whole finding rested
   on "the restart branch never converges." The judge's one-line demolition: *each transfer causes
   only one restart; the manager completes `updateNav()` in between.* There is a reset (completing
   the cycle); the attacker must pay a fresh NFT transfer before **every** batch to sustain it. That
   is sustained griefing, not a one-way lock. **The reusable bug shape's "no reset path" clause must
   be tested literally: is the lock permanent from a single action, or does a normal operation clear
   it such that the attacker must re-pay each round?** If the latter, it is not a freeze — it is a
   cost-asymmetry griefing claim, and lives or dies on the amplification math, not on "it's stuck."

3. **The severity bar for DoS, stated by a judge in numbers.** "A single occurrence should generally
   lock funds for **more than a week**, or affect a **time-sensitive function**." And: blocking
   **discretionary** operator operations (here NAV-dependent approvals by the Investor Manager) does
   **not** count — no deadline, no forced loss. Bank this as the concrete DoS-severity test to apply
   *before* writing any DoS finding: (a) does one action lock for >1 week, OR (b) does it break a
   function with a hard deadline / that an unprivileged victim needs on demand? If neither, it is
   below Medium regardless of how clean the PoC is.

**How this reconciles with "don't turn away":** these are not reasons to skip the work — they are the
checks to run *as part of* the work, on the far side of the reachability walk, so the write-up either
clears them or isn't sent. Going all the way in includes grepping every spec doc for the mechanism,
proving the lock survives the victim's own recovery action (not just the first trigger), and matching
the impact against the numeric severity bar. Do all three, then submit or drop — but never skip the
hunt to avoid finding out.
