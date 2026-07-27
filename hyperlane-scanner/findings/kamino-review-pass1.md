# Kamino — first review pass (in scope, $1.5M)

**Target**: `Kamino-Finance/{klend,kvault,scope,kfarms}` — all four whole repos
are `smart_contract` assets on the Immunefi program, alongside the deployed
program IDs. No "demonstrably unused" exclusion.
**Surface**: ~62k lines of non-test Rust (klend 35k, scope 13k, kvault 10k, kfarms 5k).
**Result of this pass**: no fund-loss bug found in the areas checked below.

## Checked and sound

### klend — flash loans (`lending_market/flash_ixs.rs`)

The classic Solana flash-loan attack is defeating the borrow↔repay
introspection. This implementation is hardened on every axis I tested:

| Guard | Present |
|---|---|
| CPI forbidden (borrow and repay) | ✅ double-checked: `crate::ID != current_ixn.program_id` **and** `get_stack_height() > TRANSACTION_LEVEL_STACK_HEIGHT` |
| Borrow requires a matching repay later in the tx | ✅ forward scan, errors with `NoFlashRepayFound` |
| Multiple borrows in one tx | ✅ rejected |
| Multiple repays | ✅ rejected |
| Amount match borrow↔repay | ✅ checked from both directions |
| `borrow_instruction_index` points back correctly | ✅ checked |
| Reserve identity | ✅ `ixn.accounts[3].pubkey == ctx.accounts.reserve.key()` |
| **All accounts identical between borrow and repay** | ✅ length + pairwise pubkey comparison |

The pairwise account comparison is the strongest part: the repay cannot be
redirected to different vaults or a different user.

*Minor, not exploitable:* the scan does `ixn.data[..8]` without a length guard,
so a klend instruction carrying <8 bytes of data placed after the borrow would
panic the loop. That only aborts the attacker's own transaction.

### kvault — share math (`operations/vault_operations.rs`)

Tested the vault-inflation / first-depositor class:

- `get_shares_to_mint` returns `user_token_amount` 1:1 when `shares_issued == 0`,
  and errors `VaultAUMZero` if shares exist but AUM is zero (no div-by-zero).
- Rounding directions both favour the vault: AUM denominator via
  `.to_ceil::<u64>()`, minted shares via `.to_floor()`.
- **The inflation attack yields a revert, not a loss:** `shares_to_mint == 0`
  → `DepositAmountsZeroShares`. A donation-inflated AUM makes the victim's
  deposit fail rather than mint them zero shares.
- Two further backstops: `vault.min_deposit_amount` and the caller-supplied
  `min_shares_out` (`require_gte!`).
- `compute_amount_to_deposit_from_shares_to_mint` uses
  `full_mul_int_ratio_ceil(...).to_ceil()` — double ceiling, so the depositor
  always pays at least fair value for the shares actually minted.

## Not yet covered — where the remaining surface is

klend is 35k lines; this pass touched one subsystem. Untouched and, in
descending order of where a fund-loss bug would plausibly still live:

1. **Liquidation** — `handler_liquidate_obligation_and_redeem_reserve_collateral`,
   plus `handler_socialize_loss` and `handler_mark_obligation_for_deleveraging`.
   Health-factor math, liquidation bonus, and bad-debt socialisation.
2. **The newer "order" feature set** — `handler_set_obligation_order`,
   `handler_set_borrow_order`, `handler_fill_borrow_order`,
   `handler_rollover_fixed_term_borrow`. Newest code in the repo, which is the
   profile that produced the one real defect found earlier in this engagement.
3. **Combined-operation handlers** — `handler_deposit_and_withdraw`,
   `handler_repay_and_withdraw_redeem`. Composite instructions are where a
   refresh or health check gets skipped between the two halves.
4. **`scope`** (13k lines) — the oracle. Staleness, confidence intervals, and
   the twap paths feed every valuation in klend and kvault.
5. **kvault `invest` / `withdraw` / `redeem_in_kind`** — movement of funds
   between vault and reserves.

## Assessment

Kamino is a mature protocol with multiple audits behind it, and it shows: the
flash-loan introspection and the vault share math are both defended past the
standard attack playbook, including the second-order cases.

A payable bug here, if one exists, is unlikely to be a missing check. The
realistic candidates are the newest handlers (item 2) and cross-subsystem
interactions — oracle staleness feeding a liquidation, or a composite handler
that skips a refresh — rather than any single function read in isolation.
