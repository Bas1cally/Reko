# PoC — Vesu rate-ramp path dependence

3 tests, all passing, run against the **real** Vesu functions. Full output in `PoC-RESULTS.txt`.

## What is real and what is not

`calculate_interest_rate`, `calculate_rate_accumulator` and `calculate_fee_shares` are **imported
from the contest source and executed unmodified** — nothing is reimplemented. The only thing the
harness supplies is the driver loop, and that loop replays exactly what `Pool::asset_config()` does
on every interaction: recompute the accumulator, mint fee shares against the delta, fold both back
into the config.

`cfg()` is copied verbatim from the project's own `src/test/setup_v2.cairo::test_interest_rate_config()`
— these are Vesu's parameters, not ones chosen to make the numbers look good.

## Running it

Requires the toolchain the project pins: scarb 2.11.4, snforge 0.46.0, universal-sierra-compiler 2.5.0.
`scarbs.xyz` is egress-blocked in this environment, so `openzeppelin 2.0.0` has to be cloned from
GitHub and wired as a path dependency with `snforge_std` / `assert_macros` stripped from its
manifests.

```bash
cp test_rate_path_dependence.cairo <vesu-v2>/src/test/
# register it in src/lib.cairo under the #[cfg(test)] mod test block
snforge test test_rate_path_dependence --max-n-steps 400000000
```

The step limit matters: each iteration runs the real Cairo functions, so a 30-day sweep at
block granularity (86,400 steps) exhausts the default budget. 720 steps is enough — the effect is
monotone in step count and has essentially converged by then.

## Results (30 days, 50% utilization, 10M debt, identical elapsed time)

| updates over the period | interest charged | fee shares minted |
|---|---|---|
| 1 (quiet pool) | 19,525.04 | 1,950.79 |
| 6 | 22,582.58 | — |
| 30 (daily) | 23,408.56 | 2,339.55 |
| 180 | 23,596.23 | — |
| 720 (hourly) | **23,625.51** | **2,361.29** |

**+21.0%** interest for identical elapsed time and identical utilization. The only variable is how
often somebody triggered an update. Monotone in step count, converging upward — as the maths
predicts, since `R·(1+k·Δt)` applied `n` times converges to `R·e^{k·T}`.

## The control matters more than the headline

`test_control_no_drift_inside_target_band` runs the same comparison at **80%** utilization, inside
`[min_target, max_target]`, where the rate is not supposed to move at all. Result:

```
control: full_utilization_rate unchanged? a=32150205761 b=32150205761
```

Identical to the last digit. The harness does not manufacture differences where the model says there
should be none, which is what makes the 21% in the decay branch trustworthy.

## Two things this settles, one of them against my own earlier claim

**The Python model was right.** Before writing this test the numbers came from a Python
reimplementation of the formulas — a model, not a proof. It predicted 19,506 vs 23,607 (ratio 1.2103)
for 30 days; the real Cairo gives 19,525 vs 23,626 (ratio 1.2100). Agreement to four significant
figures. The earlier figures in `LEAD.md` stand.

**The fee-share rounding lead is dead.** I had flagged `calculate_fee_shares` as the most promising
remaining angle, on the theory that many small mintings might round in the fee recipient's favour
relative to one large minting. Measured: the fee-share ratio is **1.21043** against an interest ratio
of **1.21001** — a 0.035% difference, which is proportional tracking plus noise, not an exploitable
edge. There is no independent fee-rounding gain. That lead is closed.
