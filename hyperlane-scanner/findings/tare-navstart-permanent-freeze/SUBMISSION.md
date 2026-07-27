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
   in a single transaction, i.e. `_navLoanIds.length` to be greater than one transaction's gas budget
   allows — the multi-batch mode the pagination machinery (`batchSize`, `navCursor`, `pendingNav`,
   `maxNavComputationTime`) exists to serve.
2. `PORTFOLIO_MANAGER` or `INVESTOR_MANAGER` needs to call `updateNav()` to set `navStart` to go from
   `0` to non-zero — this happens on every routine NAV refresh and is required before any deposit or
   redemption can be approved.
3. For the zero-cost unlimited variant only: guardian needs to have called `approveOriginator()` on
   the attacker, and the attacker needs to call `registerAddress(Roles.Investor, <vault address>)` to
   add the vault to its own address book (permissionless per caller).

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
2. **The attacker calls `Loans.create(borrower, investor = <vault address>, servicer, originator, principalAmount, timestamp)`.**
   `Loans._create` validates the investor only against the *originator's own* address book and then
   calls `loansNFT.mint(investor, loanId)`. The vault is never consulted, and no tokens move anywhere
   in the function. `LoansNFT._update` bumps `ownershipNonce[vault]`.
   *(Equivalent, without originator status: `LoansNFT.transferFrom(attacker, vault, tokenId)` with any
   loan NFT. Non-safe transfers are used deliberately protocol-wide, so the vault has no receiver hook
   with which to reject the delivery.)*
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
sustainable: each round the attacker pays for one cheap write (a `create` moves no tokens; a transfer
is a single ERC-721 write), while the manager pays to value an entire batch of loans and has that
work discarded.

Two limits, stated for accuracy:

- The freeze persists while the attacker keeps paying, so it is indefinite rather than irreversible.
- `Rescuable` is not idle-gated, and `createSaleOffer` / `cancelSaleOffer` are not idle-gated either,
  so a guardian retains an emergency evacuation of contents — via the rescue hatch, or by selling the
  portfolio to a named buyer through `LoansExchange`. Neither unfreezes the vault, and the rescue path
  moves funds to a single recovery address without clearing any `pending*` / `claimable*` counters,
  leaving internal accounting inconsistent. Shareholder funds remain unredeemable throughout.

---

## PoC

See `PoC.t.sol` accompanying this submission.

The load-bearing assertion is `test_attackerHoldsNavStartOpenIndefinitely`: after twenty batches of
manager work on a portfolio a clean sweep finishes in four, `navStart` is still non-zero and
`navCursor` has never advanced past a single batch.
`test_everyPrivilegedPathIsGatedBehindTheStuckFlag` demonstrates the blast radius,
`test_noAdminLeverClearsNavStart` demonstrates the absence of recovery, and
`test_control_sweepCompletesWithoutInterference` is the control showing the same portfolio finalises
normally when the attacker is absent.

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
