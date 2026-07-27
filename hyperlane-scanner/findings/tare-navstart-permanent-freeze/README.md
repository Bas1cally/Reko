# Tare: `navStart` has no escape hatch — a cheap, repeatable nonce bump freezes the entire PortfolioVault permanently

**Target**: Sherlock contest `tare-io` (`tare-io__tare-contracts`), 50,000 USDC.
Window **20 Jul 2026 17:00 → 29 Jul 2026 17:00 UTC**.
**File**: `contracts/PortfolioVault.sol` — `updateNav`, `_requireIdleNav`, `_requireFreshNav`.
**Severity claimed**: High (locked funds + indefinite DoS of every privileged operation). Medium is a
defensible judge outcome; the argument for High is below and stated honestly.
**Source**: verified directly against `PortfolioVault.sol`, `NavCalculator.sol` and `SECURITY.md` as
supplied from the contest repo. Not covered by any of the 31 known issues, the 10 trust assumptions,
or the 9 design tradeoffs — see "Why this is not D-9 / #16 / T-3" below.

---

## Summary

`updateNav` is paginated: it sweeps `_navLoanIds` across multiple transactions, accumulating into
`pendingNav`, and only finalises when the cursor reaches the end of the list. `navStart` is the
in-progress flag. **Every other privileged function in the vault is gated behind `navStart == 0`**,
and `navStart` is cleared in exactly one place: the finalisation branch of `updateNav`.

The restart condition is controlled by an input **any third party can move**:

```solidity
} else if (
  currentNonce != lastOwnershipNonce ||                        // <-- attacker-controlled
  currentConfigurationVersion != lastCalculatorConfigurationVersion ||
  block.timestamp - navStart > maxNavComputationTime
) {
  navStart = block.timestamp;
  navCursor = 0;          // <-- all progress discarded
  pendingNav = 0;
  lastOwnershipNonce = currentNonce;
  ...
}
```

`currentNonce` is `loansNFT.ownershipNonce(address(this))`. `LoansNFT._update` — **verified against
the contest source** — bumps it for *both* sides of every movement, with only the zero address
skipped:

```solidity
// Bump per-address ownership nonce so external integrators can detect any
// change to the NFT ownership set of a given address. The zero address is
// skipped (mint's `from`, burn's `to`) because no consumer reads that slot.
unchecked {
  if (from != address(0)) ++ownershipNonce[from];
  if (to != address(0)) ++ownershipNonce[to];   // <-- the attacker's lever
}
```

The second line is the whole finding. `to` is bumped unconditionally, which means:

- an **incoming transfer** the vault never asked for bumps it, and
- a **mint** bumps it too — `from` is the zero address and is skipped, but `to` is not.

There is no consent check anywhere on the receiving side, and by design there cannot be: known issue
#20 records that the protocol deliberately uses the non-safe ERC-721 variants so no recipient hook
can reject a delivery. One such push, landing in any block between two `updateNav` transactions,
resets the cursor to zero and throws away the entire batch of work the manager just paid for.

Repeat that once per `updateNav` transaction and the sweep never reaches the end, `navStart` never
returns to `0`, and the vault is frozen — with **no configuration lever, no admin function, and no
pause/unpause sequence that clears it.**

## The full blast radius of `navStart != 0`

Everything below reverts with `NavComputationInProgress()` for as long as the attack runs:

| Function | Gate | What is lost |
|---|---|---|
| `approveDeposit` | `_requireFreshNav` | no one can enter the vault |
| `approveRedemption` | `_requireFreshNav` | **no one can exit — investor funds are locked** |
| `collectCashflows` | `_requireIdleNav` | loan repayments cannot be pulled into the vault |
| `fundLoan` / `fundLoans` | `_requireIdleNav` (in `_fundLoans`) | idle USDC cannot be deployed |
| `addLoansToNav` / `removeLoansFromNav` | `_requireIdleNav` | curated list frozen |
| `acceptSaleOffer` | `_requireIdleNav` | cannot buy |
| `transferLoans` | `_requireIdleNav` | cannot evacuate the portfolio directly |
| `setCalculator` | `_requireIdleNav` | cannot swap the valuation model |
| `setLoans` | `_requireIdleNav` | cannot migrate — the documented recovery path for #30 |

Note the last three rows: the vault's own emergency exits are gated behind the same flag that is
stuck. `setLoans` is the migration path the team names in known issue #30, and it is unreachable
precisely when it is needed.

**One partial exit does survive, and the submission should say so rather than overclaim.**
`createSaleOffer` and `cancelSaleOffer` carry **no** `_requireIdleNav()`, so a frozen manager can
still list the portfolio on `LoansExchange` and have a named buyer settle it. That converts NFTs into
USDC inside the vault; it does not unfreeze anything. `approveRedemption` stays blocked, so the
proceeds are as immobile as the loans were, and the route needs a willing counterparty at a price the
manager does not control from a position of visible distress. The claim to make is *"investor funds
are locked and the vault is inoperable"*, not *"the assets can never move."*

## Why there is no recovery

Grepping `PortfolioVault.sol` for writes to `navStart`, there are exactly three, all inside
`updateNav`: set on first entry, re-set on restart, cleared on finalise. There is no setter, no
guardian override, no admin reset.

The three plausible escapes all fail:

1. **"Pause the vault."** `updateNav` is `whenNotPaused`, so pausing only stops progress; it does not
   clear `navStart`. The nonce lives on `LoansNFT` and keeps moving regardless of the vault's pause
   state — `Loans.create` and ERC-721 transfers are outside the vault's control entirely.
2. **"Raise `maxNavComputationTime`."** `setMaxNavComputationTime` is notably *not* idle-gated, so
   admin can call it mid-cycle. It is useless here: it only relaxes the third disjunct of the restart
   condition. The nonce mismatch is the first disjunct and no setter touches it.
3. **"Finish the sweep in one transaction."** This is the only real defence, and it is also the exact
   scenario pagination exists to handle. See "Preconditions" — if the portfolio fits in one
   transaction the attack does not work at all, and this finding does not apply.

## The economics — this is the part that makes it work

The cost asymmetry runs the wrong way:

- **Defender** pays for a full batch: `getLoanValues` over `batchSize` loans plus the calculator
  loop. Hundreds of thousands of gas, discarded.
- **Attacker** pays for one ERC-721 transfer, or one `Loans.create`. Per known issue #20, *"No funds
  move at mint time — `fund()` still requires the investor's signed allowance."* A `create` is a
  cheap write that mints an NFT and moves zero value.

The attacker does not need to front-run. They need their transaction to land in **any** block between
two `updateNav` transactions — and `updateNav` is a manager-submitted public transaction, so the
timing is observable. Reacting is sufficient; racing is not required.

## Reachability — three independent routes, in ascending order of trust required

**Route A — anyone holding a loan NFT.** Transfer it to the vault. `LoansNFT` is a normal ERC-721;
nothing stops an unsolicited transfer, and known issue #20 confirms the protocol deliberately uses
non-safe transfer variants so the recipient has no hook to reject with. Cost: one NFT per bump —
they are stuck in the vault afterwards, since `transferLoans` is itself frozen. This route needs a
supply of NFTs, so it is the weakest of the three on its own.

**Route B — an approved originator, unlimited and free.** Confirmed against `Loans.sol`.
`Loans._create` validates the investor against the **originator's own book** and mints
unconditionally:

```solidity
require(isRegisteredForRole(originator, Roles.Investor, investor), UnregisteredAddress(investor));
...
loansNFT.mint(investor, loanId);
```

Known issue #14 confirms those books are permissionless per caller, so the originator registers
`address(vault)` as an Investor in its own book and calls `create(..., investor = vault, ...)`. The
vault is never consulted. `_create` moves no tokens — it writes loan storage, mints the NFT, and
books one internal ledger entry — so the marginal cost is a cheap write, repeatable without limit.

Known issue #20 already states the primitive — *"Combined with 14, an approved originator can also
spam NFTs to arbitrary addresses at create time"* — but frames the impact purely as
*"Recipients are responsible for ensuring they can manage and transfer the NFT they hold."* That is
the gap: the disclosed consequence is an inventory nuisance. The actual consequence is a permanent
freeze of an unrelated vault's entire operational surface.

**Route C — no attacker at all.** If a full sweep takes more wall-clock time than
`maxNavComputationTime`, the third disjunct fires every cycle and the vault self-bricks. This variant
*is* recoverable, because `setMaxNavComputationTime` is not idle-gated. Worth reporting as a
sub-case: it shows the restart-with-no-escape shape is reachable through ordinary growth, not only
through malice.

Routes A and C need no trusted role whatsoever. That matters for the trust-model argument below.

## Preconditions, stated plainly

The attack requires that a full sweep of `_navLoanIds` **cannot fit in a single transaction**. If it
can, the manager calls `updateNav(N)`, the restart and the complete sweep happen atomically in that
one call, and it finalises. The attacker cannot interleave.

Three reasons this precondition is expected to hold in production:

1. Pagination with a `batchSize` parameter, a persisted `navCursor`, a persisted `pendingNav`, and a
   `maxNavComputationTime` guard is a substantial amount of machinery. It exists because the team
   expects portfolios too large to sweep atomically. A design that only ever needed one transaction
   would not need any of it.
2. `updateNav` allocates `new uint64[](batchSize)` **unconditionally**, before knowing how many
   entries it will use. Memory cost is quadratic in `batchSize`, so "just pass a huge number" is not
   available — an oversized `batchSize` runs out of gas on the allocation alone, independent of how
   many loans actually get valued.
3. Per-loan work is an external `getLoanValues` call plus a storage-heavy valuation, on a per-loan
   double-entry ledger (design tradeoff D-2: *"no cross-loan netting … expensive for batch
   operations"*).

Be honest in the submission: this is a conditional finding, and the condition is portfolio size. It
should be argued from (1) — the presence of pagination is the team's own statement that multi-batch
is the expected mode.

## Why this is not D-9 / #16 / T-3

These three are the nearest disclosed items, and all three are about **valuation correctness** —
whether the NAV number is right. This finding is about **liveness** — whether the cycle can ever
terminate. Different property, different consequence:

- **D-9** — *"the snapshot mechanism detects when the vault's NFT inventory changes mid-cycle but
  does not detect per-loan state mutations."* D-9 concerns what the nonce **fails to catch**. This
  finding is the opposite: it concerns what the nonce **does** catch, and the fact that catching it
  discards all progress with no bound on how often that can be forced. D-9 disclosing the mechanism's
  blind spot is not a disclosure that the mechanism can be weaponised for a permanent freeze.
- **#16 / T-3** — mid-cycle discount-factor changes and batch-composition bias. Both are about a
  *trusted* calculating agent skewing the resulting number. Neither mentions termination, `navStart`,
  or a third party.
- **#19** (no protocol-wide pause) and **#7** (zero-NAV bootstrap deadlock) are the only other
  liveness items. #7 is a bootstrap edge case with a documented recovery (seed a donation). This is
  a steady-state freeze with no recovery.

Nothing in the 31 items, the T-list, or the D-list mentions that `navStart` is one-way, that every
manager function sits behind it, or that a third party can hold it open.

## The trust-model argument

Route B runs through an approved originator, so expect the "trusted role" objection. Two answers:

1. **Routes A and C do not.** Route A needs only a loan NFT — obtainable by any secondary-market
   participant via `LoansExchange`, and loan NFTs are transferable by design. Route C needs no
   attacker.
2. **The carve-out applies to Route B anyway.** The contest brief's trust language for
   originators/servicers/investors carries the explicit qualifier *"if they can hurt other
   loans/users, this can be considered valid issue."* Known issue #5 bounds the analogous servicer
   damage as *"bounded per-loan (segregation holds)"*. Here segregation does not hold in either
   direction: the originator touches none of the vault's loans, holds no role on them, and yet
   freezes every shareholder's ability to exit. That is damage crossing every boundary the trust
   model draws.

## Severity

**High**, on two of the impacts the program names explicitly:

- **Funds locked.** `approveRedemption` is unreachable for the duration. Every shareholder's capital
  is immobilised, and the amount is the entire vault.
- **Bricking.** Every privileged function is unreachable, including the two evacuation paths
  (`transferLoans`, `setLoans`) that would otherwise let a guardian unwind.

The honest counterweights, which the submission should state rather than hide:

- The freeze persists only while the attacker keeps paying. It is indefinite, not irreversible.
- `Rescuable` is **not** idle-gated, so a guardian can still evacuate `assetToken` and loan NFTs to
  `recoveryAddress`. Funds are therefore recoverable — but only through the emergency hatch that
  known issue #2 documents as breaking internal accounting, and which per #31 does not clear any
  `pending*` / `claimable*` counters. The vault itself is not recoverable; only its contents are,
  into a state the team already documents as inconsistent.
- Conditional on portfolio size, as set out above.

A judge weighing the sustained-cost point down to Medium would not be unreasonable. High is the
right claim because funds are locked for the duration and the attacker's per-round cost is strictly
lower than the defender's.

## Suggested fix

Any one of these closes it; the first is the smallest change:

1. **Do not discard progress on a nonce change — validate at finalisation instead.** Keep sweeping,
   and compare the nonce against the snapshot only in the finalise branch. A single restart on a
   genuine change is fine; unbounded attacker-triggered restarts are not. Combined with (2) this
   preserves the freshness property D-9 already scopes.
2. **Give `navStart` an escape hatch**: `function abortNavComputation() external onlyAdminOrGuardian`
   that sets `navStart = 0; navCursor = 0; pendingNav = 0;`. This alone converts a permanent freeze
   into a recoverable one and is worth having regardless of (1).
3. **Do not let unsolicited NFTs move the nonce.** The vault already maintains a curated list and
   deliberately ignores donated NFTs for valuation (*"Donations landing in the vault are not added
   automatically"*). The nonce should follow the same principle — only churn within `_navLoanIds`
   should matter. As written, the vault ignores donations for pricing but lets them destroy liveness,
   which is the inconsistency at the heart of this bug.

## Secondary observations from the same read (not submitted separately)

Recorded here because they came out of the same pass and are cheap to check:

- **`acceptSaleOffer` never calls `_invalidateNav()`.** It is covered in the normal case because the
  incoming NFTs bump the ownership nonce, which `_requireFreshNav` catches. It is *not* covered if
  `offer.loanIds.length == 0` and `offer.price > 0`: the vault pays cash, receives nothing, no nonce
  bump, no invalidation, cached NAV silently overstated. Requires a `PORTFOLIO_MANAGER` to accept a
  degenerate offer, so this is self-harm by a trusted role — low value on its own, but it is the one
  cash-side NAV mutation in the contract with no invalidation and no nonce coverage.
- ~~**`createSaleOffer` leaves residual per-token ERC-721 approvals to the exchange**, giving it a
  standing ability to lock previously-listed vault loans — the vault-side mirror of known issue #1,
  and the highest-value remaining lead in the codebase.~~ **WRONG — retracted once `LoansNFT` and
  `LoansExchange` were read together.** `LoansNFT.lock` clears the approval as its first action
  (`_approve(address(0), id, address(0), false)`), and `LoansExchange.createOffer` locks every listed
  loan immediately. The approval is consumed by the lock inside the same transaction that grants it,
  and `unlock` never restores it. No residual approval exists and no standing lock capability
  follows. Kept rather than deleted because it was written up as the strongest remaining lead one
  step before the source that disproved it arrived: the mechanism was genuinely plausible from
  `LoansNFT` alone, and only reading the two contracts *together* killed it.
- **A listed loan's cashflows are unreachable by anyone while its offer is open.** Real, but
  self-inflicted and recoverable, so not submitted separately. `LoansExchange.createOffer` locks each
  listed loan with `unlocker = address(exchange)`. `Loans.investorWithdraw` pays the **unlocker**
  whenever one is set (`require(cachedUnlocker == msg.sender, Unauthorized())`), so the vault is no
  longer the authorised withdrawer and `collectCashflows` reverts — while `LoansExchange` contains no
  function that calls `investorWithdraw` at all. Interest and principal accrue in the ledger with
  nobody able to pull them until the offer is cancelled or accepted. `cancelSaleOffer` is not
  idle-gated, so a manager can always recover; the real exposure is a manager who lists loans and
  forgets them.
- **`NavCalculator.setMaxPortfolioFactor` bumping `configurationVersion` only when it clamps is
  correct**, not a bug — raising the cap alone leaves `portfolioFactor` unchanged, so a cached NAV
  computed under the old cap stays valid. Recorded because `specs/invariants.md` §7 flags it as
  worth checking; it checks out.

## Verification checklist

- [x] **`LoansNFT.ownershipNonce` semantics — DONE, confirmed against source.** Declared
      `mapping(address account => uint256 nonce) public ownershipNonce` (per-address), and `_update`
      bumps `to` unconditionally for any non-zero recipient, including on mint. Both Route A and
      Route B are live. `mint` is gated `msg.sender == LOANS_CONTRACT`, so Route B runs through
      `Loans.create` as described; there is no other mint path and no external burn.
- [x] **`Loans.create` mints to the `investor` argument — DONE, confirmed against source.**
      `_create` does `loansNFT.mint(investor, loanId)` after checking only
      `isRegisteredForRole(originator, Roles.Investor, investor)` — the originator's *own* book. No
      consent from the investor, no token movement in the whole function.
      **Note the one mitigation this reveals**: `create` is `whenNotPaused` on `Loans`, so pausing
      `Loans` stops Route B. It does **not** stop Route A — `LoansNFT` is not `Pausable` and `_update`
      has no pause check, so plain ERC-721 transfers into the vault keep bumping the nonce no matter
      what is paused. There is no pause anywhere in the system that closes this.
- [ ] `grep -n "navStart" contracts/PortfolioVault.sol` — confirm the only writes are the three in
      `updateNav`, and that no admin/guardian function resets it.
- [ ] Measure the real per-loan gas of `updateNav` against the block gas limit to state a concrete
      portfolio-size threshold. This is the single number that most strengthens the submission.
- [ ] Read the deployed `maxNavComputationTime` to quantify Route C.
- [ ] Re-check `specs/invariants.md` §6 for any liveness claim about `navStart` — if the team asserts
      termination there, quote it; it turns this from an omission into a broken stated invariant.

---

## Addendum — measured evidence (added after the harness ran)

The two open questions in the original write-up are now answered with numbers rather than argument.
Harness and full output: `harness/`, `harness/RESULTS.txt`. 13 tests, all passing.

### The portfolio-size precondition, quantified

Sweep cost measured against a verbatim copy of `updateNav`, with per-loan reads matching the real
`getLoanValues` pattern:

| portfolio | total gas | avg gas/loan | marginal gas/loan |
|---|---|---|---|
| 50 | 373,208 | 7,464 | — |
| 200 | 1,004,960 | 5,024 | 4,211 |
| 500 | 2,271,055 | 4,542 | 4,220 |
| 1,000 | 4,389,023 | 4,389 | 4,235 |
| 2,000 | 8,654,258 | 4,327 | 4,265 |

Fitting: `gas ≈ 162,815 + 4,265·n`. Single-transaction ceiling → **~2,310 loans at 10M gas**,
~3,470 at 15M, ~6,930 at a full 30M block. Above that the manager *must* paginate, which is the
precondition. The harness understates the real cost — the real path also materialises a 5-field
`LoanValue[]` across an external call — so the true threshold sits lower.

Note the marginal cost *rises* (4,211 → 4,265) while the average falls: `new uint64[](batchSize)` is
allocated up front, so memory expansion is quadratic. Trying to finish in one big call is penalised.

### The cost asymmetry, quantified

Attacker 24,227 gas (Route A, cold) or 98,669 (Route B, cold). Manager per discarded batch:
324,178 @ 50 → **13×**; 534,680 @ 100 → **22×**; 1,166,678 @ 250 → **48×**; 2,222,025 @ 500 → **91×**.

The ratio worsens the harder the manager tries to finish, because a larger `batchSize` means more
progress discarded per bump.

### A measurement error caught in-flight

The first revision of the economics test measured the attacker's transfer against a vault whose slots
had just been warmed by 500 mints, and reported **2,329 gas** — impossible for three SSTOREs — which
inflated the ratios to 139–954×. `GasCheck.t.sol` was written specifically to re-measure in isolation
with cold storage and returned 28,538; the corrected in-suite figure is 24,227.

Recorded because it is the same failure mode as the retracted approval lead further up: a number that
looked good, measured in a context that made it wrong. The corrected ratios are ~10× smaller and are
the ones that go in the submission. An inflated figure a judge can recompute costs more credibility
than the larger number could ever buy.
