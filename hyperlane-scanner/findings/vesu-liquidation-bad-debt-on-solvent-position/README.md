# Vesu v2: liquidations book bad debt against lenders on positions that are still over-collateralised

**Target**: `vesuxyz/vesu-v2`, `src/pool.cairo`.

> ## ✅ Programme question RESOLVED — 28 Jul 2026
>
> The open question in this report was never the defect, only *where to send it*. That is now
> answered: **Vesu runs an official bug bounty on Sherlock**, live since 27 Jul 2026 21:57, max
> 50,000 USDC, scope `https://github.com/vesuxyz/vesu-v2` — the exact repo and file this finding
> targets. The earlier Immunefi listing (sourced from an unofficial mirror, never confirmed at
> source, see `../vesu-programme-status.md`) is superseded and should be disregarded.
>
> **But this finding is very likely out of scope for that programme.** It was disclosed by email to
> `security@vesu.xyz` *before* the programme existed, and Sherlock's Vesu scope excludes
> *"vulnerabilities that have already been reported or are known to the protocol team"*. Do **not**
> re-submit it as a fresh Sherlock report — the team has it in their inbox, and a duplicate arriving
> as new work would cost more credibility than the payout is worth.
>
> The correct move is a one-paragraph reply on the existing email thread asking whether a disclosure
> predating the programme qualifies. That puts the decision with them and keeps the disclosure clean.
>
> Two further notes for whoever picks this up:
> - **Submitting to Sherlock's bug bounty platform requires a 250 USDC deposit.** For a finding the
>   team already has, that is a bad bet regardless of the refund rules — which are not verified here.
> - **Severity ceiling is High, not Critical.** Critical needs ≥10% of TVL, High ≥1%. A single
>   liquidation clears neither on its own; the case rests on repeatability. High pays 1,000–10,000 USD.
> - **Expect the "design choice" objection.** The programme lists *"Instant bad debt socialization
>   among lenders of the affected asset only"* as intended. The rebuttal is already the core of this
>   report: the defect is not that bad debt is socialised, but that it is *booked at all* on a
>   position that is still over-collateralised — which the contract's own doc-comment contradicts.

Per that mirror: Immunefi programme `vesu`, max **$100,000**, **no KYC**, and
`src/pool.cairo` is an explicit in-scope `smart_contract` asset.
**File**: `src/pool.cairo` → `Pool::compute_liquidation_amounts` (lines 716–788)
**Reachability**: confirmed against Vesu's own mainnet configuration — see below.
**Proof**: `PoC_test_liquidation.cairo`, runs against the unmodified contract under
`snforge`, both cases pass and print the numbers quoted here.

---

## Summary

`compute_liquidation_amounts` discounts the position's collateral value by the
pair's `liquidation_factor` **before** comparing it to the debt value in order to
decide whether the liquidation produces bad debt. As a result the protocol
declares bad debt — and charges it to the lenders of the debt asset — whenever

```
collateral_value × liquidation_factor  <  debt_value
```

but the honest solvency condition is `collateral_value < debt_value`. For every
position whose LTV sits between `liquidation_factor` and 100%, the collateral
fully covers the debt at market prices, yet the pool still writes off the
difference as bad debt so that the liquidator can be paid the full configured
bonus.

**The liquidation bonus is not capped by the borrower's remaining equity.** Once
the equity runs out, the bonus keeps being paid out of lender principal.

## The code

`src/pool.cairo:740–785`:

```cairo
// apply liquidation factor to debt value to get the collateral amount to release
let collateral_value_to_receive = u256_mul_div(
    debt_to_repay, context.debt_asset_price.value, context.debt_asset_config.scale, Rounding::Floor,
);
let mut collateral_to_receive = u256_mul_div(
    u256_mul_div(collateral_value_to_receive, SCALE, context.collateral_asset_price.value, Rounding::Floor),
    context.collateral_asset_config.scale,
    liquidation_factor,                       // <- divide: this IS the bonus
    Rounding::Floor,
);
collateral_to_receive = if collateral_to_receive > collateral { collateral } else { collateral_to_receive };

// apply liquidation factor to collateral value
collateral_value = u256_mul_div(collateral_value, liquidation_factor, SCALE, Rounding::Floor);  // <- the defect

// account for bad debt if there isn't enough collateral to cover the debt
let mut bad_debt = 0;
if collateral_value < debt_value {                                  // <- compares the DISCOUNTED value
    if collateral_value < u256_mul_div(debt_to_repay, ... Rounding::Ceil) {
        bad_debt = u256_mul_div(debt_value - collateral_value, ... Rounding::Floor);
        debt_to_repay = debt;
    } else { ... }
}
```

`collateral_value` is overwritten with the discounted figure and then used as the
solvency yardstick. The function's own doc-comment states the intent:

> In an event where there's **not enough collateral to cover the debt**, the
> liquidation will result in bad debt.

In the case below there *is* enough collateral to cover the debt.

*(Side note, same doc-comment: it says the bad debt is "distributed amongst the
lenders of the corresponding **collateral** asset". The code charges it to the
**debt** asset's lenders — `apply_position_update_to_context` does
`debt_asset_config.reserve += debt_delta.abs() - bad_debt`. The code's behaviour
is the sensible one; the comment is wrong. Worth fixing either way.)*

## Proof

`PoC_test_liquidation.cairo` builds a position on the stock `setup_v2` fixture:

| | |
|---|---|
| Collateral | 100 units @ $1 = **$100** |
| Debt | 9.5 units @ $10 = **$95** |
| `max_ltv` | 0.80 (fixture default) → LTV 95% ⇒ liquidatable |
| Position is solvent at market prices | **$100 > $95** ✔ |

Same position, liquidated in full, only the `liquidation_factor` differs:

```
=== liquidation_factor = 1.00 (control) ===
collateral value (market)  : 100000000000000000000     ($100)
debt value       (market)  :  95000000000000000000     ($95)
bad debt booked            : 0
lender total assets before : 100000000002000
lender total assets after  : 100000000002000
liquidator paid  (debt u)  : 9500000000000             ($95)
liquidator got   (coll u)  : 9500000000                ($95)
>>> lenders unharmed (gained 0)

=== liquidation_factor = 0.90 (mainnet value) ===
collateral value (market)  : 100000000000000000000     ($100)
debt value       (market)  :  95000000000000000000     ($95)
bad debt booked            : 500000000000              ($5)
lender total assets before : 100000000002000
lender total assets after  :  99500000002000
liquidator paid  (debt u)  : 9000000000000             ($90)
liquidator got   (coll u)  : 10000000000               ($100)
>>> LENDERS LOST 500000000000 debt units on a SOLVENT position
```

Both tests pass. The control isolates the cause: with no discount there is no
bad debt on the identical position; the entire $5 loss is produced by the
discount being applied before the solvency comparison.

**Flow of value in the second case:**

| Party | Change |
|---|---|
| Liquidator | pays $90, receives $100 → **+$10** |
| Borrower | loses $100 collateral, $95 debt cleared → −$5 (their whole equity) |
| **Debt-asset lenders** | **−$5, socialised across every vToken holder** |

A correct implementation pays the liquidator the whole surplus ($100 for $95, a
5.3% bonus) and books **zero** bad debt. Vesu pays the full 11.1% and bills the
difference to the lenders.

## Reachability — confirmed, no manipulation required

`liquidation_factor` is `liquidation_discount` in Vesu's deployment config
(`lib/config.mainnet.ts:70`), which is pinned to
`github.com/vesuxyz/changelog@3ed4dbe`. **Every live mainnet pair uses 0.90 or
0.95 — none uses 1.00:**

| Pool config | Pair | `max_ltv` | `liquidation_discount` | leak window (LTV) |
|---|---|---|---|---|
| `config_prime_sn_main` | usd-coin / tether | 0.93 | **0.95** | 95 – 100% |
| `config_prime_sn_main` | tether / usd-coin | 0.93 | **0.95** | 95 – 100% |
| `config_prime_sn_main` | wrapped-steth / ethereum | 0.91 | **0.95** | 95 – 100% |
| `config_prime_sn_main` | most pairs | 0.70–0.80 | **0.90** | 90 – 100% |
| `config_re7_usdc_sn_main` | ethereum / usd-coin | 0.87 | **0.90** | 90 – 100% |
| `config_re7_xstrk_sn_main` | endur staked strk / starknet | 0.87 | **0.90** | 90 – 100% |

No oracle manipulation, no flash loan, no privileged role. The position only has
to drift past `liquidation_factor` — which, on the stablecoin pair
(`max_ltv` 0.93, `lf` 0.95) and the LST pairs (`max_ltv` 0.87–0.91, `lf`
0.90–0.95), is a **2 to 4 percentage-point** move above the point at which
liquidation first becomes legal. Interest accrual alone gets a maxed-out
position there.

`liquidate_position` is permissionless (`get_caller_address()` is used only as
the counterparty), so anyone can trigger it and keep the bonus.

**Upper bound on the loss:** as LTV → 100%, the avoidable bad debt tends to
`collateral_value × (1 − liquidation_factor)` — **10%** of the position's
collateral on a 0.90 pair, 5% on a 0.95 pair. `debt_cap` on the live pairs is
$50,000,000, so a single maxed pair bounds this in the millions.

## Why this is a defect and not just a parameter choice

1. **It contradicts the function's own specification** (quoted above).
2. **It is avoidable.** The borrower's collateral covers the debt; the shortfall
   is created purely by paying a bonus larger than the equity that exists.
3. **Every comparable protocol caps it.** Aave, Compound and Kamino all clamp
   the liquidation bonus to the remaining equity — Kamino literally computes
   `effective_max_bonus_rate = min(configured_max_bonus_rate, diff_to_bad_debt)`
   where `diff_to_bad_debt = 1 − ltv`. Vesu has no such clamp.
4. **The bad debt is permanent and socialised.** It is never recovered; it
   dilutes every vToken holder of the debt asset immediately.

## Suggested fix

Decide solvency on the *undiscounted* collateral value, and cap the released
collateral so the bonus cannot exceed the borrower's equity:

```cairo
// keep the market value for the solvency test
let market_collateral_value = collateral_value;
...
let mut bad_debt = 0;
if market_collateral_value < debt_value {
    // genuine shortfall only
    ...
}
// and/or clamp the bonus:
//   effective_collateral_to_receive = min(collateral_to_receive, collateral)
//   with the implied bonus capped at (market_collateral_value - debt_value)
```

The liquidator still gets every unit of collateral the position holds; they just
stop being paid out of other people's deposits.

Add a regression test for the window `liquidation_factor < LTV < 1.0` — the
existing suite only covers genuinely insolvent positions
(`test_liquidate_position_scenario_1_full_liquidation`: $80 collateral against
$100 debt) and fully-healthy ones.

## Reproduction

```bash
git clone https://github.com/vesuxyz/vesu-v2 && cd vesu-v2
cp <this dir>/PoC_test_liquidation.cairo src/test/test_zz_liq_probe.cairo
# register the module
sed -i 's|    pub mod test_v_token;|    pub mod test_v_token;\n    pub mod test_zz_liq_probe;|' src/lib.cairo
snforge test test_zz_liq_probe --max-n-steps 100000000
```

Toolchain used: `scarb 2.11.4`, `snforge 0.46.0`, `universal-sierra-compiler 2.5.0`.
The full upstream suite (169 tests) passes unchanged in the same tree.

## Honest caveats

- **Vesu may classify this as intended behaviour.** The discount-before-compare
  is explicit, not an obvious slip, and v1 likely behaved the same way. The
  argument for it being a defect is the doc-comment contradiction plus the fact
  that the loss is avoidable — not that the code looks accidental. Expect that
  argument to be the crux of the report.
- **Checked against all four published disclosures — none covers this.** For the
  record:

  | Disclosure | Subject | Bearing on this finding |
  |---|---|---|
  | 2024-06-07 Extension Trust | v1 Singleton↔Extension trust model | That architecture no longer exists in v2 |
  | 2024-12-03 Fee Accounting | `fee_shares` denominator missing the `(1 − fee_rate)` term | **Already fixed in v2** — `common.cairo:170` uses `total_assets + (accrued_interest − fee)`, which is the corrected formula |
  | 2024-12-03 Share Inflation | `INFLATION_FEE_SHARES` reset could be triggered | **Already fixed in v2** — `add_asset` burns the inflation fee permanently, no reset path exists |
  | 2025-06-04 Rounding Convention | `receive_as_shares` in `liquidate_position` | **Already fixed in v2** — the flag and the code path are gone |

  This finding is in `compute_liquidation_amounts`' bad-debt comparison, which
  none of the four touches.
- Live pair parameters were read from the pinned `vesuxyz/changelog` config, not
  from chain — every Starknet RPC is blocked by this environment's egress policy.
  Confirm on-chain with:
  ```bash
  starkli call 0x451fe483d5921a2919ddd81d0de6696669bccdacd859f72a4fba7656b97c3b5 \
      pair_config <collateral_asset> <debt_asset> --rpc <your-rpc>
  ```
  and check the second returned felt (`liquidation_factor`) is below `1e18`.

## Also checked, clean

`property_tests.cairo` (5 fuzz properties, 300–500 runs each, all pass) rules
out the neighbouring bug classes in the same code:

| Property | Result |
|---|---|
| deposit → redeem round-trip never returns more than deposited | holds |
| withdrawing `x` assets always burns shares worth ≥ `x` | holds |
| borrow rounds debt up, repay rounds cleared debt down | holds |
| `bad_debt` never exceeds `debt_to_repay` (would revert `settle_position`) | holds |
| liquidator's collateral ≤ paid value ÷ `liquidation_factor` | holds |

So the rounding is uniformly conservative and the bonus obeys the configured
factor. The finding above is not a rounding error — it is the missing equity cap.
