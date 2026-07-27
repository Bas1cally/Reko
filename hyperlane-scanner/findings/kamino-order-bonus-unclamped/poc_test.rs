#[cfg(test)]
mod poc_unclamped_bonus {
    use super::*;
    use crate::state::liquidation_operations::calculate_order_execution_bonus_rate;
    use crate::ObligationOrder;

    /// Builds a *legitimate* stop-loss order: `LiquidationLtvCloserThan` with a
    /// 1-point buffer and a bonus range of [0%, 10%] — the maximum the protocol
    /// allows. `validate_order` accepts it (asserted below).
    fn realistic_order() -> ObligationOrder {
        ObligationOrder {
            condition_threshold_sf: Fraction::from_num(0.01).to_bits(),
            opportunity_parameter_sf: Fraction::MAX.to_bits(),
            min_execution_bonus_bps: 0,
            max_execution_bonus_bps: 1000, // 10.00% == EXECUTION_BONUS_SANITY_LIMIT
            condition_type: ConditionType::LiquidationLtvCloserThan.into(),
            opportunity_type: OpportunityType::DeleverageAllDebt.into(),
            padding1: [0; 10],
            padding2: [0; 5],
        }
    }

    #[test]
    fn order_execution_bonus_exceeds_its_own_validated_maximum() {
        let order = realistic_order();

        // 1. The protocol accepts this order, and caps its bonus at 10%.
        validate_order(order).expect("order must be valid");
        let configured_max = *order.execution_bonus_rate_range().end();
        assert_eq!(configured_max, Fraction::from_bps(1000));
        assert!(configured_max <= EXECUTION_BONUS_SANITY_LIMIT);

        // 2. Market state: reserve liquidates at 70% LTV; a price gap pushes the
        //    position to 75% before anyone executes. Nothing exotic.
        let unhealthy_ltv = Fraction::from_num(0.70);
        let ltv_after_gap = Fraction::from_num(0.75);
        let no_bf_ltv = ltv_after_gap; // no borrow factor, the conservative case

        // 3. Condition evaluation, exactly as ConditionType::LiquidationLtvCloserThan does.
        let hit = evaluate_stop_loss(
            ltv_after_gap,
            unhealthy_ltv.saturating_sub(order.condition_threshold()),
            unhealthy_ltv,
        )
        .expect("condition is hit");
        let distance = hit.normalized_distance_from_threshold.unwrap();

        // 4. The real production function.
        let effective = calculate_order_execution_bonus_rate(&order, &hit, no_bf_ltv);

        println!("configured max bonus      = {configured_max}");
        println!("sanity limit              = {EXECUTION_BONUS_SANITY_LIMIT}");
        println!("normalized distance       = {distance}");
        println!("EFFECTIVE bonus rate      = {effective}");
        println!(
            "collateral multiplier     = {} (vs {} if capped correctly)",
            effective + Fraction::ONE,
            configured_max + Fraction::ONE
        );

        assert!(distance > Fraction::ONE, "distance must exceed 1");
        assert!(
            effective > configured_max,
            "BUG: effective bonus {effective} exceeds the order's configured max {configured_max}"
        );
        assert!(
            effective > EXECUTION_BONUS_SANITY_LIMIT,
            "BUG: effective bonus {effective} exceeds the protocol sanity limit {EXECUTION_BONUS_SANITY_LIMIT}"
        );
    }

    /// The executor picks *when* to execute, and the bonus is a curve in LTV
    /// with an interior maximum (the interpolation grows, the
    /// `1 - ltv` cap shrinks). Waiting past the trigger point is strictly
    /// profitable up to that peak.
    #[test]
    fn executor_can_wait_for_a_bonus_far_above_the_cap() {
        let order = realistic_order();
        validate_order(order).unwrap();
        let unhealthy_ltv = Fraction::from_num(0.70);
        let threshold = unhealthy_ltv.saturating_sub(order.condition_threshold());
        let cap = Fraction::from_bps(1000);

        let mut best = (0u32, Fraction::ZERO);
        let mut at_trigger = Fraction::ZERO;
        for ltv_pct in 70u32..=90 {
            let ltv = Fraction::from_num(ltv_pct) / Fraction::from_num(100);
            let Some(hit) = evaluate_stop_loss(ltv, threshold, unhealthy_ltv) else { continue };
            let bonus = calculate_order_execution_bonus_rate(&order, &hit, ltv);
            if ltv_pct == 70 { at_trigger = bonus; }
            if bonus > best.1 { best = (ltv_pct, bonus); }
        }

        println!("bonus at trigger LTV 70%   = {at_trigger}");
        println!("peak bonus  = {} at LTV {}%", best.1, best.0);
        println!("configured/validated cap   = {cap}");

        assert!(best.1 > cap, "peak bonus {} must exceed the cap {cap}", best.1);
        assert!(
            best.1 > at_trigger,
            "waiting past the trigger must pay more than executing immediately"
        );
    }
}
