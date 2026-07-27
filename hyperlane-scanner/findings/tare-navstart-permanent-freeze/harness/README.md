# Runnable harness — Tare `navStart` freeze

13 tests, all passing. Full output in `RESULTS.txt`.

```bash
git clone --depth 1 https://github.com/foundry-rs/forge-std.git lib/forge-std
forge test -vv
```

Requires forge (tested on 1.5.1) and solc 0.8.33. No other dependencies, no network beyond the
one clone.

## What this is, and what it is not

**It is not the contest repo.** The full-repo PoC is `../PoC.t.sol`, which drops into a clone of
`tare-io__tare-contracts` and drives the real contracts. That version has never been executed here
because the clone did not survive a container recycle.

**This is a distillation that runs.** The vulnerable control flow is copied **verbatim** from the
contest source; everything around it is reduced to the minimum needed to execute it:

| Copied verbatim | From |
|---|---|
| `updateNav` — every branch, assignment and ordering | `PortfolioVault.sol` |
| `_requireFreshNav`, `_requireIdleNav` | `PortfolioVault.sol` |
| `_addLoanToNav`, `_removeLoanFromNav`, `_invalidateNav` | `PortfolioVault.sol` |
| the `_update` ownership-nonce block | `LoansNFT.sol` |

| Reduced to a stand-in | Why it does not affect the result |
|---|---|
| roles / `AccessControl` | the bug is in control flow, not authorisation |
| ERC-20 asset token | replaced by an `idleAssets` counter; NAV finalisation arithmetic is unchanged |
| `NavCalculator` valuation maths | only `configurationVersion` and `applyPortfolioAdjustment` are touched by `updateNav` |
| `Loans.getLoanValues` | reproduces the same per-loan cold-storage read pattern so the gas benchmark is representative |

The one thing this cannot prove is that the real `Loans`/`LoansNFT`/`PortfolioVault` wire together as
modelled. That is what `../PoC.t.sol` is for. Everything the harness *does* prove — that the restart
branch discards progress, that `navStart` is never cleared, that no lever recovers it — depends only
on code copied character-for-character.

## The tests

`NavFreeze.t.sol`

| Test | Proves |
|---|---|
| `test_attackerHoldsNavStartOpenIndefinitely` | 20 batches of manager work on a 4-batch portfolio; cursor never passes 10, `navStart` never clears |
| `test_routeA_plainTransferByAnyNftHolder` | no privileged role needed — one unsolicited ERC-721 push restarts the sweep |
| `test_everyPrivilegedPathIsGatedBehindTheStuckFlag` | all 7 gated entry points revert `NavComputationInProgress()` |
| `test_noAdminLeverClearsNavStart` | neither `setMaxNavComputationTime` nor `setMaxNavAge` recovers |
| `test_control_sweepCompletesWithoutInterference` | **control** — same portfolio finalises normally when left alone |
| `test_boundary_singleTransactionSweepIsImmune` | **the precondition, demonstrated** — an atomic sweep defeats the attack |

`Economics.t.sol` quantifies the portfolio-size threshold and the cost asymmetry.
`GasCheck.t.sol` re-measures the attacker-side costs in isolation with cold storage.

## A measurement error caught and corrected — read this before quoting numbers

The first version of `test_C_attackerVsDefenderCost` measured the attacker's transfer against a vault
that had just had 500 loans minted into it. Those mints left `ownershipNonce[vault]` and the owner
slots **warm**, and the test reported **2,329 gas** for a `transferFrom` — physically impossible for
three SSTOREs, and it inflated the cost ratio to 139–954×.

`GasCheck.t.sol` exists to catch exactly this: it re-measures on fresh contracts with cold storage and
gets **28,538 gas**. `Economics.t.sol` now deploys fresh contracts per measurement and reports
**24,227 gas**, with ratios of **13–91×** instead.

The corrected numbers are the ones in the submission. They are less dramatic and they are real — a
judge who recomputes an inflated figure discounts the entire finding, so the smaller true number is
worth far more than the larger false one.
