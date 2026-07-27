# Sherlock submission — Tare

> Fill in the two `<!-- LINE -->` markers with permalinks to the contest commit before pasting.
> Everything else is ready as-is.

---

## Title

`Any loan NFT holder will permanently freeze deposits, redemptions and all portfolio operations for PortfolioVault shareholders`

---

## Summary

The one-way `navStart` flag in `PortfolioVault.updateNav` will cause a permanent freeze of deposits,
redemptions and every privileged vault operation for vault shareholders, as any holder of a loan NFT
will push one unsolicited NFT into the vault between two `updateNav` transactions, resetting the
pagination cursor so the NAV cycle never finalises and `navStart` never returns to `0`.

---

## Root Cause

In `PortfolioVault.sol:updateNav` <!-- LINE --> the restart branch discards all pagination progress
whenever the vault's NFT ownership nonce changed since the cycle began:

```solidity
} else if (
  currentNonce != lastOwnershipNonce ||
  currentConfigurationVersion != lastCalculatorConfigurationVersion ||
  block.timestamp - navStart > maxNavComputationTime
) {
  navStart = block.timestamp;
  navCursor = 0;      // all progress discarded
  pendingNav = 0;
  lastOwnershipNonce = currentNonce;
  ...
}
```

`navStart` is written in exactly three places, all inside `updateNav`: set on first entry, re-set on
restart, and cleared **only** in the finalisation branch reached when `cursor >= _navLoanIds.length`.
There is no setter, no admin reset and no guardian override.

The restart condition is externally controllable because `LoansNFT.sol:_update` <!-- LINE --> bumps
the recipient's nonce unconditionally:

```solidity
unchecked {
  if (from != address(0)) ++ownershipNonce[from];
  if (to != address(0)) ++ownershipNonce[to];   // no consent check on the receiving side
}
```

Any third party can therefore force a restart at will. Because `_requireIdleNav()` and
`_requireFreshNav()` both begin with `require(navStart == 0, NavComputationInProgress())`, holding the
cycle open holds the entire vault closed.

---

## Internal Pre-conditions

1. `PORTFOLIO_MANAGER` needs to have curated a NAV list large enough that a full sweep cannot complete
   in a single transaction — the multi-batch mode the pagination machinery (`batchSize`, `navCursor`,
   `pendingNav`, `maxNavComputationTime`) exists to serve. **Measured threshold** (harness, verbatim
   `updateNav`, per-loan reads matching `getLoanValues`): a sweep costs `162,815 + ~4,265 × n` gas, so
   `_navLoanIds.length` needs to be **above ~2,300 loans** for a single 10M-gas transaction to be
   impossible. **The deployment target is Avalanche C-Chain, whose block gas limit is 15,000,000** —
   half of Ethereum's — so the concrete ceilings are:

   | transaction size | max loans in one sweep |
   |---|---|
   | 15M — an entire C-Chain block, nothing else in it | **3,478** |
   | 10M — already a very large transaction | **2,306** |
   | 7.5M — half a block | **1,720** |

   Above roughly **1,700–2,300 loans** the manager must paginate, and pagination is the precondition.
   The true figure is lower still: the real path additionally materialises a 5-field `LoanValue[]`
   across an external call, which this harness does not model.

   Note also that the C-Chain targets 15,000,000 gas per 10-second rolling window. A manager burning
   a full block on a sweep that is then discarded is consuming the chain's entire throughput target
   for that window, repeatedly, to make no progress.
2. `PORTFOLIO_MANAGER` or `INVESTOR_MANAGER` needs to call `updateNav()` to set `navStart` to go from
   `0` to non-zero — this happens on every routine NAV refresh and is required before any deposit or
   redemption can be approved.
3. The attacker needs to hold one loan NFT per `updateNav` transaction — loan NFTs are freely
   transferable and tradeable through `LoansExchange`, and the trust model states that the investor
   identified by NFT ownership "can potentially be untrusted".
   *(Only for the cheaper amplifier variant: guardian would need to have called `approveOriginator()`
   on the attacker, who then calls `registerAddress(Roles.Investor, <vault address>)` on its own
   permissionless book. Not required for the finding.)*

## Scope

Three clauses of the contest's own Q&A place this in scope, and one nearby exclusion does not reach it:

- **In scope, explicitly:** *"Any value or array-length input reachable by an **untrusted** party
  (Borrower, Investor, or an arbitrary caller) that is not adequately bounded **is in scope**."*
  The unsolicited NFT push is exactly that — an unbounded, unauthenticated input from an arbitrary
  caller that drives `updateNav`'s restart branch.
- **The exclusion does not apply.** The Q&A excludes array-length DoS where *"the resulting gas/DoS
  exposure requires a **trusted role** to supply an oversized array."* No oversized array is supplied
  here by anyone. `_navLoanIds` grows through ordinary curation of a real portfolio; what forces the
  restart is an untrusted third party, not an argument passed by a manager.
- **Named impacts:** the Q&A lists as items of interest *"Loans NFT being stuck"* (the vault's entire
  portfolio, since `transferLoans` is gated behind the stuck flag) and *"Going into a state that is
  unrecoverable (bricking)"* (every privileged entry point, with no on-chain reset).
- **Trust model:** the finding's primary route uses no trusted role at all. Where a trusted role is
  mentioned, it is only as a cheaper variant, and it is flagged as such rather than relied on.

---

## External Pre-conditions

None.

The attack uses no oracle, no external protocol, no price movement and no specific gas price. The
only timing requirement is internal to this protocol: the attacker's transaction must land in any
block between two of the manager's `updateNav` transactions. `updateNav` is a public transaction, so
reacting to it is sufficient — no front-running is required.

---

## Attack Path

1. **`PORTFOLIO_MANAGER` calls `updateNav(batchSize)`** on a portfolio too large to sweep atomically.
   `navStart` is set to `block.timestamp`, `lastOwnershipNonce` is snapshotted, the cursor advances by
   `batchSize`, and the cycle does not finalise.
2. **The attacker calls `LoansNFT.transferFrom(attacker, <vault address>, tokenId)`** with any loan
   NFT they hold. `LoansNFT._update` bumps `ownershipNonce[vault]`. The vault cannot refuse: the
   protocol deliberately uses the non-safe ERC-721 variants (known issue #20), so there is no
   receiver hook to reject the delivery, and `LoansNFT` is not `Pausable` — `_update` has no pause
   check, so no pause anywhere in the system stops this.
   No role is required. This is the route the finding rests on, and the contest's own trust model
   names it: *"The Investor is identified by loan-NFT ownership which can potentially be untrusted."*
   *(Cheaper variant, if the attacker also holds originator approval: `Loans.create(..., investor = <vault>, ...)`
   mints a fresh NFT into the vault for free — `_create` validates the investor only against the
   originator's own book and moves no tokens. Originator is listed as trusted **without** the
   "can hurt other loans/users" carve-out that Borrower/Investor/Servicer get, so this variant is
   offered only as an amplifier, not as the basis of the finding.)*
3. **`PORTFOLIO_MANAGER` calls `updateNav(batchSize)` again.** `currentNonce != lastOwnershipNonce`, so
   the restart branch fires: `navCursor = 0`, `pendingNav = 0`. The batch the manager just paid for is
   discarded and the sweep begins again from index zero.
4. **The attacker repeats step 2 once per `updateNav` transaction.** The cursor never reaches
   `_navLoanIds.length`, the finalisation branch is never entered, and `navStart` never returns to `0`.
5. **Every entry point is now bricked.** `approveDeposit`, `approveRedemption`, `collectCashflows`,
   `fundLoan`, `fundLoans`, `addLoansToNav`, `removeLoansFromNav`, `acceptSaleOffer`, `transferLoans`,
   `setCalculator` and `setLoans` all revert with `NavComputationInProgress()`.

No configuration lever exits this state. `setMaxNavComputationTime` is not idle-gated and so is
callable, but it only relaxes the third disjunct of the restart condition — the nonce mismatch is the
first, and no setter touches it. Pausing does not help either: `updateNav` is `whenNotPaused`, so
pausing merely stops progress, and `LoansNFT` is not `Pausable` at all — `_update` has no pause check,
so NFT transfers into the vault keep bumping the nonce regardless of what is paused. Pausing `Loans`
blocks the `create` variant of step 2 but not the plain-transfer variant.

---

## Impact

The vault's shareholders **cannot redeem**: `approveRedemption` is unreachable for as long as the
attack runs, so the entire vault's capital is immobilised. The vault is simultaneously inoperable —
no capital can be deployed to loans, no repayments collected, no valuation model swapped, and the
`setLoans` migration path that the protocol documents as its recovery mechanism is itself gated
behind the stuck flag.

The attacker gains nothing and loses only gas — this is griefing. The cost asymmetry is what makes it
sustainable, and it is **measured, not asserted**:

| | gas per round |
|---|---|
| Attacker, Route A (`transferFrom` into the vault, cold storage) | **24,227** |
| Attacker, Route B (`create` minting into the vault, cold storage) | **98,669** |
| Manager, one discarded batch @ `batchSize = 50` | 324,178 — **13×** Route A |
| Manager, one discarded batch @ `batchSize = 100` | 534,680 — **22×** |
| Manager, one discarded batch @ `batchSize = 250` | 1,166,678 — **48×** |
| Manager, one discarded batch @ `batchSize = 500` | 2,222,025 — **91×** |

Every round the attacker pays once and the manager pays for an entire batch that is then thrown away.
The ratio worsens the harder the manager tries to finish: a larger `batchSize` is more progress lost
per bump. A manager who paginates at 500 burns 91 gas for every 1 the attacker spends, and still ends
the round no closer to finalising than when they started.

Two limits, stated for accuracy:

- The freeze persists while the attacker keeps paying, so it is indefinite rather than irreversible.
- `Rescuable` is not idle-gated, and `createSaleOffer` / `cancelSaleOffer` are not idle-gated either,
  so a guardian retains an emergency evacuation of contents — via the rescue hatch, or by selling the
  portfolio to a named buyer through `LoansExchange`. Neither unfreezes the vault, and the rescue path
  moves funds to a single recovery address without clearing any `pending*` / `claimable*` counters,
  leaving internal accounting inconsistent. Shareholder funds remain unredeemable throughout.

---

## PoC

Two artefacts are provided.

**1. `harness/` — 13 tests, all passing, runnable with no contest-repo dependency.**

```
$ forge test -vv
Ran 7 tests for test/NavFreeze.t.sol:NavFreezeTest
[PASS] test_attackerHoldsNavStartOpenIndefinitely()
  rounds run                      20
  batches a clean sweep needs     4
  furthest cursor ever reached    10
[PASS] test_routeA_plainTransferByAnyNftHolder()
[PASS] test_everyPrivilegedPathIsGatedBehindTheStuckFlag()
[PASS] test_noAdminLeverClearsNavStart()
[PASS] test_control_sweepCompletesWithoutInterference()
[PASS] test_boundary_singleTransactionSweepIsImmune()
[PASS] test_gas_derivePortfolioSizeThreshold()
...
13 tests passed, 0 failed
```

`updateNav`, `_requireFreshNav`, `_requireIdleNav`, `_addLoanToNav`, `_removeLoanFromNav`,
`_invalidateNav` and the `LoansNFT._update` nonce block are copied **verbatim** from the contest
source — every branch, assignment and ordering unchanged. Only roles, the ERC-20 and the calculator's
arithmetic are reduced to stand-ins, none of which the defect depends on. `harness/README.md` gives
the full copied-vs-stubbed breakdown.

Load-bearing result: after **twenty** batches of manager work on a portfolio a clean sweep finishes in
**four**, `navStart` is still non-zero and `navCursor` has never advanced past a single batch.
`test_control_sweepCompletesWithoutInterference` is the control — the same portfolio finalises
normally when the attacker is absent — and `test_boundary_singleTransactionSweepIsImmune` demonstrates
the precondition honestly by showing the attack *failing* against an atomic sweep.

**2. `PoC.t.sol` — the full-repo version**, which drops into a clone of `tare-io__tare-contracts` and
drives the real contracts. It encodes the same sequence against real `Loans` / `LoansNFT` /
`PortfolioVault` / `NavCalculator`. It has not been executed, and its constructor calls are marked
`// SIG?` where they need checking against the contest commit.

---

## Mitigation

Any one of these closes it; the first is the smallest change.

**1. Validate the nonce at finalisation instead of discarding progress mid-sweep.** Keep sweeping and
compare `ownershipNonce` against the snapshot only in the finalisation branch, restarting at most once
per genuine change rather than once per attacker transaction. This preserves the freshness property
the nonce exists to enforce while removing the unbounded restart.

**2. Give `navStart` an escape hatch.** Worth adding regardless of (1):

```solidity
function abortNavComputation() external onlyAdminOrGuardian {
  navStart = 0;
  navCursor = 0;
  pendingNav = 0;
}
```

This alone converts a permanent freeze into a recoverable one.

**3. Do not let unsolicited NFTs move the nonce.** The vault already maintains a curated list and
deliberately ignores donated NFTs for valuation — *"Donations landing in the vault are not added
automatically and therefore cannot influence NAV"*. The liveness path should follow the same
principle: only churn within `_navLoanIds` should trigger a restart. As written, the vault correctly
ignores donations for pricing but lets them destroy liveness, and that inconsistency is the bug.
