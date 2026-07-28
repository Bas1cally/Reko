# Vesu v2: the interest-rate ramp is path-dependent on poke frequency, and anyone can poke for free

**Target**: `vesuxyz/vesu-v2` @ `e14d772` — `src/interest_rate_model.cairo`, `src/pool.cairo`,
`src/common.cairo`. Read from a fresh public clone, not from memory or a mirror.
**Programme**: Sherlock bug bounty, live 27 Jul 2026, max 50,000 USDC, 250 USDC submission deposit.
**Status**: mechanism **confirmed end to end against source and quantified**. Severity mapping is the
open question — see the honest assessment at the bottom. Not yet submitted.

## How this was found

Applying the lesson the Tare contest produced: the team documents *correctness* exhaustively and
*liveness / path-dependence* barely, so hunt for **monotonic state that gates everything with no
reset**. That led to the `18 × SCALE` accumulator ceiling (section 3), and following the growth path
backwards from it produced the actual defect (sections 1–2).

## 1. The defect

`full_utilization_rate` in `src/interest_rate_model.cairo` grows **linearly in `time_delta`** but is
applied **multiplicatively**:

```cairo
let utilization_delta = ((utilization - max_target_utilization) * SCALE)
    / (UTILIZATION_SCALE - max_target_utilization);
let growth = half_life_scaled + (utilization_delta * time_delta);
(full_utilization_rate * growth) / half_life_scaled
```

The parameter is named **`rate_half_life`**, and the formula confirms the intended semantics exactly:
with `time_delta == rate_half_life` and `utilization_delta == SCALE`, `growth == 2 × half_life_scaled`,
so the rate **doubles over one half-life**. That is the documented behaviour.

But `R × (1 + k·Δt)` applied `n` times over the same total time `T` gives `R × (1 + k·T/n)ⁿ`, which
converges to `R × e^{k·T}`. The realized ramp therefore depends entirely on **how often somebody
triggers an update**:

| half-lives elapsed | intended (one update) | poked every block | overshoot |
|---|---|---|---|
| 1.0 | 2.00× | 2.72× | 1.36× |
| 2.0 | 3.00× | 7.39× | 2.46× |
| 3.5 | 4.50× | 33.12× | **7.36×** |
| 5.0 | 6.00× | 148.41× | 24.74× |
| 7.0 | 8.00× | 1096.63× | 137.08× |

With `rate_half_life = 2 days`, 3.5 half-lives is **one week**: the borrow rate ramps to 33× instead
of the intended 4.5×.

The decay branch (`utilization < min_target_utilization`) has the same structure inverted, so
frequent poking accelerates decay below the intended floor too. The direction is chosen by whoever
pokes — a lender pokes while utilization is high, a borrower pokes while it is low.

## 2. The poke is free and permissionless — confirmed through the whole call path

1. `asset_config()` (`pool.cairo`) recomputes the accumulator on **every call in a new block**:
   `if asset_config.last_updated != get_block_timestamp() { … new_rate_accumulator … }`.
2. `context()` calls `asset_config()` for both the collateral and the debt asset.
3. `modify_position` → `context()` → `update_position`, which **persists** it:
   `self.asset_configs.write((collateral_asset), context.collateral_asset_config);`
4. `modify_position` has **no minimum-amount check**. `assert_delta_invariants` explicitly permits
   all-zero deltas (`(collateral_delta.abs() == 0) == (collateral_shares_delta.abs() == 0)`), and
   `assert_floor_invariant` passes trivially on an empty position.

So a **zero-value `modify_position` from any address** advances and persists one rate step. The
`last_updated != get_block_timestamp()` guard caps this at one effective poke per block, which is
exactly what the table above models.

## 3. Where it leads: the `18 × SCALE` ceiling

`assert_security_invariants` hard-fails above a fixed cap:

```cairo
let safe_rate_accumulator = collateral_accumulator < 18 * SCALE && debt_accumulator < 18 * SCALE;
assert!(safe_rate_accumulator, "unsafe-rate-accumulator");
```

`last_rate_accumulator` is written in exactly two places in the contract — `add_asset` initialises it
to `SCALE`, `new_rate_accumulator` compounds it upward — and there is **no reset, no setter, no admin
override**. The assert runs from `assert_invariants` on both `modify_position` **and**
`liquidate_position` (`is_liquidation` only skips `assert_position_invariants`), so at the ceiling
**repayment and liquidation revert too** — the two operations a user would need to escape. That is
`Permanent freezing of user funds`, the programme's Critical category.

Section 1 is what makes this more than theoretical: the march to the ceiling can be driven up to
7× faster than the documented half-life implies, for gas.

## Honest severity assessment

The mechanism is solid. The severity mapping is where this is weak, and the submission must say so:

- **Vesu's High bar is "direct theft of user funds… ≥1% of TVL"**; Critical is ≥10% or permanent
  freezing. An interest-rate distortion transfers value from borrowers to lenders — real, but
  characterising it as *theft* is a stretch a judge may not accept, and clearing 1% of TVL requires
  a large pool distorted for a sustained period.
- **In a busy pool the attacker adds little.** Natural traffic already pokes most blocks, so the
  realized rate is near the exponential ceiling anyway. The exploitable gap is a pool with
  *high utilization but low interaction frequency* — a real but narrow combination.
- **The ceiling variant needs the growth to be free.** It is not: pushing utilization up means
  borrowing, and borrowing means paying interest to the pool's real lenders. Against a
  self-created pool it is cheap, but pools are isolated, so there is no victim. Poking is free, but
  poking alone cannot create the high utilization it amplifies.

The strongest honest framing is **not** "attacker drains a pool" but: *the borrow rate is supposed to
be governed by `rate_half_life`, and instead it is governed by how often an unprivileged third party
calls a zero-value function — with a measured 7.36× divergence over one week at realistic parameters,
in a direction the caller chooses.*

## Next steps

1. **Get the mainnet `InterestRateConfig`** for live assets — `rate_half_life`,
   `max_full_utilization_rate`, `min/max_target_utilization`. `max_full_utilization_rate` clamps the
   overshoot, so it decides whether the 7.36× is realizable or clipped early. This single fetch
   determines whether this is submittable.
2. **Write the snforge PoC**: two identical pools, one poked every block, one poked once, same
   elapsed time and utilization — assert the divergence in `last_rate_accumulator` and in interest
   actually charged to a borrower. The toolchain from the earlier Vesu round applies (scarb 2.11.4,
   snforge 0.46.0, OZ v2.0.0 as a path dependency).
3. **Check `calculate_fee_shares`** on the same path: `asset_config()` mints fee shares on every
   recomputation. Whether repeated per-block recomputation mints *more* total fee shares than one
   large step is a separate rounding question, and it would land in the fee recipient's pocket.
4. Only then decide on submission, against the severity discussion above and the 250 USDC deposit.
