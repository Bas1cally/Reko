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

## The reusable bug shape

The same shape found the Tare finding and the Vesu lead, in two different languages:

> **Monotonic or one-way state that gates everything, whose trip condition an unprivileged party
> controls, with no reset path.**

- Tare: `navStart` set by `updateNav`, cleared only on finalisation, restart forced by
  `ownershipNonce` which any NFT holder can bump.
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
