# Vesu v2 — full review coverage

Complete pass over all 11 in-scope source files (~4,400 lines of non-test Cairo).
The finding is in `README.md`; this records everything else that was checked, so a
later pass doesn't repeat it.

**Harness**: `scarb 2.11.4`, `snforge 0.46.0`, `universal-sierra-compiler 2.5.0`.
`scarbs.xyz` is blocked by this environment's egress policy, so `openzeppelin
2.0.0` was pulled from `OpenZeppelin/cairo-contracts@v2.0.0` and wired in as a
path dependency with its test-only dev-dependencies stripped. Upstream suite:
**169/169 pass** in that tree.

## Files

| File | Lines | Verdict |
|---|---|---|
| `units.cairo` | 8 | constants only |
| `math.cairo` | 125 | `pow_scale` / `log_10` / `pow_10` — checked for u256 overflow, see below |
| `data_model.cairo` | 151 | asserts on scale / max_utilization / fee_rate / max_ltv ≤ liquidation_factor are all present |
| `common.cairo` | 332 | rounding conventions verified by fuzzing, all conservative |
| `packing.cairo` | 215 | `pack` uses `try_into().expect(...)` everywhere — panics, never truncates |
| `interest_rate_model.cairo` | 328 | every subtraction guarded by `assert_interest_rate_config`, see below |
| `oracle.cairo` | 342 | one real gap, killed by reachability — see below |
| `pool.cairo` | 1596 | **finding here**; rest checked |
| `v_token.cairo` | 521 | clean |
| `pool_factory.cairo` | 553 | clean |
| `vendor/*` | 47 | interfaces only |

## Checked and sound

### `common.cairo` — rounding

Five fuzz properties (`property_tests.cairo`, 300–500 runs each, all pass):

| Property | Result |
|---|---|
| deposit → redeem round-trip never returns more than deposited | holds |
| withdrawing `x` assets always burns shares worth ≥ `x` | holds |
| borrow rounds debt up; repay rounds cleared debt down | holds |
| `bad_debt ≤ debt_to_repay` (otherwise `settle_position` underflows and the position could never be closed) | holds |
| liquidator's collateral ≤ paid value ÷ `liquidation_factor` | holds |

The asymmetry that looked suspicious — `calculate_collateral_shares` computes
`total_assets` with `!round_up` while `calculate_collateral` uses `round_up` — is
correct in all four deposit/withdraw × native/assets combinations. Each one
biases against the user.

Full-liquidation round-trip also checked by hand:
`calculate_nominal_debt(calculate_debt(N, ↑), ↓) ≥ N`, so the clamp in
`apply_position_update_to_context` always fires and no dust `nominal_debt` is
left behind to trip `assert_floor_invariant`.

### `packing.cairo`

`floor` and `scale` are stored as base-10 exponents and reconstructed with
`pow_10_or_0`, which silently rounds to a power of ten — but `pack` is only
reached with values that came out of `unpack`, and every path that *sets* those
fields (`add_asset`, `set_asset_parameter`) calls `assert_storable_asset_config`,
which does a pack/unpack round-trip and compares all twelve fields.

`last_rate_accumulator` is a `u64`, so the maximum storable value is ≈1.845e19;
`assert_security_invariants` rejects anything ≥ `18 * SCALE` = 1.8e19, i.e. the
runtime check is strictly tighter than the storage width. An asset whose
accumulator reaches 18× would be permanently frozen (no repay, no withdraw, no
liquidation) — that is the explicit, deliberate `unsafe-rate-accumulator` bound,
and `test_modify_position_unsafe_rate_accumulator` covers it.

### `interest_rate_model.cairo`

Every subtraction in `calculate_interest_rate` / `full_utilization_rate` is
protected by an invariant that `assert_interest_rate_config` enforces:

- `next_full_utilization_rate − zero_utilization_rate` ≥ 0 because the result is
  clamped to `[min_full_utilization_rate, max_full_utilization_rate]` and
  `zero_utilization_rate ≤ min_full_utilization_rate` is asserted.
- `next_full_utilization_rate − target_rate` ≥ 0 because `target_rate_percent ≤ SCALE`.
- `UTILIZATION_SCALE − target_utilization` > 0 because
  `target_utilization ≤ max_target_utilization < UTILIZATION_SCALE`.
- `utilization` can never exceed `UTILIZATION_SCALE`: it is derived from
  `calculate_utilization`, which is bounded by `SCALE`, then divided by 1e13.

`pow_scale` squares `x` up to `log2(time_delta)` times, so a u256 overflow needs
roughly `time_delta × rate > 47`. At the live `max_full_utilization_rate` that is
on the order of 15 years of complete dormancy for one asset. Not reachable.

### `oracle.cairo` — real gap, not live

`price()` picks between a spot read and a Pragma TWAP, but computes validity
**only** from the spot entry:

```cairo
let price = if start_time_offset == 0 || time_window == 0 { spot } else { twap };
let valid = (timeout == 0 || time_delta <= timeout)      // spot's last_updated_timestamp
    && (number_of_sources <= response.num_sources_aggregated)  // spot's source count
    && (response.price.into() != 0);                     // spot's price, not the returned one
```

In the TWAP branch nothing about the returned value is validated — not its age,
not its source count, not that it is non-zero. A zero price on a debt asset makes
`debt_value == 0`, which makes `is_collateralized` unconditionally true and the
floor check pass, i.e. unlimited borrowing of that reserve.

**Not reachable on mainnet, twice over:**

1. Every asset in every live pool config (`vesuxyz/changelog@3ed4dbe`) has
   `start_time_offset = 0` **and** `time_window = 0`, so the TWAP branch is dead
   code on all five deployed pools.
2. Pragma's `SummaryStats::calculate_twap` asserts `start_index != stop_index`
   ('Not enough data'), so the no-checkpoints case reverts rather than returning
   zero.

Recorded as defence-in-depth only. It becomes live the moment any curator sets
`time_window > 0`, which `assert_oracle_config` explicitly permits.

**Separately noted, configuration not code:** the three Re7 pools
(`re7_sstrk`, `re7_usdc`, `re7_xstrk`) run every asset with `timeout = 0`, which
disables the staleness check entirely (`timeout == 0 || ...`), and
`number_of_sources = 1`. A stalled Pragma feed on those LST pairs would be
accepted indefinitely. This is a per-asset parameter set by the oracle manager,
and the program excludes centralisation risk and third-party oracle data, so it
is not a submission — but it is worth telling them.

### `pool.cairo` — everything except the finding

| Area | Verdict |
|---|---|
| `assert_ownership` | only bypassed for pure deposits / repayments, which is intended and harmless (donating to a stranger's position only helps them) |
| `flash_loan` | no state mutation, no reserve accounting change, so utilisation and the share price are untouched during the callback; re-entering `modify_position` sees consistent state |
| `donate_to_reserve` | curator-only — the Compound-donation vector is closed because `reserve` is an accounting figure, so a raw ERC20 transfer to the pool does nothing |
| `add_asset` inflation fee | `INFLATION_FEE` shares are minted to nobody and never reset (this is the fix for the 2024-12-03 share-inflation disclosure) |
| `asset_config()` interest accrual | idempotent within a block (`last_updated != get_block_timestamp()` guard); every caller that mutates writes the accrued config back |
| `calculate_fee_shares` | denominator is `total_assets + (accrued_interest − fee)`, i.e. the corrected formula from the 2024-12-03 fee-accounting disclosure |
| `receive_as_shares` | gone — the 2025-06-04 rounding-convention disclosure is fixed |
| `claim_fees` | curator / fee-recipient only; `reserve -= fee_amount` can underflow at high utilisation, but that is a revert on a privileged call |
| curator transfer | two-step nominate/accept, `accept` checks `caller == pending_curator` |
| `pause` / `unpause` | pausing agent can only stop, not restart; owner and curator can do both |
| `upgrade` | `assert_only_owner` + `upgrade_name` sanity check. Owner of every pool is the factory owner, i.e. the 3/5 multisig named in the 2025-06 disclosure. Centralisation, out of scope |
| `set_pair_config` / `set_pair_parameter` | curator-only, `assert_pair_config` + `assert_storable_pair_config` |
| `max_ltv = 0` | cannot strand existing debt: a position with debt cannot be created on a pair with `max_ltv = 0`, because `is_collateralized(_, debt>0, 0)` is false |

### `v_token.cairo`

ERC-4626 rounding is correct in all six directions (`preview_mint` and
`preview_withdraw` round up; `preview_deposit`, `preview_redeem`,
`convert_to_*` and `total_assets` round down).

- The vToken's pool position can never carry debt, so it can never be liquidated.
- Nobody but the vToken can reduce that position — `assert_ownership` fires for
  any negative collateral delta, and the vToken never delegates.
- Donating collateral shares into the vToken's position permanently locks them;
  the attacker loses money and holders are unaffected.
- Token accounting nets to zero on every path: `deposit` pulls exactly `assets`,
  `mint` refunds `assets_estimate − assets`, `withdraw` asserts
  `collateral_delta == assets`, `redeem` forwards `collateral_delta`.
- `approve_pool` is public but only re-establishes the intended standing
  approval; the pool can only pull from `get_caller_address()`.

### `pool_factory.cairo`

`create_pool` and `create_oracle` are permissionless by design. `add_asset` and
`update_v_token` take an arbitrary `pool` address and trust `pool.curator()`, so
an attacker can drive them with a fake pool contract — but every mapping is keyed
by `(pool, …)`, so a fake pool cannot collide with a real one, and the only side
effect is a 2000-unit approval on the attacker's own tokens. vToken addresses are
derived from calldata that includes the pool address, and pool addresses use a
`poseidon(nonce, timestamp)` salt, so neither can be pre-empted.

## Not covered

- On-chain state. Every Starknet RPC (Alchemy, Blast, Nethermind, Lava) is
  403-blocked by this environment's egress policy, so all live-parameter claims
  come from the pinned `vesuxyz/changelog` config rather than from chain.
- `src/test/test_invariants.cairo` — 1,580 lines, **entirely commented out** in
  v2. It targets v1's shutdown/recovery/subscription modes, which no longer
  exist, so it is dead weight rather than a coverage hole. Worth mentioning to
  the team.
