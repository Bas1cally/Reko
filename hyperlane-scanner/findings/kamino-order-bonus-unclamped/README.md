# Kamino klend: obligation-order execution bonus is not clamped to its configured maximum — borrower over-liquidated

**Target**: `Kamino-Finance/klend` (Immunefi `kamino`, max $1,500,000 — the repo
is an in-scope `smart_contract` asset, as are the deployed program IDs)
**Files**:
- `programs/klend/src/state/obligation_order_operations.rs` → `evaluate_stop_loss`
- `programs/klend/src/state/liquidation_operations.rs` → `interpolate_bonus_rate`, `calculate_order_execution_bonus_rate`

**Status**: **Verified by a unit test compiled and run against the real klend
types** (`poc_test.rs`, passes). Not yet reproduced end-to-end on a validator.

---

## Summary

An obligation order (stop-loss / take-profit) lets any third party deleverage
a borrower's position and take an *execution bonus* — extra collateral, paid by
the borrower.

At set time the protocol validates that the bonus can never exceed 10%:

```rust
const EXECUTION_BONUS_SANITY_LIMIT: Fraction = fraction!(0.1);
...
if execution_bonus_rate_range.end() > &EXECUTION_BONUS_SANITY_LIMIT {
    msg!("Maximum execution bonus {} higher than sanity limit {}", ...);
    return err!(LendingError::InvalidOrderConfiguration);
}
```

**At execution time that bound is not enforced.** The bonus is interpolated
using a "normalized distance from threshold" that is never clamped to 1, so
once the position's LTV moves past the liquidation threshold the interpolation
runs past the end of the configured range.

The only cap applied afterwards is `1 - no_bf_ltv`, not the configured maximum.
The borrower therefore loses materially more collateral than the protocol
validated as possible.

## Root cause — two missing clamps

**1. The distance is unbounded above** (`obligation_order_operations.rs`):

```rust
fn evaluate_stop_loss(current_value, condition_threshold, liquidation_threshold)
    -> Option<ConditionHit>
{
    if current_value <= condition_threshold { return None; }
    let normalized_distance_towards_liquidation = if condition_threshold >= liquidation_threshold {
        Fraction::ONE
    } else {
        let current_distance = current_value - condition_threshold;
        let maximum_distance = liquidation_threshold - condition_threshold;
        current_distance / maximum_distance          // ← no .min(ONE)
    };
    Some(ConditionHit::with_distance(normalized_distance_towards_liquidation))
}
```

`current_value > liquidation_threshold` ⇒ ratio > 1. That is simply a position
that has drifted past its liquidation LTV before anyone acted on it — the
normal state of a position during a price gap.

**2. The interpolation is not clamped to the range end**
(`liquidation_operations.rs`):

```rust
fn interpolate_bonus_rate(normalized_distance_from_threshold, bonus_rate_range) -> Fraction {
    bonus_rate_range.start()
        + normalized_distance_from_threshold * (bonus_rate_range.end() - bonus_rate_range.start())
}
```

With distance > 1 this returns more than `bonus_rate_range.end()`.

**3. The only post-cap omits the configured maximum:**

```rust
pub(crate) fn calculate_order_execution_bonus_rate(order, condition_hit, user_no_bf_ltv) -> Fraction {
    let theoretic_bonus_rate = ...interpolate_bonus_rate(...);
    let diff_to_bad_debt = Fraction::ONE.saturating_sub(user_no_bf_ltv);
    if theoretic_bonus_rate > diff_to_bad_debt { diff_to_bad_debt } else { theoretic_bonus_rate }
}
```

### The adjacent function shows the intended pattern

`calculate_autodeleverage_bonus_rate`, directly above in the same file, caps at
**both** bounds:

```rust
let effective_max_bonus_rate = min(configured_max_bonus_rate, diff_to_bad_debt);
if liquidation_bonus_rate > effective_max_bonus_rate { effective_max_bonus_rate } else { ... }
```

The order-execution sibling is missing the `configured_max_bonus_rate` half.
This is an internal inconsistency, not a design decision.

## Proof

`poc_test.rs` — appended to `obligation_order_operations.rs` and run with
`cargo test -p kamino_lending --lib poc_unclamped_bonus -- --nocapture`:

```
normalized_distance_from_threshold = 6.000000000000004336
interpolated bonus rate = 0.600000000000000466  (order max = 0.10, sanity limit = 0.10)
test ... ok
```

Scenario: `LiquidationLtvCloserThan` with a 1-point buffer on a reserve whose
unhealthy LTV is 0.70, after the LTV gaps to 0.75.

- condition threshold `t = 0.70 − 0.01 = 0.69`
- distance `= (0.75 − 0.69) / (0.70 − 0.69) = 6`
- bonus `= 0% + 6 × (10% − 0%) = 60%` — **6× the validated maximum**
- capped only by `1 − no_bf_ltv`; at `no_bf_ltv = 0.75` that is **25%**

**Effective bonus: 25% where the protocol validated a 10% ceiling.**

Further parameter points, same arithmetic:

| Order | unhealthy LTV | LTV | distance | theoretic | effective | vs 10% cap |
|---|---|---|---|---|---|---|
| `LiqLtvCloserThan` buf 0.01, bonus [0%, 10%] | 0.70 | 0.75 | 6.0 | 60% | 25% | 2.5× |
| same, with borrow factor (`no_bf_ltv` 0.68) | 0.70 | 0.75 | 6.0 | 60% | 32% | 3.2× |
| `LiqLtvCloserThan` buf 0.02, bonus [1%, 5%] | 0.80 | 0.86 | 4.0 | 17% | 14% | 1.4× |
| `UserLtvAbove` t 0.75, bonus [1%, 5%] | 0.80 | 0.88 | 2.6 | 11.4% | 11.4% | 1.14× |

The overshoot grows as the gap between the order threshold and the liquidation
threshold narrows — and configuring a *tight* buffer is the rational use of
`LiquidationLtvCloserThan`, whose entire purpose is "deleverage me just before
I would be liquidated".

## Impact

The borrower loses collateral in excess of the maximum the protocol validated
and displayed when the order was created. The excess is bounded by
`1 − no_bf_ltv` but, as shown, can be several times the configured cap.

Two things make this more than a rounding concern:

1. **No misconfiguration is required.** A perfectly reasonable order
   (tight buffer, bonus range within the 10% limit) plus ordinary market
   movement is sufficient. The user is given an explicit guarantee at set time
   that execution does not honour.
2. **The executor controls the timing, and delay pays.** The bonus rises
   monotonically with LTV past the threshold, so an executor is incentivised
   *not* to execute promptly and instead let the position deteriorate before
   taking a super-sized bonus. That inverts the intended incentive, which is to
   deleverage early.

## Suggested fix

Clamp in both places — either is sufficient, both is better:

```rust
// obligation_order_operations.rs — evaluate_stop_loss
let normalized = (current_distance / maximum_distance).min(Fraction::ONE);
```

```rust
// liquidation_operations.rs — calculate_order_execution_bonus_rate
// mirror the sibling autodeleverage function
let configured_max = *order.execution_bonus_rate_range().end();
let effective_max = min(configured_max, diff_to_bad_debt);
if theoretic_bonus_rate > effective_max { effective_max } else { theoretic_bonus_rate }
```

There is currently **no test** covering `interpolate_bonus_rate` or
`evaluate_stop_loss` with a distance above 1; a regression test at
distance > 1 should accompany the fix.

## Reproduction

```bash
git clone https://github.com/Kamino-Finance/klend && cd klend
# append poc_test.rs to programs/klend/src/state/obligation_order_operations.rs
cargo test -p kamino_lending --lib poc_unclamped_bonus -- --nocapture
```

## Before submitting

- Re-pin to an exact commit (the clone used here was shallow).
- Confirm `is_obligation_order_execution_enabled()` is true on the deployed
  lending markets — `check_obligation_order_execution` returns `None` when the
  feature flag is off, which would make this latent rather than live. This
  materially affects severity and a triager will check it.
- The end-to-end demonstration (an actual over-sized collateral seizure on a
  local validator) is not built here; the unit test proves the bonus
  computation, not the full liquidation transaction.
