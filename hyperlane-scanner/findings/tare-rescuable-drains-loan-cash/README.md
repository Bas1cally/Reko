# Tare: `Rescuable.rescueERC20Tokens` has no exclusion for the operating currency, breaking Loans' custody invariant for every open loan

**Target**: Sherlock contest `tare-io` (`sherlock-scoping/tare-io__tare-contracts`), scope 2,542 nSLOC,
total rewards 50,000 USDC. Contest window: **20 Jul 2026 17:00 → 29 Jul 2026 17:00 UTC**.
**File**: `contracts/misc/Rescuable.sol` → `rescueERC20Tokens`, as inherited (unmodified) by `contracts/Loans.sol`.
**Status**: root cause fully verified against pasted source. PoC pending one more file
(`GuardianAccessControl.sol`) to pin down the exact role-grant mechanics; narrative and impact
analysis below do not depend on it.

---

## Summary

`Rescuable` is documented as a guardian-only recovery path for **tokens accidentally sent to the
contract**:

```solidity
/**
 * @title Rescuable
 * @notice Allows a guardian to rescue ERC20 and ERC721 tokens accidentally sent to the contract.
 */
```

The implementation does not enforce that intent — `rescueERC20Tokens` takes an arbitrary `token`
address with no exclusion list:

```solidity
function rescueERC20Tokens(
  address token,
  uint256 amount
) external whenNotPaused onlyRole(GUARDIAN_ROLE) returns (uint256 rescued) {
  require(recoveryAddress != address(0), RecoveryAddressNotSet());
  uint256 balance = IERC20(token).balanceOf(address(this));
  rescued = amount >= balance ? balance : amount;
  if (rescued > 0) {
    IERC20(token).safeTransfer(recoveryAddress, rescued);
    emit ERC20TokensRescued(token, rescued, recoveryAddress);
  }
}
```

`Loans` inherits `Rescuable` with no override:

```solidity
contract Loans is LoansLedger, Rescuable, ReentrancyGuardTransient { ... }
```

`Loans` is the one contract in this codebase that legitimately, continuously custodies real USDC —
principal awaiting disbursement, borrower payments awaiting waterfall allocation, interest/fees
awaiting withdrawal by investors/servicers/originators, all for potentially many concurrently open
loans. Calling `rescueERC20Tokens(address(USDC), type(uint256).max)` sweeps the entire operating
balance to `recoveryAddress`, for **every loan at once**, in a single call.

## Why this breaks the protocol, not just moves money

`LoansLedger` maintains a per-loan `ACC_CASH` ledger account that is meant to mirror the contract's
real token balance 1:1. Every legitimate path that changes real custody also changes the matching
loan's `ACC_CASH` entry by the exact same amount, gated by an explicit solvency check:

```solidity
// _updateBalances, LoansLedger.sol
if (from == ACC_CASH) {
  require(fromBalance >= amount, InsufficientCashBalance());
}
```

`rescueERC20Tokens` moves real tokens through neither `_deposit` nor `_withdraw` — it calls
`IERC20(token).safeTransfer` directly, bypassing the ledger entirely. After a rescue call on
`currency`:

- Every loan's `ACC_CASH` ledger balance is **unchanged** — the ledger still asserts the money is
  there.
- The contract's actual token balance is **reduced or zero**.
- Every subsequent legitimate withdrawal on every affected loan
  (`investorWithdraw`, `servicerWithdraw`, `originatorWithdraw`, `disburse`, `refundBorrower`, the
  disbursement leg of `create`→`fund`→`disburse`) attempts a real `safeTransfer`/`safeTransferFrom`
  that the contract can no longer back, and **reverts** — not because of any ledger check, but
  because the ERC20 itself has insufficient balance.

The result is simultaneous, protocol-wide impact matching two of the categories the program
explicitly asked for:

- **"Funds loss: stolen or being stuck"** — the swept amount is gone; whatever wasn't swept becomes
  unreachable because withdrawal calls now revert against a ledger that no longer matches reality.
- **"Going into a state that is unrecoverable (bricking)"** — there is no repair path in the
  contract. The ledger can't be manually corrected (no admin function rewinds `ACC_CASH`), and even
  a benevolent guardian sending money back in via a normal ERC20 transfer would land as an
  unaccounted, un-ledgered balance rather than restoring any specific loan's entry.

## Why the other `Rescuable` inheritors are not affected

The same base contract is inherited by `LoansExchange`, `TrustedSpender`, `TrustedCalls`, and (per
the interface list) likely `SmartAccountFactory`-adjacent contracts. None of those legitimately
hold the operating currency at rest:

- `LoansExchange.acceptOffer` settles `CURRENCY.safeTransferFrom(msg.sender, seller, price)`
  **directly buyer→seller** — the Exchange's own balance is never the custodian.
- `TrustedSpender.executeTransfer` moves tokens **from a Safe to a pre-approved recipient**; it
  never holds a balance itself.
- `TrustedCalls` doesn't touch ERC20 balances at all.

For those contracts, "any ERC20 sitting in this contract's balance is accidental" is actually true,
and the unmodified `Rescuable` behavior is correct. **`Loans` is the one place where the documented
assumption behind `Rescuable` is false**, and it's the one place that got no override to say so.

## Reachability

Requires `GUARDIAN_ROLE`. Per the contest's own trust-model brief, Guardian is listed as "fully
trusted" without the explicit "but if it hurts other users, still valid" carve-out that's attached
to Borrower/Investor/Servicer. This is the honest tension in this submission:

- **Argument for validity despite the trust level**: the contract's own NatSpec states the intended
  scope ("accidentally sent"). The code does not implement that scope — it is strictly broader than
  documented. This is the standard "rescue/sweep function forgets to exclude the protocol's own
  token" pattern, which routinely gets flagged as a real (Medium/High, sometimes Critical-adjacent
  given blast radius) finding in Sherlock/Immunefi audits *because* the resulting damage
  (protocol-wide, simultaneous, unrecoverable insolvency across every open loan) is categorically
  different from what a "trusted role doing its intended job" should be capable of — this looks like
  an implementation gap relative to stated intent, not a deliberate power grant.
- **Argument against**: Guardian is unconditionally trusted per the brief; Sherlock's judge may rule
  this an intended-permission exclusion regardless of the doc-comment mismatch.

Given the ambiguity, frame the submission around the NatSpec-vs-code mismatch and the
disproportionate, protocol-wide blast radius — that's the strongest version of the argument, and
it's honest about being the crux the judge will weigh.

## Suggested fix

```solidity
function rescueERC20Tokens(address token, uint256 amount) external whenNotPaused onlyRole(GUARDIAN_ROLE) returns (uint256 rescued) {
    require(token != address(currency), CannotRescueOperatingCurrency()); // add in Loans, or make token exclusion a virtual hook in Rescuable
    ...
}
```

Since `Rescuable` is a shared base with no knowledge of `currency`, the cleanest fix is a virtual
`_isRescuable(address token)` hook that `Rescuable` calls before transferring, overridden in `Loans`
to return `false` for `address(currency)`.

## Reproduction (PoC — pending one input)

Plan: deploy `Loans` with a mock ERC20, `initialGuardian`, `initialRecoveryAddress`; originate,
fund, and disburse a loan so `Loans` legitimately custodies real tokens with a matching `ACC_CASH`
ledger entry; have the guardian call `rescueERC20Tokens(address(mockUSDC), type(uint256).max)`;
assert the contract's token balance drops while the loan's `ACC_CASH` ledger balance is unchanged;
assert a subsequent legitimate `investorWithdraw`/`servicerWithdraw` on that loan reverts.

Blocked on: exact role-grant mechanics in `GuardianAccessControl.sol` (is `GUARDIAN_ROLE` granted
via `_initGuardian` alone, or via a separate `grantRole` call; is `hasRole` standard OZ
`AccessControl`). Everything else needed for the test (constructors, `Roles` enum, ledger account
IDs) is already in hand from the pasted files.

## Not yet reviewed in this contest

`PortfolioVault.sol` (601 nSLOC), `NavCalculator.sol` (94), `VaultShareToken.sol` (91),
`LoansAuth`'s interaction with the vault's approval flow, and `specs/invariants.md` /
`SECURITY.md` (not yet supplied — should be checked before submission in case this is a documented
known issue). Given the 2-day contest window, this finding was prioritized to closure over opening
a new front.
