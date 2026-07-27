# Kamino klend — pass 2: the newest code in the repo

**Target**: `Kamino-Finance/klend` (Immunefi `kamino`, max $1,500,000 — whole
repo is an in-scope `smart_contract` asset).
**Method**: reachability-first (see `METHOD-NOTE.md`), plus target selection by
**recency** rather than by reading the repo top-to-bottom.
**Result of this pass**: **no exploitable fund-loss bug found.** One latent
overflow panic and one design-level DoS lever noted below; neither is payable.

---

## How the targets were chosen

Deepened the shallow clone to 120 commits and dated every handler:

| Feature | Handlers | First release | Lines |
|---|---|---|---|
| **Withdrawal queue** | `enqueue_to_withdraw`, `withdraw_queued_liquidity`, `cancel_withdraw_ticket` | **1.22.0** (2nd-newest release) | 851 |
| Invalid-ticket recovery | `recover_invalid_ticket_collateral` | 1.17.0 | 144 |
| Borrow orders / fixed term | `set_borrow_order`, `fill_borrow_order`, `rollover_fixed_term_borrow` | 1.16.0–1.18.0 | 617 |
| Composite handlers | `deposit_and_withdraw`, `repay_and_withdraw_redeem` | older | 461 |

The withdrawal queue is the newest funds-moving code in the repository, and
two of the three new order handlers are **permissionless** (`payer: Signer`,
no `has_one = owner` on the obligation) — a third party acts on someone else's
position. That is the highest-value combination available here.

## Checked and sound

### Withdrawal queue (release 1.22.0)

| Attack | Why it fails |
|---|---|
| Redeem a ticket out of order | The ticket PDA seed is `next_withdrawable_ticket_sequence_number` — only the queue head can be loaded |
| Redeem someone else's ticket to your own account | `user_destination_liquidity` is pinned by `address = ticket.user_destination_liquidity_ta`, and `owner_queued_collateral_vault` is a PDA seeded on `ticket.owner` |
| Double-redeem | `queued_collateral_amount` is decremented in-place and the ticket is closed at zero; a partially-redeemed ticket stays head with a reduced balance |
| Burn more collateral than the ticket holds | `collateral_amount_to_burn = min(ticket_amount, max_redeemable)`, then `post_transfer_owner_queued_collateral_vault_balance_checks` asserts vault delta == burn == queue delta |
| Cancel-then-brick the queue | `cancel_withdraw_ticket` calls `dequeue(amount, false)` and never closes the account; the redeem handler has an explicit branch that steps over a zero-amount ticket and closes it |
| Drain the ticket's lamports via the ATA-rent path | Prepayment is `minimum_balance(MAX_TOKEN_ACCOUNT_DATA_LEN)`; the refund is `minimum_balance(actual_ata_len)` ≤ prepayment. `require_closing_ticket` then forces full redemption, so the branch cannot repeat |
| Take liquidity earmarked for the queue | Regular withdraw/borrow use `freely_available_liquidity_amount()` = total − queued. Only `FOR_WITHDRAW_QUEUED_LIQUIDITY`, the liquidation paths, and flash loans (same-tx repay) pass `use_withdraw_queue = true` |

The kvault progress callback (`ProgressCallbackType::KlendQueueAccountingHandlerOnKvault`)
is gated at enqueue by requiring the signer to be `pda::kvault::base_authority(vault)`,
so only kvault can create such a ticket, and at redemption the callback program
and its two custom accounts are pinned by `address =` constraints against the
ticket. **The kvault side of this CPI could not be reviewed** — the public
`Kamino-Finance/kvault` repo is at 2.2.2 and contains no
`update_klend_queue_accounting` handler, i.e. the counterpart is unpublished.
That is the one unexamined half of this feature.

### Permissionless order handlers

`fill_borrow_order` builds a `BorrowObligationLiquidity` in Rust with
`owner = payer`, which deliberately bypasses that struct's `has_one = owner`
(Anchor constraints only run at deserialisation). Anyone can push debt onto
someone else's obligation. The bounds that make it safe:

- Proceeds go to `order.filled_debt_destination`, which is additionally
  constrained `token::authority = obligation.owner` — the filler cannot
  redirect the funds.
- Reserve choice is bounded by `debt_liquidity_mint`, `max_borrow_rate_bps`,
  `min_debt_term_seconds`, and the reserve's debt-maturity timestamp.
- Amount is not filler-controlled: `BorrowSize::AtMost(remaining)` resolves to
  `calculate_borrow_exact(remaining)`, so `receive_amount == remaining` exactly.
- `accounts.owner` is never read inside `borrow_obligation_liquidity_process_impl`,
  so nothing else silently authorises off it.

`rollover_fixed_term_borrow` is also permissionless, and the target reserve is
attacker-chosen. The two ways that would have paid are both closed:

- **Borrow-factor swap** (roll the victim into a reserve with a higher borrow
  factor so their LTV jumps and they become liquidatable):
  `check_rollover_possible` requires
  `target.config.borrow_factor_pct == source.config.borrow_factor_pct`.
- **Rate/term degradation**: `resolve_rollover_mode` requires the owner's
  `auto_rollover_enabled`, and checks the target's max borrow rate and debt
  term against the owner's configured bounds.

One asymmetry worth noting but not a bug: when the target reserve is
**open-term**, `resolve_rollover_from_fixed_term_mode` returns early and the
`max_borrow_rate_bps` comparison is skipped — only the owner's
`open_term_allowed` flag gates it. A fixed-term reserve's rate is a constant so
the comparison is meaningful; an open-term reserve's is not, so this reads as
deliberate. The owner still has to opt in.

I also chased `target_borrow.borrowed_amount_at_expiration = 0` (rollover
clears the snapshot that throttles term-expiry liquidations). Zeroing it looks
like it destroys the borrower's throttle protection, but
`capture_borrowed_amount_at_expiration` re-snapshots on the next
`refresh_obligation` — and a liquidation requires a fresh obligation, so the
attacker must run that refresh. The re-captured value is *larger* (accrued
interest), so the protection comes back stronger, not weaker.

### Composite handlers

`deposit_and_withdraw` and `repay_and_withdraw_redeem` both read `initial_ltv`
from the obligation before acting and enforce `new_ltv <= initial_ltv` and
`new_ltv < unhealthy_ltv` afterwards. The attack would be to inflate
`initial_ltv` so the "don't make it worse" guard goes slack, letting a user
lever up past `max_ltv` to just under the liquidation threshold. It fails:

- Both paths reach a `is_stale(slot, PriceStatusFlags::NONE)` assertion
  (`deposit_obligation_collateral` / `check_repay_possible`), so the obligation
  must have been refreshed **in the current slot** — prices are constant within
  a slot, so the pre-read value is the real one.
- The refresh itself cannot be fed a doctored account set:
  `handler_refresh_obligation` pins `remaining_accounts.len()` to
  `deposits + borrows (+ borrows again if referred)`, and
  `check_obligation_collateral_deposit_reserve` compares each supplied reserve
  pubkey against `deposit.deposit_reserve` positionally.

Same for `update_elevation_group_debt_trackers_on_borrow`, which is fed an
attacker-supplied `deposit_reserves_iter`: it `require_keys_eq!`s each entry
against the obligation's own deposits.

## Noted, not payable

**1. `fraction_collateral_to_liquidity` panics on overflow, on a path every
refresh takes.**

The head commit (`c060019`, "saturating fraction collateral to liquidity")
*adds* `checked_…` and `saturating_…` variants — and wires up neither. All four
call sites still use the panicking version, including
`calculate_obligation_collateral_market_value`, which
`refresh_obligation_deposits` runs for every deposit:

```rust
pub fn fraction_collateral_to_liquidity(&self, collateral_amount: Fraction) -> Fraction {
    self.checked_fraction_collateral_to_liquidity(collateral_amount)
        .expect("fraction_collateral_to_liquidity: liquidity_amount overflow")
}
```

An obligation whose `deposited_amount × exchange_rate` exceeds `Fraction`'s
range (u128 with 60 fractional bits, so ≈2⁶⁸) can never be refreshed again —
which means it can never be withdrawn from *or liquidated*. That is the
bad-debt shape, not just a griefing shape. But reaching it needs roughly
`deposited_amount ≈ u64::MAX` with an exchange rate ≈16, i.e. a reserve whose
cToken supply collapsed relative to its liquidity, and klend's
`seed_deposit_on_init_reserve` exists to prevent exactly that. **Not
demonstrated reachable, so not written up as a finding** — but the fact that
Kamino wrote the saturating helper suggests they hit this internally, and the
mitigation is not yet applied in the published tree.

**2. The queue is a free lever to freeze a reserve's liquidity.**

`enqueue_to_withdraw` moves the depositor's cTokens into a vault and adds them
to `queued_collateral_amount`, which is subtracted from
`freely_available_liquidity_amount()` — so it blocks *other people's* borrows
and withdrawals, while the queuer keeps earning and can cancel at any time.
Queue-jumping is the point of the feature, so this is design, not defect; it is
worth flagging only because the lever is free (no fee, no lockup, instant
cancel) and there is no cap on a single ticket's share of a reserve.

## Assessment

Two passes over klend now. The consistent picture: the invariants that matter
are asserted twice — once in the operation and once in a `post_*_checks`
function that re-reads the token account balances and compares deltas. Account
substitution is closed by PDA seeds and `address =` constraints on every
account that can receive value. The permissionless handlers are permissionless
*on purpose*, and each one binds the destination to the position's owner.

Where a bug would still plausibly live, in order:

1. **The kvault side of the queue CPI** — unpublished, so unreviewable here.
   This is the only genuine blind spot in the feature.
2. `kfarms` (5k lines, untouched in both passes) and the klend↔kfarms
   `refresh_farms!` interaction.
3. `handler_socialize_loss` and the bad-debt accounting.
4. kvault `invest` / `redeem_in_kind`.
