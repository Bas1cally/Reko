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

## 4. THE ACTUAL DEFECT — found by digging for a theft path, and it is not a theft

Trying to turn section 1 into value extraction produced a sharper and *different* bug, plus the
reason it cannot be weaponised. Both belong in the record.

**`calculate_rate_accumulator` applies the end-of-interval rate retroactively to the whole interval.**
`rate_accumulator()` computes `next_full_utilization_rate` first — fully decayed or grown over the
entire `time_delta` — derives `interest_rate` from it, and only then calls
`calculate_rate_accumulator(last_updated, last_rate_accumulator, interest_rate)`, which compounds
that single rate across every second since `last_updated`. The correct treatment integrates the rate
over the interval. This one prices the whole interval at its endpoint.

In the decay regime (utilization below `min_target_utilization`) the endpoint is the *lowest* rate of
the interval, so the longer the gap between updates, the more the protocol **undercharges borrowers
and underpays lenders**. Measured with the project's own `test_interest_rate_config`
(`rate_half_life` 2 days, max 101.39% APR, min 4.99% APR), 50% utilization, $10M of debt:

| period | interest if left alone | interest if poked every block | shortfall to lenders |
|---|---|---|---|
| 7 days | $11,104 | $13,964 | $2,860 |
| 14 days | $15,029 | $18,896 | $3,867 |
| 30 days | $19,506 | $23,607 | $4,101 |
| 60 days | $24,582 | $31,928 | **$7,346 (−23%)** |

### Why this is not theft, and why I am not going to dress it up as one

Three separate checks, each confirmed against source rather than assumed:

1. **The manipulable direction is the harmless one.** Anyone can *shrink* the gap by poking; nobody
   can *lengthen* it. Poking moves the result **toward** the correct integral — the "attacker" would
   be repairing the undercharge, not exploiting it. The party who benefits from the defect (the
   borrower) benefits by doing nothing, which is not an attack.
2. **The flash-loan utilization spike is dead.** `calculate_utilization(asset_config.reserve, …)`
   reads the *bookkeeping* reserve, and `flash_loan` moves only real tokens — it never touches
   `asset_config.reserve`. A flash loan therefore does not move utilization at all.
3. **Spike-then-price in one transaction is impossible.** `context()` reads the stored config and
   computes the new accumulator *before* `update_position` applies any deltas, so the utilization
   used is always the pre-transaction value. And the spike transaction itself sets
   `last_updated = now`, so the following interval starts from zero elapsed time.

The growth regime would overcharge borrowers the same way, and that *would* be extractable — but
`max_target_utilization = 99_999` out of 100_000 means it only engages above **99.999%** utilization,
which requires the reserve to be essentially empty. Unreachable in practice.

So the honest classification is a **systematic value leak from lenders to borrowers in quiet pools**,
not an attacker-driven theft. Vesu's programme pays for theft (≥1% TVL) or freezing; it has no
category for this. Submitting it as theft would be the kind of fantasy this engagement was told to
avoid, and a judge would take it apart in one paragraph.

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
