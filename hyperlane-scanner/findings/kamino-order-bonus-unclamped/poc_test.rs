#[cfg(test)]
mod poc_unclamped_bonus {
    use super::*;

    /// PoC: `evaluate_stop_loss` returns a normalized distance > 1 once the
    /// obligation's LTV moves past the liquidation threshold, and nothing
    /// clamps it, so the interpolated execution bonus exceeds the order's
    /// configured maximum (and the 10% sanity limit enforced at set time).
    #[test]
    fn stop_loss_distance_exceeds_one_past_liquidation_ltv() {
        // LiquidationLtvCloserThan with a 1-point buffer: t = u - 0.01
        let u = Fraction::from_num(0.70); // unhealthy (liquidation) LTV
        let t = u - Fraction::from_num(0.01);
        let v = Fraction::from_num(0.75); // LTV after a price gap

        let hit = evaluate_stop_loss(v, t, u).expect("condition must be hit");
        let d = hit.normalized_distance_from_threshold.expect("has distance");

        println!("normalized_distance_from_threshold = {d}");
        // interpolate_bonus_rate is private; replicate it verbatim:
        //   start + distance * (end - start)
        let (lo, hi) = (Fraction::from_num(0.0), Fraction::from_num(0.10));
        let bonus = lo + d * (hi - lo);
        println!("interpolated bonus rate = {bonus}  (order max = 0.10, sanity limit = 0.10)");
        assert!(
            d > Fraction::ONE,
            "distance must exceed 1 past the liquidation LTV, got {d}"
        );
        assert!(
            bonus > Fraction::from_num(0.10),
            "bonus must exceed the configured max, got {bonus}"
        );
    }
}
