# Tare: cached NAV is never invalidated by loan-ledger changes made through `Loans`

> ## ⚠️ VERIFICATION STATUS — read before submitting
>
> This finding was derived from `PortfolioVault.sol`, `NavCalculator.sol`, `Loans.sol`,
> `LoansLedger.sol` and `specs/invariants.md` read in-session from the real repo clone. **That clone
> no longer exists** — the execution container was recycled and GitHub access in this session is
> scoped to `bas1cally/reko` only, so the quoted code below could not be re-read at write-up time.
> The quotes are exact as captured, but **line numbers are not included precisely because they could
> not be re-checked**.
>
> Before submitting: re-open the four functions named in "Verification checklist" at the bottom and
> confirm each claim against the contest commit. Every one of them is a two-minute grep. This banner
> exists because an earlier finding in this engagement was written on unverified second-hand data and
> had to be retracted — see `../vesu-programme-status.md`.
>
> **Also re-check `SECURITY.md`.** Two prior Tare findings this session turned out to be items #1 and
> #2 of the team's own 31-item known-issue list. This one has no matching entry as of the version
> read (baseline `fb12133`), but that version was demonstrably out of sync with the shipped `Loans.sol`.

**Target**: Sherlock contest `tare-io` (`tare-io__tare-contracts`), 50,000 USDC, window
**20 Jul 2026 17:00 → 29 Jul 2026 17:00 UTC**.
**Files**: `contracts/PortfolioVault.sol` (`_requireFreshNav`), `contracts/NavCalculator.sol`
(`_bucketFactor`, `getLoansValue`), `contracts/Loans.sol` (`updateLoanData`, `applyWaterfall`).
**Severity claimed**: Medium. See "Honest severity assessment" — this is not a High and should not
be argued as one.

---

## Summary

`PortfolioVault` prices every deposit and redemption off a **cached** NAV (`lastNav`). The cache is
protected by a hand-maintained conjunction of guards. The team documents the property it is supposed
to enforce, in `specs/invariants.md` §6:

> "**The master freshness invariant** (vault.md): *every* state affecting NAV — curated list, NFT
> holdings, idle USDC, **loan ledger**, `loans` pointer, calculator config — invalidates the cached
> NAV before the next `approveDeposit`/`approveRedemption`. It's maintained by a *manual conjunction*
> (nonce check + version check + explicit `_invalidateNav()` at each mutating call site + `maxNavAge`).
> **This is the highest-value property to fuzz: each new vault function must remember to invalidate,
> and a single omission is invisible until mispricing happens.**"

Six inputs are named. **Five of them are covered. The loan ledger is not covered by anything.**

## The guard, in full

```solidity
function _requireFreshNav() internal view {
  require(navStart == 0, NavComputationInProgress());
  require(lastNav > 0, ZeroNav());
  require(loansNFT.ownershipNonce(address(this)) == lastOwnershipNonce, PortfolioHoldingsChanged());
  require(calculator.configurationVersion() == lastCalculatorConfigurationVersion, CalculatorConfigurationChanged());
  require(block.timestamp - lastNavUpdate <= maxNavAge, StaleNav());
}
```

Mapping each of the six documented NAV inputs to its actual protection:

| NAV input | Protection | Sound? |
|---|---|---|
| NFT holdings | `ownershipNonce` check above; `LoansNFT._update` bumps unconditionally | yes |
| calculator config | `configurationVersion` check above | yes |
| curated list | explicit `_invalidateNav()` in `addLoansToNav` / `removeLoansFromNav` | yes |
| idle USDC | explicit `_invalidateNav()` in `_fundLoans` / `collectCashflows` | yes |
| `loans` pointer | explicit `_invalidateNav()` in `setLoans` / `setCalculator` | yes |
| **loan ledger** | **none** | **no** |

The first five are all mutated *by the vault itself*, so the vault can invalidate at its own call
site. The loan ledger is the one input mutated **outside** the vault, in `Loans`, by parties the
vault never hears from. `Loans.sol` contains no reference to the vault, no callback, no ledger nonce,
no event the vault consumes. The vault's only defence against a ledger change it did not initiate is
`maxNavAge` — a time bound, not an event bound.

## What a ledger change actually does to NAV

`NavCalculator.getLoansValue` values each held loan as *collected cash at par plus outstanding
principal at a discount*:

```solidity
int256 collectedCash = int256(loanData.investorPrincipalWithdrawable) + int256(loanData.investorInterestWithdrawable);
int256 unreturnedInvestorPrincipal = int256(loanData.outstandingInvestorPrincipal) - int256(loanData.investorPrincipalWithdrawable);
uint256 factoredPrincipal = (uint256(unreturnedInvestorPrincipal) * _bucketFactor(loanData.status, loanData.nextDueDate)) / WAD_UNIT;
totalValue += factoredPrincipal + uint256(collectedCash);
```

and the discount depends on exactly two non-monetary fields:

```solidity
function _bucketFactor(LoanStatus status, uint48 nextDueDate) internal view returns (uint256) {
  if (status == LoanStatus.Active) { /* dpd buckets from block.timestamp vs nextDueDate */ }
  if (status == LoanStatus.ChargedOff) return discountFactors[ValuationBucket.ChargedOff];
  ...
}
```

So NAV moves discontinuously on two ordinary `Loans` operations:

**Downward — `Loans.updateLoanData`.** It writes `status` and `nextDueDate`, i.e. *both* inputs to
`_bucketFactor`, and nothing else in the system reacts:

```solidity
function updateLoanData(uint64 loanId, LoanStatus status, uint48 nextDueDate, uint48 maturityDate, uint48 timestamp)
  external whenNotPaused onlyServicerOrAdmin(loanId) loanExists(loanId) withLoanUpdate(loanId, timestamp)
```

Flipping a vault-held loan to `ChargedOff` collapses its factor to `discountFactors[ChargedOff]`
in a single transaction. `lastNav` does not move. Neither does `ownershipNonce` (the NFT never
transferred) nor `configurationVersion` (the calculator was not touched). `_requireFreshNav()` passes.

**Upward — `Loans.applyWaterfall` / `pay`.** Collected cash counts at par (factor 1.0) while
outstanding principal is discounted. Repayment therefore *raises* NAV mechanically: 1,000 outstanding
at a 0.95 factor is worth 950; after full repayment the same 1,000 sits in
`investorPrincipalWithdrawable` and is worth 1,000. A ~5% jump in that loan's contribution, again
with no invalidation.

## Impact

Both mispricings land on **shareholders who did nothing**, because both mint/burn formulas read the
cache directly:

```
approveDeposit:      shares = assets * totalSupply / lastNav       // stale-LOW  -> over-issues shares
approveRedemption:   assets = shares * lastNav / totalSupply       // stale-HIGH -> over-pays the exiting holder
```

- **Stale-low NAV** (a repayment/waterfall landed since the last refresh): the incoming depositor
  buys shares at a price that ignores value the vault already holds. Existing holders are diluted by
  the delta.
- **Stale-high NAV** (a charge-off landed since the last refresh): the exiting holder redeems at a
  price that ignores a loss the vault already took. The loss is transferred in full onto the holders
  who stayed.

The window is `maxNavAge` (~4h in the configuration read). Nothing about the exploit requires
front-running or precise block timing — it requires only that an approval land in the same
`maxNavAge` window as a ledger event, which is the ordinary operating cadence of this system, not an
edge case.

## Reachability — and the honest problem with it

`updateLoanData` and `applyWaterfall` are both **servicer-gated** (`onlyServicerOrAdmin`). Servicer
is trust assumption T-4. That is the crux this submission lives or dies on, so state it plainly
rather than hiding it:

**Argument for validity.** The contest brief's trust language for Borrower/Investor/Servicer carries
an explicit carve-out: *"if they can hurt other loans/users, this can be considered valid issue."*
Known issue #5 bounds servicer damage as "bounded per-loan (segregation holds)". This finding is
precisely the case where segregation **does not** hold: a servicer acting entirely within its
per-loan authority, on a loan it legitimately services, moves value between **unrelated vault
shareholders** who are not parties to that loan and have no relationship with that servicer. The
damage escapes the loan boundary — which is the exact condition the carve-out names. And the vault
side is not a documented tradeoff: `invariants.md` §6 asserts the loan ledger *does* invalidate NAV.
It does not.

**Argument against.** A judge may rule that (a) servicer is trusted and this is intended-permission,
or (b) `maxNavAge` *is* the designed mitigation and bounded staleness is accepted. Note that
`invariants.md` explicitly accepts **DPD time-drift** — the bucket factor silently decaying as
`block.timestamp` crosses a bucket boundary with no state change at all. A judge could extend that
acceptance to cover ledger-event drift.

The rebuttal to (b) is the one that matters: DPD drift and ledger drift are documented
*differently*. Time-drift is named as accepted; the loan ledger is named as **invalidating**. Those
are opposite claims about two mechanisms in the same paragraph, and only one of them is implemented.
That mismatch is the finding — not "NAV can be stale," which is admitted, but "the specific staleness
source the spec says is closed is open."

Note also that a servicer is not strictly required for the *upward* case: any borrower repayment
routed through the waterfall raises NAV, and borrower payment is permissionless. The servicer is
needed to apply the waterfall, but the value change originates outside any trusted role.

## Honest severity assessment

**Medium.** Not High, and arguing High will hurt credibility:

- It needs a trusted role for the clean version of the attack.
- The loss is bounded by `maxNavAge` and by the size of a single ledger event relative to total NAV.
- No funds leave the protocol; value is redistributed between shareholders.

What keeps it above Low: the redistribution is unbounded in *who* it hits (any shareholder), it is
reachable during normal operation with no special timing, and the property it breaks is one the team
wrote down as holding.

## Suggested fix

Give the ledger the same treatment the other five inputs already have — an *event* signal, not a
time bound:

1. Add a monotonic `ledgerNonce` to `Loans`, bumped in `_updateBalances` and in `updateLoanData`
   (i.e. on every write that can move either a monetary field or `status`/`nextDueDate`).
2. Snapshot it alongside `lastOwnershipNonce` when NAV is computed, and add
   `require(loans.ledgerNonce() == lastLedgerNonce, LoanLedgerChanged())` to `_requireFreshNav()`.

A global nonce will invalidate on ledger activity for loans the vault does not hold, which is
conservative but cheap; a per-vault-portfolio nonce is the tighter version if the extra bookkeeping
is acceptable. Either way the guard becomes structural instead of "remember to call
`_invalidateNav()`" — which is the maintenance hazard `invariants.md` §6 itself warns about.

## PoC

`PoC.t.sol` in this directory. **It has not been executed** — the repo clone was lost with the
container and could not be restored in this session, so the file is a drop-in test written against
the interfaces as read, not a passing run. Treat it as a specification of the reproduction, and run
it in a local clone before submitting:

```
cp PoC.t.sol <clone>/test/NavStaleness.t.sol
forge test --match-contract NavStalenessLoanLedger -vvv
```

Sequence it encodes:

1. Deploy `Loans` + `LoansNFT` + `PortfolioVault` + `NavCalculator`; originate and fund a loan whose
   NFT is held by the vault; add it to the curated NAV list.
2. Refresh NAV. Record `lastNav`.
3. Alice requests a redemption of her full share balance.
4. Servicer calls `updateLoanData(loanId, ChargedOff, ...)`. The loan's true value collapses.
5. Assert `_requireFreshNav()` still passes — `ownershipNonce` unchanged, `configurationVersion`
   unchanged, `lastNavUpdate` inside `maxNavAge`.
6. Operator calls `approveRedemption` for Alice. She is paid at the pre-charge-off NAV.
7. Refresh NAV. Assert the per-share value for the remaining holder is now strictly lower than it
   would have been had the refresh happened before step 6 — the charge-off loss landed entirely on
   the holder who stayed.

Step 5 is the assertion that carries the finding; steps 6–7 quantify it.

## Verification checklist (do this before submitting)

- [ ] `PortfolioVault._requireFreshNav` — confirm the five `require`s are exactly as quoted and that
      **no sixth check** references `Loans` state.
- [ ] `grep -n "_invalidateNav" contracts/PortfolioVault.sol` — confirm every call site is a
      vault-initiated mutation, and that none is reachable from a `Loans` state change.
- [ ] `grep -rn "PortfolioVault\|vault\|nav" contracts/Loans.sol contracts/LoansLedger.sol` —
      confirm `Loans` has no callback, hook, nonce, or event the vault consumes. **If this grep hits,
      the finding is dead; check it first.**
- [ ] `NavCalculator._bucketFactor` — confirm `status` and `nextDueDate` are its only non-monetary
      inputs, and `Loans.updateLoanData` writes both.
- [ ] `SECURITY.md` — confirm no entry among the 31 covers vault mispricing from loan-ledger changes.
- [ ] Read the actual `maxNavAge` default/deployment value; the ~4h figure above is from the version
      read in-session and should be quoted from the contest commit, not from this document.
