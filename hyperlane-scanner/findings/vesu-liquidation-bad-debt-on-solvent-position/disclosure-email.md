To: security@vesu.xyz
Subject: [Security Disclosure] Vesu v2 Singleton — liquidations create bad debt on over-collateralised positions

Hi Vesu team,

I found what I believe is a real economic defect in Singleton::liquidate_position
(vesu-v2, src/pool.cairo) and would like to disclose it responsibly. I could not
find an active Immunefi bug bounty for Vesu — the listing I initially worked from
turned out to be an unofficial, unmaintained mirror — so I'm sending this
directly. Happy to go through whatever process/channel you prefer, including a
formal bounty if one exists that I've missed.

SUMMARY

`compute_liquidation_amounts` (pool.cairo, ~lines 716-788) discounts the
position's collateral value by the pair's `liquidation_factor` *before*
comparing it against the debt value to decide whether the liquidation produces
bad debt:

    collateral_value = collateral_value * liquidation_factor / SCALE;
    if collateral_value < debt_value { ... bad_debt is booked ... }

The comparison should be against the undiscounted collateral value. As written,
the pool books bad debt — charged to the debt asset's lenders — whenever

    collateral_value * liquidation_factor < debt_value

instead of the correct insolvency condition

    collateral_value < debt_value

For any position whose LTV sits between `liquidation_factor` and 100%, the
collateral fully covers the debt at market prices, yet the pool still writes off
the difference so the liquidator can be paid the full configured bonus. That
shortfall comes out of lender principal, not the borrower's equity — which the
function's own doc-comment says should not happen ("In an event where there's
not enough collateral to cover the debt, the liquidation will result in bad
debt").

PROOF

I wrote a test against the unmodified v2 contract (snforge, on top of the
existing setup_v2 fixture) that opens a position with $100 of collateral
against $95 of debt — solvent at market prices — and liquidates it in full,
once at liquidation_factor = 1.00 (control) and once at 0.90 (the value used on
every live mainnet pair per the pinned vesuxyz/changelog config):

    factor 1.00 (control): bad_debt = 0,   lender assets unchanged
    factor 0.90 (mainnet): bad_debt = $5,  lender assets -$5
                            liquidator pays $90, receives $100 (+$10)

Both cases pass; the control isolates the discount as the sole cause. Full test
file and writeup attached / linked below.

REACHABILITY

No oracle manipulation, flash loan, or privileged role needed. Per the pinned
mainnet pool configs, every live pair uses liquidation_factor 0.90 or 0.95, and
several sit only 2-4 LTV points below that in max_ltv (e.g. USDC/USDT: max_ltv
0.93, factor 0.95; wstETH/ETH: max_ltv 0.91, factor 0.95). Ordinary interest
accrual on a maxed-out position reaches the window. liquidate_position is
permissionless, so any liquidator can trigger and keep the bonus.

Upper bound on the avoidable loss, per liquidation, tends toward
collateral_value * (1 - liquidation_factor) as LTV -> 100%: 10% of the
position's collateral on a 0.90 pair, 5% on a 0.95 pair.

I checked this against all four disclosures on docs.vesu.xyz/security/disclosures
(extension trust, fee accounting, share inflation, rounding convention) — none
of them cover this path, and the two that are architecturally adjacent (fee
accounting, share inflation) both look genuinely fixed in v2.

SUGGESTED FIX

Decide insolvency on the undiscounted collateral value, and separately cap the
collateral released so the bonus can't exceed the borrower's remaining equity —
e.g. keep a `market_collateral_value` alongside the discounted figure and test
against that, or clamp released collateral to
`min(theoretical_amount, collateral_value_at_market - debt_value + configured_bonus)`.
Aave/Compound/Kamino all clamp the liquidation bonus to remaining equity in some
form; Vesu currently doesn't.

Would also suggest a regression test for the specific window
`liquidation_factor < LTV < 1.0` — the existing suite covers genuinely insolvent
positions and fully healthy ones, but not this gap.

WHAT I'D APPRECIATE FROM YOU

1. Confirmation you can reproduce, and your take on severity/whether this is
   intended behavior I'm misreading.
2. If there's an active bounty program (Immunefi or otherwise) this should go
   through instead, please point me to it.
3. Coordinated disclosure timeline if you'd like one before this goes anywhere
   public — no rush on my end, happy to sit on it.

I'm attaching/can send the full report and the runnable PoC test file
(snforge, drops into src/test/ and runs against your existing setup_v2
fixture). Let me know the best way to get it to you securely if you'd rather
not have it over plain email.

Best,
[your name]
