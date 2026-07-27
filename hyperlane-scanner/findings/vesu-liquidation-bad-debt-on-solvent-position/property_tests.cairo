// Probe tests. Not part of the upstream suite.
// Properties that must hold for the protocol to be solvent; each one is a place
// where a violation would be a real finding.
#[cfg(test)]
mod TestZZProbe {
    use openzeppelin::utils::math::{Rounding, u256_mul_div};
    use vesu::common::{calculate_collateral, calculate_collateral_shares, calculate_debt, calculate_nominal_debt};
    use vesu::data_model::AssetConfig;
    use vesu::units::SCALE;

    fn cfg(reserve: u256, tcs: u256, tnd: u256, ra: u256, scale: u256) -> AssetConfig {
        AssetConfig {
            total_collateral_shares: tcs,
            total_nominal_debt: tnd,
            reserve,
            max_utilization: SCALE,
            floor: 0,
            scale,
            is_legacy: false,
            last_updated: 0,
            last_rate_accumulator: ra,
            last_full_utilization_rate: 0,
            fee_rate: 0,
            fee_shares: 0,
        }
    }

    // ------------------------------------------------------------------
    // P1: depositing `x` assets and immediately redeeming the minted shares
    //     must never return more than `x`.
    // ------------------------------------------------------------------
    #[test]
    #[fuzzer(runs: 300, seed: 7)]
    fn p1_deposit_redeem_roundtrip_never_profits(x_raw: u64, reserve_raw: u64, tnd_raw: u64, ra_raw: u32) {
        let scale: u256 = 1_000_000;
        let x: u256 = (x_raw.into() % 1_000_000_000_000_u256) + 1;
        let reserve: u256 = (reserve_raw.into() % 1_000_000_000_000_u256) + 1;
        let tnd: u256 = tnd_raw.into() % 1_000_000_000_000_u256;
        let ra: u256 = SCALE + (ra_raw.into() * 1_000_000_000_u256);

        let c0 = cfg(reserve, reserve * (SCALE / scale), tnd, ra, scale);
        // mint: round shares down
        let shares = calculate_collateral_shares(x, c0, false);
        if shares == 0 {
            return;
        }
        // state after the deposit
        let c1 = cfg(reserve + x, c0.total_collateral_shares + shares, tnd, ra, scale);
        // redeem: round assets down
        let back = calculate_collateral(shares, c1, false);
        assert!(back <= x, "P1 violated: put in {} got back {}", x, back);
    }

    // ------------------------------------------------------------------
    // P2: withdrawing exactly `x` assets must burn at least as many shares
    //     as `x` is worth.
    // ------------------------------------------------------------------
    #[test]
    #[fuzzer(runs: 300, seed: 11)]
    fn p2_withdraw_burns_enough_shares(x_raw: u64, reserve_raw: u64, tnd_raw: u64, ra_raw: u32) {
        let scale: u256 = 1_000_000;
        let reserve: u256 = (reserve_raw.into() % 1_000_000_000_000_u256) + 1;
        let x: u256 = (x_raw.into() % reserve) + 1;
        let tnd: u256 = tnd_raw.into() % 1_000_000_000_000_u256;
        let ra: u256 = SCALE + (ra_raw.into() * 1_000_000_000_u256);

        let c = cfg(reserve, reserve * (SCALE / scale), tnd, ra, scale);
        // withdraw by assets: shares rounded up
        let shares = calculate_collateral_shares(x, c, true);
        // those shares valued back, rounded down
        let value = calculate_collateral(shares, c, false);
        assert!(value >= x, "P2 violated: withdrew {} but burnt shares worth {}", x, value);
    }

    // ------------------------------------------------------------------
    // P3: borrowing `d` must book at least `d` of debt; repaying `d` must
    //     never clear more than `d`.
    // ------------------------------------------------------------------
    #[test]
    #[fuzzer(runs: 300, seed: 13)]
    fn p3_debt_roundtrip(d_raw: u64, ra_raw: u32) {
        let scale: u256 = 1_000_000;
        let d: u256 = (d_raw.into() % 1_000_000_000_000_u256) + 1;
        let ra: u256 = SCALE + (ra_raw.into() * 1_000_000_000_u256);

        // borrow: nominal debt rounded up, then valued back rounded down
        let nd_up = calculate_nominal_debt(d, ra, scale, true);
        let d_back = calculate_debt(nd_up, ra, scale, false);
        assert!(d_back >= d, "P3a violated: borrowed {} booked {}", d, d_back);

        // repay: nominal debt rounded down, then valued back rounded up
        let nd_down = calculate_nominal_debt(d, ra, scale, false);
        let d_cleared = calculate_debt(nd_down, ra, scale, true);
        assert!(d_cleared <= d, "P3b violated: repaid {} cleared {}", d, d_cleared);
    }

    // ------------------------------------------------------------------
    // Replica of Pool::compute_liquidation_amounts (pool.cairo:716-788),
    // minus the min_collateral_to_receive assert.
    // ------------------------------------------------------------------
    fn liq(
        collateral: u256,
        collateral_price: u256,
        coll_scale: u256,
        debt: u256,
        debt_price: u256,
        debt_scale: u256,
        liquidation_factor: u256,
        mut debt_to_repay: u256,
    ) -> (u256, u256, u256) {
        let mut collateral_value = u256_mul_div(collateral, collateral_price, coll_scale, Rounding::Floor);
        let debt_value = u256_mul_div(debt, debt_price, debt_scale, Rounding::Ceil);

        let liquidation_factor = if liquidation_factor == 0 {
            SCALE
        } else {
            liquidation_factor
        };

        debt_to_repay = if debt_to_repay > debt {
            debt
        } else {
            debt_to_repay
        };

        let collateral_value_to_receive = u256_mul_div(debt_to_repay, debt_price, debt_scale, Rounding::Floor);
        let mut collateral_to_receive = u256_mul_div(
            u256_mul_div(collateral_value_to_receive, SCALE, collateral_price, Rounding::Floor),
            coll_scale,
            liquidation_factor,
            Rounding::Floor,
        );
        collateral_to_receive = if collateral_to_receive > collateral {
            collateral
        } else {
            collateral_to_receive
        };

        collateral_value = u256_mul_div(collateral_value, liquidation_factor, SCALE, Rounding::Floor);

        let mut bad_debt = 0;
        if collateral_value < debt_value {
            if collateral_value < u256_mul_div(debt_to_repay, debt_price, debt_scale, Rounding::Ceil) {
                bad_debt =
                    u256_mul_div(debt_value - collateral_value, debt_scale, debt_price, Rounding::Floor);
                debt_to_repay = debt;
            } else {
                bad_debt = u256_mul_div(debt_to_repay, debt_value - collateral_value, collateral_value, Rounding::Floor);
                debt_to_repay = debt_to_repay + bad_debt;
            }
        }

        (collateral_to_receive, debt_to_repay, bad_debt)
    }

    // ------------------------------------------------------------------
    // P4: `settle_position` transfers `debt_to_repay - bad_debt` from the
    //     liquidator. If bad_debt ever exceeds debt_to_repay that subtraction
    //     underflows and the liquidation reverts -> position can never be
    //     closed -> permanently frozen collateral + permanent bad debt.
    // ------------------------------------------------------------------
    #[test]
    #[fuzzer(runs: 500, seed: 17)]
    fn p4_bad_debt_never_exceeds_repaid(
        collateral_raw: u64, debt_raw: u64, cp_raw: u32, dp_raw: u32, lf_raw: u16, repay_raw: u64,
    ) {
        let coll_scale: u256 = 1_000_000_000_000_000_000;
        let debt_scale: u256 = 1_000_000;
        let collateral: u256 = collateral_raw.into() % 1_000_000_000_000_000_000_000_u256;
        let debt: u256 = (debt_raw.into() % 1_000_000_000_000_u256) + 1;
        // prices in [1e12, ~4.3e21]
        let collateral_price: u256 = (cp_raw.into() + 1) * 1_000_000_000_000_u256;
        let debt_price: u256 = (dp_raw.into() + 1) * 1_000_000_000_000_u256;
        // liquidation factor in (0, SCALE]
        let lf: u256 = ((lf_raw.into() % 10_000_u256) + 1) * (SCALE / 10_000);
        let repay: u256 = repay_raw.into() % (debt + 1);

        let (coll_out, repaid, bad_debt) = liq(
            collateral, collateral_price, coll_scale, debt, debt_price, debt_scale, lf, repay,
        );

        assert!(
            bad_debt <= repaid,
            "P4 violated: bad_debt {} > debt_to_repay {} (coll {} debt {} cp {} dp {} lf {} req {})",
            bad_debt,
            repaid,
            collateral,
            debt,
            collateral_price,
            debt_price,
            lf,
            repay,
        );
        assert!(coll_out <= collateral, "P5 violated: released {} of {}", coll_out, collateral);
    }

    // ------------------------------------------------------------------
    // P6: the liquidator must never walk away with collateral worth more
    //     than (value actually paid) / liquidation_factor. A violation means
    //     lenders are funding the bonus beyond the configured discount.
    // ------------------------------------------------------------------
    #[test]
    #[fuzzer(runs: 500, seed: 23)]
    fn p6_liquidator_bonus_bounded_by_liquidation_factor(
        collateral_raw: u64, debt_raw: u64, cp_raw: u16, dp_raw: u16, lf_raw: u16, repay_raw: u64,
    ) {
        let coll_scale: u256 = 1_000_000_000_000_000_000;
        let debt_scale: u256 = 1_000_000;
        let collateral: u256 = (collateral_raw.into() % 1_000_000_000_000_000_000_000_u256) + 1;
        let debt: u256 = (debt_raw.into() % 1_000_000_000_000_u256) + 1;
        let collateral_price: u256 = (cp_raw.into() + 1) * 1_000_000_000_000_000_u256;
        let debt_price: u256 = (dp_raw.into() + 1) * 1_000_000_000_000_000_u256;
        let lf: u256 = ((lf_raw.into() % 10_000_u256) + 1) * (SCALE / 10_000);
        let repay: u256 = repay_raw.into() % (debt + 1);

        let (coll_out, repaid, bad_debt) = liq(
            collateral, collateral_price, coll_scale, debt, debt_price, debt_scale, lf, repay,
        );
        if repaid < bad_debt {
            return; // covered by P4
        }
        let paid = repaid - bad_debt; // what settle_position pulls from the liquidator
        let paid_value = u256_mul_div(paid, debt_price, debt_scale, Rounding::Floor);
        let received_value = u256_mul_div(coll_out, collateral_price, coll_scale, Rounding::Floor);
        // allow 1 unit of rounding slack on top of the configured discount
        let max_received = u256_mul_div(paid_value, SCALE, lf, Rounding::Ceil) + 1;
        assert!(
            received_value <= max_received,
            "P6 violated: paid_value {} received_value {} max {} (lf {} coll {} debt {} cp {} dp {} req {})",
            paid_value,
            received_value,
            max_received,
            lf,
            collateral,
            debt,
            collateral_price,
            debt_price,
            repay,
        );
    }
}
