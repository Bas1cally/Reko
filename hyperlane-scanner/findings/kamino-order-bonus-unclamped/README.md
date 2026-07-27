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

## Proof — measured against the real production function

`poc_test.rs` builds a **legitimate** order (`validate_order` accepts it,
asserted in the test), evaluates the condition exactly as
`ConditionType::LiquidationLtvCloserThan` does, and calls the real
`calculate_order_execution_bonus_rate` — including its `diff_to_bad_debt` cap.

```
cargo test -p kamino_lending --lib poc_unclamped_bonus -- --nocapture
```

```
configured max bonus      = 0.0999999999999999995
sanity limit              = 0.1
normalized distance       = 6.000000000000004336
EFFECTIVE bonus rate      = 0.25
collateral multiplier     = 1.25 (vs 1.0999999999999999995 if capped correctly)

bonus at trigger LTV 70%  = 0.100000000000000441
peak bonus  = 0.280000000000000001 at LTV 72%
configured/validated cap  = 0.0999999999999999995

test order_execution_bonus_exceeds_its_own_validated_maximum ... ok
test executor_can_wait_for_a_bonus_far_above_the_cap ... ok
```

Order used: `LiquidationLtvCloserThan`, 1-point buffer, bonus range
[0%, 10%] — the maximum the protocol permits. Reserve liquidates at 70% LTV.

**At 75% LTV the executor receives 25% instead of the validated 10%**; the
collateral multiplier applied to the seized amount is `1.25` rather than `1.10`.

The protocol's own log line confirms it is capping against the wrong bound —
at 90% LTV it prints a theoretic bonus of `2.10` (210%) reduced only to
`1 - ltv`:

```
At user_no_bf_ltv = 0.9, the calculated order execution bonus 2.100000000000000387 is capped at 0.1
```

### Correction: the bonus is not monotonic in LTV

An earlier draft of this report claimed the bonus rises monotonically with LTV,
so an executor could wait indefinitely. **The test disproves that** and the
claim has been removed. The interpolation grows with LTV while the
`1 - no_bf_ltv` cap shrinks, so the curve has an interior maximum:

| LTV | effective bonus |
|---|---|
| 70% (trigger) | 10.0% — correctly capped |
| **72%** | **28.0% — peak** |
| 74% | 26.0% |
| 80% | 20.0% |
| 90% | 10.0% |

The incentive distortion is therefore real but bounded: an executor maximises
their take by waiting for roughly a 2-point LTV overshoot, yielding **2.8× the
validated cap** — not by waiting indefinitely.

## Impact

The borrower loses collateral in excess of the maximum the protocol validated
and displayed when the order was created. The excess is bounded by
`1 − no_bf_ltv` but, as shown, can be several times the configured cap.

Two things make this more than a rounding concern:

1. **No misconfiguration is required.** A perfectly reasonable order
   (tight buffer, bonus range within the 10% limit) plus ordinary market
   movement is sufficient. The user is given an explicit guarantee at set time
   that execution does not honour.
2. **The executor controls the timing, and delay pays — up to a point.**
   Executing at the trigger yields the correct 10%; waiting for a ~2-point LTV
   overshoot yields 28% (measured). That inverts the intended incentive to
   deleverage early, though the gain is bounded by the `1 - ltv` cap rather
   than unbounded.

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
- **Confirm the feature flag on the deployed markets — this decides the
  severity and I could not check it.** Every Solana RPC endpoint is blocked by
  this environment's egress policy (`403` on CONNECT from the gateway to
  `api.mainnet-beta.solana.com`, `solana-rpc.publicnode.com`, `solana.drpc.org`,
  `rpc.ankr.com`), so the on-chain read was not possible here. Run it yourself:

  ```bash
  # main Kamino lending market; repeat for any other market in use
  solana account <LENDING_MARKET_PUBKEY> --url mainnet-beta --output json
  ```

  and decode `obligation_order_execution_enabled` (a `u8` in `LendingMarket`).
  If it is `0`, `check_obligation_order_execution` returns `None` and this is
  latent rather than live — still a valid report, but not funds-at-risk.
  If it is `1`, the path is live.

- The proof covers the **bonus computation** end to end through the real
  production function, not a full liquidation transaction on a validator. The
  remaining step — that `liquidation_bonus_rate` becomes
  `bonus_multiplier = rate + 1` and scales the seized collateral — is a direct
  read of `calculate_liquidation_amounts` (`liquidation_operations.rs`) with no
  further clamp, but it is not exercised by this test.
