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

`currentNonce` is `loansNFT.ownershipNonce(address(this))`. It bumps whenever a loan NFT enters or
leaves the vault — including when an **unsolicited** NFT is pushed to it. One such push, landing in
any block between two `updateNav` transactions, resets the cursor to zero and throws away the entire
batch of work the manager just paid for.

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
| `transferLoans` | `_requireIdleNav` | **cannot evacuate the portfolio** |
| `setCalculator` | `_requireIdleNav` | cannot swap the valuation model |
| `setLoans` | `_requireIdleNav` | cannot migrate — the documented recovery path for #30 |

Note the last three rows: the vault's own emergency exits are gated behind the same flag that is
stuck. `setLoans` is the migration path the team names in known issue #30, and it is unreachable
precisely when it is needed.

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

**Route B — an approved originator, unlimited and free.** Known issue #4: *"A compromised or
malicious originator can name any address in any role"*, with `borrower` / `investor` / `servicer`
drawn from the originator's **own self-curated book**. Known issue #14 confirms those books are
permissionless per caller. So an originator registers `address(vault)` as an Investor in its own
book and calls `create(..., investor = vault, ...)`, which mints a loan NFT to the vault. No consent
from the vault, no funds moved, repeatable without limit.

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
- **`createSaleOffer` leaves per-token ERC-721 approvals to the exchange after the offer is cancelled
  or expires.** Known issue #25 documents the analogous residual *ERC-20* approval from
  `acceptSaleOffer` but says nothing about the NFT side. Impact requires a `LoansExchange` bug, so it
  is an exposure-window issue rather than a finding. Worth checking against `LoansExchange.sol`,
  which was not available for this review.
- **`NavCalculator.setMaxPortfolioFactor` bumping `configurationVersion` only when it clamps is
  correct**, not a bug — raising the cap alone leaves `portfolioFactor` unchanged, so a cached NAV
  computed under the old cap stays valid. Recorded because `specs/invariants.md` §7 flags it as
  worth checking; it checks out.

## Verification checklist

- [ ] **`LoansNFT.ownershipNonce` semantics — check this first, the finding depends entirely on it.**
      Confirm it is per-address, and that `_update` bumps it for the *recipient* on an incoming
      transfer and on mint. If the nonce only tracks outgoing transfers, Route B collapses and only
      Route A survives.
- [ ] `Loans.create` mints the loan NFT to the `investor` argument (corroborated by known issue #21:
      *"`fund` pulls from `loansNFT.ownerOf(loanId)` (the investor)"*) and has no check that the
      investor consented.
- [ ] `grep -n "navStart" contracts/PortfolioVault.sol` — confirm the only writes are the three in
      `updateNav`, and that no admin/guardian function resets it.
- [ ] Measure the real per-loan gas of `updateNav` against the block gas limit to state a concrete
      portfolio-size threshold. This is the single number that most strengthens the submission.
- [ ] Read the deployed `maxNavComputationTime` to quantify Route C.
- [ ] Re-check `specs/invariants.md` §6 for any liveness claim about `navStart` — if the team asserts
      termination there, quote it; it turns this from an omission into a broken stated invariant.
