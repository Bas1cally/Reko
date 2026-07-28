#[cfg(test)]
mod TestRatePathDependence {
    use snforge_std::start_cheat_block_timestamp_global;
    use vesu::common::{calculate_debt, calculate_fee_shares, calculate_rate_accumulator};
    use vesu::data_model::AssetConfig;
    use vesu::interest_rate_model::InterestRateConfig;
    use vesu::interest_rate_model::interest_rate_model_component::calculate_interest_rate;
    use vesu::units::{PERCENT, SCALE};

    // Verbatim from src/test/setup_v2.cairo::test_interest_rate_config()
    fn cfg() -> InterestRateConfig {
        InterestRateConfig {
            min_target_utilization: 75_000,
            max_target_utilization: 99_999,
            target_utilization: 87_500,
            min_full_utilization_rate: 1582470460,
            max_full_utilization_rate: 32150205761,
            zero_utilization_rate: 158247046,
            rate_half_life: 172_800,
            target_rate_percent: 20 * PERCENT,
        }
    }

    // A pool with 10M debt against 10M reserve => 50% utilization, below
    // min_target_utilization (75%), i.e. the decay branch: the branch that is
    // actually reachable at these parameters.
    fn asset_config() -> AssetConfig {
        AssetConfig {
            total_collateral_shares: 20_000_000 * SCALE,
            total_nominal_debt: 10_000_000 * SCALE,
            reserve: 10_000_000 * SCALE,
            max_utilization: SCALE,
            floor: 0,
            scale: SCALE,
            is_legacy: false,
            last_updated: 0,
            last_rate_accumulator: SCALE,
            last_full_utilization_rate: 32150205761, // start at the max rate
            fee_rate: 10 * PERCENT,
            fee_shares: 0,
        }
    }

    const UTIL_50: u256 = SCALE / 2;

    /// Replays exactly what `Pool::asset_config()` does on each interaction:
    /// recompute the accumulator, mint fee shares against the delta, fold both
    /// back into the config. `steps` interactions of `dt` seconds each.
    fn advance(mut c: AssetConfig, dt: u64, steps: u32) -> AssetConfig {
        let mut i = 0_u32;
        let mut now = c.last_updated;
        while i < steps {
            now += dt;
            start_cheat_block_timestamp_global(now);

            let (interest_rate, next_furate) = calculate_interest_rate(
                cfg(), UTIL_50, dt, c.last_full_utilization_rate,
            );
            let new_acc = calculate_rate_accumulator(c.last_updated, c.last_rate_accumulator, interest_rate);
            let fee_shares = calculate_fee_shares(c, new_acc);

            c.last_rate_accumulator = new_acc;
            c.last_full_utilization_rate = next_furate;
            c.last_updated = now;
            c.total_collateral_shares += fee_shares;
            c.fee_shares += fee_shares;

            i += 1;
        }
        c
    }

    /// Total interest charged to borrowers = debt(now) - debt(start).
    fn accrued(c: @AssetConfig) -> u256 {
        calculate_debt(*c.total_nominal_debt, *c.last_rate_accumulator, *c.scale, false)
            - calculate_debt(*c.total_nominal_debt, SCALE, *c.scale, false)
    }

    /// 30 days of identical elapsed time and identical utilization. The ONLY
    /// difference is how many times an unprivileged party triggered an update.
    /// Step counts are kept modest because each iteration runs the real Cairo
    /// functions; the effect is present for any n > 1 and converges upward as n
    /// grows, which `test_convergence` below demonstrates.
    #[test]
    fn test_rate_path_dependence_30_days() {
        let total: u64 = 30 * 86400;

        let quiet = advance(asset_config(), total, 1); // nobody interacts, one settle at the end
        let daily = advance(asset_config(), 86400, 30); // once a day
        let hourly = advance(asset_config(), 3600, 720); // once an hour

        println!("=== 30 days, 50% utilization, 10M debt, identical elapsed time ===");
        println!("quiet  (1 update)  acc={} interest={} fee_shares={}", quiet.last_rate_accumulator, accrued(@quiet), quiet.fee_shares);
        println!("daily  (30x)       acc={} interest={} fee_shares={}", daily.last_rate_accumulator, accrued(@daily), daily.fee_shares);
        println!("hourly (720x)      acc={} interest={} fee_shares={}", hourly.last_rate_accumulator, accrued(@hourly), hourly.fee_shares);
        println!("interest ratio hourly/quiet (x1000) = {}", (accrued(@hourly) * 1000) / accrued(@quiet));
        println!("fee_shares ratio hourly/quiet (x1000) = {}", (hourly.fee_shares * 1000) / quiet.fee_shares);

        // The finding: realized interest depends on interaction frequency alone.
        assert!(accrued(@hourly) > accrued(@quiet), "expected path dependence in accrued interest");
        assert!(hourly.fee_shares > quiet.fee_shares, "expected path dependence in fee shares");
    }

    /// The gap widens monotonically with update frequency, converging upward.
    #[test]
    fn test_convergence_in_update_frequency() {
        let total: u64 = 30 * 86400;
        println!("=== steps | interest | fee_shares (30d, 50% util) ===");
        let n1 = advance(asset_config(), total, 1);
        let n6 = advance(asset_config(), total / 6, 6);
        let n30 = advance(asset_config(), total / 30, 30);
        let n180 = advance(asset_config(), total / 180, 180);
        let n720 = advance(asset_config(), total / 720, 720);
        println!("1    | {} | {}", accrued(@n1), n1.fee_shares);
        println!("6    | {} | {}", accrued(@n6), n6.fee_shares);
        println!("30   | {} | {}", accrued(@n30), n30.fee_shares);
        println!("180  | {} | {}", accrued(@n180), n180.fee_shares);
        println!("720  | {} | {}", accrued(@n720), n720.fee_shares);

        assert!(accrued(@n6) > accrued(@n1), "monotone in n: 6 > 1");
        assert!(accrued(@n30) > accrued(@n6), "monotone in n: 30 > 6");
        assert!(accrued(@n180) > accrued(@n30), "monotone in n: 180 > 30");
        assert!(accrued(@n720) > accrued(@n180), "monotone in n: 720 > 180");
    }

    /// Control: at a utilization inside [min_target, max_target] the rate does
    /// not move at all, so frequency must make no difference. If this fails the
    /// harness itself is wrong.
    #[test]
    fn test_control_no_drift_inside_target_band() {
        let total: u64 = 30 * 86400;
        let util_80: u256 = (SCALE * 80) / 100; // between 75% and 99.999%

        let mut a = asset_config();
        let mut b = asset_config();
        // inline advance with util_80
        let mut i = 0_u32;
        let mut now = 0_u64;
        now += total;
        start_cheat_block_timestamp_global(now);
        let (ir, fr) = calculate_interest_rate(cfg(), util_80, total, a.last_full_utilization_rate);
        a.last_rate_accumulator = calculate_rate_accumulator(a.last_updated, a.last_rate_accumulator, ir);
        a.last_full_utilization_rate = fr;

        now = 0;
        while i < 720_u32 {
            now += total / 720;
            start_cheat_block_timestamp_global(now);
            let (ir2, fr2) = calculate_interest_rate(cfg(), util_80, total / 720, b.last_full_utilization_rate);
            b.last_rate_accumulator = calculate_rate_accumulator(b.last_updated, b.last_rate_accumulator, ir2);
            b.last_full_utilization_rate = fr2;
            b.last_updated = now;
            i += 1;
        }

        println!("control: full_utilization_rate unchanged? a={} b={}", a.last_full_utilization_rate, b.last_full_utilization_rate);
        assert!(a.last_full_utilization_rate == b.last_full_utilization_rate, "rate must not drift inside the target band");
    }
}
