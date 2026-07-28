# Vesu v2 LEAD: `last_rate_accumulator` is monotonic, capped at 18×SCALE, and has no reset

**Status: UNPROVEN LEAD, not a finding.** The structure is confirmed against source; the
*reachability* is not. Do not submit until the open question at the bottom is answered — the whole
thing lives or dies on it. Recorded now because the shape is right and the analysis should not be
lost.

**Target**: `vesuxyz/vesu-v2` @ `e14d772`, `src/pool.cairo`.
**Programme**: Sherlock bug bounty, live 27 Jul 2026, max 50,000 USDC. 250 USDC submission deposit.

## Why this was looked at

Applying the lesson from the Tare contest: the team documents *correctness* exhaustively and
*liveness* barely, so hunt for **a monotonic or one-way piece of state that gates everything and has
no reset path**. In Tare that was `navStart`. The Vesu equivalent is the interest rate accumulator.

## The structure (confirmed against source)

`assert_security_invariants` (`src/pool.cairo`) hard-fails above a fixed ceiling:

```cairo
let collateral_accumulator = context.collateral_asset_config.last_rate_accumulator;
let debt_accumulator = context.debt_asset_config.last_rate_accumulator;
let safe_rate_accumulator = collateral_accumulator < 18 * SCALE && debt_accumulator < 18 * SCALE;
assert!(safe_rate_accumulator, "unsafe-rate-accumulator");
```

Three properties make this the `navStart` shape:

1. **Monotonic.** `last_rate_accumulator` is written in exactly two places in the whole contract:
   `add_asset` initialises it to `SCALE` (1.0), and `new_rate_accumulator` overwrites it with the
   compounding value from the interest rate model. Compounding only goes up.
2. **No reset.** There is no setter, no admin override, no re-init — `add_asset` rejects an asset
   that already exists. Verified by grepping every write to the field.
3. **It gates everything.** `assert_security_invariants` is called from `assert_invariants`, and the
   `is_liquidation` flag only skips `assert_position_invariants` — the security invariants run
   regardless. So once an asset's accumulator reaches `18 × SCALE`, every `modify_position` **and**
   every `liquidate_position` on every pair using that asset reverts. That includes **repayment**
   and **liquidation**, i.e. the two operations a user would need to escape.

If reachable, the impact is `Permanent freezing of user funds` — the programme's own **Critical**
category.

## Why the cap exists at all

Almost certainly overflow protection: `calculate_debt` multiplies nominal debt by the accumulator,
and the packed `AssetConfig` fields are width-limited. 18× is a headroom bound, not a policy. That
makes the shape more interesting, not less: the ceiling is a *safety* check whose trip condition was
apparently never considered as a terminal state.

## The open question — answer this before doing anything else

**How long does an asset take to reach an 18× accumulator at real mainnet configuration, and can an
attacker meaningfully accelerate it?**

- The growth rate is driven by utilization, which is **user-controllable** — any borrower can pin an
  asset at high utilization, and the rate model responds by raising the rate.
- `max_full_utilization_rate` is curator-set (trusted), so the ceiling on the *rate* is not
  attacker-controlled, but the *time spent at that rate* is.
- At 10% APR, 18× takes ~30 years. At a sustained 1000% APR it is roughly 3–4 months. The mainnet
  `InterestRateConfig` values decide which of those worlds this is. **Get them.**

### The honest problem with the attack story

Pushing utilization up means borrowing, and borrowing means **paying interest to the pool's real
lenders**. The attacker funds the very growth they are trying to cause. Two consequences:

- Against a pool with genuine TVL, this is extremely expensive and probably not economic.
- Against a pool the attacker creates themselves (pool creation is permissionless), it is cheap —
  but pools are isolated, so they would only brick their own, with no victim.

That tension is the reason this is filed as a lead and not a finding. The version that would be
worth 50k is one where the accumulator can be driven up **without** the attacker paying proportional
interest — e.g. via a rounding or time-delta path in `calculate_rate_accumulator` that advances the
accumulator faster than real accrued interest. That is the specific thing to look for next.

There is also a no-attacker variant worth pricing: a long-lived, heavily-utilised asset reaching the
cap through **ordinary operation** years in. That is a real protocol-bricks-itself issue with a long
fuse, and the team may reasonably answer "we would migrate first".

## Next steps, in order

1. Read `calculate_rate_accumulator` and `full_utilization_rate` in `src/interest_rate_model.cairo`
   for a path that advances the accumulator disproportionately to real interest — repeated tiny
   `time_delta` updates, rounding direction, or the `last_full_utilization_rate` ratchet.
2. Pull the mainnet `InterestRateConfig` for live assets and compute the actual time-to-18×.
3. If (1) yields nothing and (2) says decades, close this lead and write it up as dead — the same
   way the Kamino TWAP and Vesu oracle-validity leads were closed.
4. Only if it survives both: build the snforge PoC. The toolchain from the earlier Vesu round
   (scarb 2.11.4, snforge 0.46.0, OZ v2.0.0 as a path dependency) still applies.

## Verification notes

Everything under "The structure" was read directly from `vesuxyz/vesu-v2` @ `e14d772`, cloned fresh
— the repo is public now, unlike during the earlier round in this engagement. Nothing here is from
memory or from a mirror.
