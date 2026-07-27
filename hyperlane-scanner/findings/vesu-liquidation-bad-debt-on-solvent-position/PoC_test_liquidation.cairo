// Probe: does a liquidation create bad debt on a position that is still solvent
// at market prices? Modelled on test_liquidate_position_scenario_1_full_liquidation.
#[cfg(test)]
mod TestZZLiqProbe {
    use alexandria_math::i257::I257Trait;
    use openzeppelin::token::erc20::{ERC20ABIDispatcher as IERC20Dispatcher, ERC20ABIDispatcherTrait};
    use snforge_std::{start_cheat_caller_address, stop_cheat_caller_address};
    use vesu::data_model::{Amount, AmountDenomination, LiquidatePositionParams, ModifyPositionParams};
    use vesu::oracle::IPragmaOracleDispatcherTrait;
    use vesu::pool::IPoolDispatcherTrait;
    use vesu::test::mock_asset::{IMintableDispatcher, IMintableDispatcherTrait};
    use vesu::test::mock_oracle::{IMockPragmaOracleDispatcher, IMockPragmaOracleDispatcherTrait};
    use vesu::test::setup_v2::{DEBT_PRAGMA_KEY, TestConfig, setup};
    use vesu::units::SCALE;

    // Runs one full liquidation of a position worth 100 USD of collateral against
    // 95 USD of debt (i.e. still over-collateralised at market prices) and reports
    // the bad debt booked plus the change in the debt reserve.
    fn run(liquidation_factor: u256) -> (u256, u256, u256, u256, u256, u256, u256) {
        let (pool, oracle, config, users, _) = setup();
        let TestConfig { collateral_asset, debt_asset, collateral_scale, debt_scale, .. } = config;

        let liquidity_to_deposit = 100 * debt_scale;
        let collateral = 100 * collateral_scale; //   100 units @ 1 USD  = 100 USD
        let debt = 95 * debt_scale / 10; //           9.5 units @ 10 USD =  95 USD (after the price move)
        let debt_price = 10 * SCALE;

        start_cheat_caller_address(pool.contract_address, users.curator);
        pool
            .set_pair_parameter(
                collateral_asset.contract_address,
                debt_asset.contract_address,
                'liquidation_factor',
                liquidation_factor.try_into().unwrap(),
            );
        stop_cheat_caller_address(pool.contract_address);

        start_cheat_caller_address(collateral_asset.contract_address, users.lender);
        IMintableDispatcher { contract_address: debt_asset.contract_address }.mint(users.lender, 100 * debt_scale);
        IMintableDispatcher { contract_address: collateral_asset.contract_address }.mint(users.borrower, collateral);
        stop_cheat_caller_address(collateral_asset.contract_address);

        // LENDER supplies the debt asset
        let params = ModifyPositionParams {
            collateral_asset: debt_asset.contract_address,
            debt_asset: collateral_asset.contract_address,
            user: users.lender,
            collateral: Amount { denomination: AmountDenomination::Assets, value: liquidity_to_deposit.into() },
            debt: Default::default(),
        };
        start_cheat_caller_address(pool.contract_address, users.lender);
        pool.modify_position(params);
        stop_cheat_caller_address(pool.contract_address);

        // BORROWER opens the position while the debt asset is still at 1 USD (LTV 9.5%)
        let params = ModifyPositionParams {
            collateral_asset: collateral_asset.contract_address,
            debt_asset: debt_asset.contract_address,
            user: users.borrower,
            collateral: Amount { denomination: AmountDenomination::Assets, value: collateral.into() },
            debt: Amount { denomination: AmountDenomination::Assets, value: debt.into() },
        };
        start_cheat_caller_address(collateral_asset.contract_address, users.borrower);
        collateral_asset.approve(pool.contract_address, collateral);
        stop_cheat_caller_address(collateral_asset.contract_address);
        start_cheat_caller_address(pool.contract_address, users.borrower);
        pool.modify_position(params);
        stop_cheat_caller_address(pool.contract_address);

        // total assets backing the debt-asset lenders = reserve + outstanding debt
        let ac = pool.asset_config(debt_asset.contract_address);
        let total_assets_before = ac.reserve
            + pool
                .calculate_debt(
                    I257Trait::new(ac.total_nominal_debt, is_negative: false), ac.last_rate_accumulator, ac.scale,
                );
        let liquidator_debt_before = IERC20Dispatcher { contract_address: debt_asset.contract_address }
            .balance_of(users.lender);
        let liquidator_coll_before = IERC20Dispatcher { contract_address: collateral_asset.contract_address }
            .balance_of(users.lender);

        // the debt asset appreciates 10x -> LTV 95%, above the 80% max_ltv
        let mock_pragma_oracle = IMockPragmaOracleDispatcher { contract_address: oracle.pragma_oracle() };
        mock_pragma_oracle.set_price(DEBT_PRAGMA_KEY, debt_price.try_into().unwrap());

        let (collateralized, collateral_value, debt_value) = pool
            .check_collateralization(collateral_asset.contract_address, debt_asset.contract_address, users.borrower);
        assert!(!collateralized, "position must be liquidatable");

        let params = LiquidatePositionParams {
            collateral_asset: collateral_asset.contract_address,
            debt_asset: debt_asset.contract_address,
            user: users.borrower,
            min_collateral_to_receive: 0,
            debt_to_repay: debt,
        };
        start_cheat_caller_address(pool.contract_address, users.lender);
        let response = pool.liquidate_position(params);
        stop_cheat_caller_address(pool.contract_address);

        let ac = pool.asset_config(debt_asset.contract_address);
        let total_assets_after = ac.reserve
            + pool
                .calculate_debt(
                    I257Trait::new(ac.total_nominal_debt, is_negative: false), ac.last_rate_accumulator, ac.scale,
                );
        let liquidator_debt_after = IERC20Dispatcher { contract_address: debt_asset.contract_address }
            .balance_of(users.lender);
        let liquidator_coll_after = IERC20Dispatcher { contract_address: collateral_asset.contract_address }
            .balance_of(users.lender);

        (
            collateral_value,
            debt_value,
            response.bad_debt,
            total_assets_before,
            total_assets_after,
            liquidator_debt_before - liquidator_debt_after,
            liquidator_coll_after - liquidator_coll_before,
        )
    }

    fn report(tag: ByteArray, lf: u256) {
        let (coll_value, debt_value, bad_debt, ta_before, ta_after, paid, received) = run(lf);
        println!("=== {} ===", tag);
        println!("collateral value (market)  : {}", coll_value);
        println!("debt value       (market)  : {}", debt_value);
        println!("bad debt booked            : {}", bad_debt);
        println!("lender total assets before : {}", ta_before);
        println!("lender total assets after  : {}", ta_after);
        println!("liquidator paid  (debt u)  : {}", paid);
        println!("liquidator got   (coll u)  : {}", received);
        assert!(coll_value > debt_value, "precondition: position is solvent at market prices");
        if ta_after < ta_before {
            println!(">>> LENDERS LOST {} debt units on a SOLVENT position", ta_before - ta_after);
        } else {
            println!(">>> lenders unharmed (gained {})", ta_after - ta_before);
        }
    }

    #[test]
    fn probe_bad_debt_on_solvent_position() {
        // 0.90 is the liquidation_discount used on every live mainnet pair
        report("liquidation_factor = 0.90 (mainnet value)", 90 * SCALE / 100);
    }

    #[test]
    fn probe_control_no_liquidation_factor() {
        // control: no discount, same position, same prices
        report("liquidation_factor = 1.00 (control)", SCALE);
    }
}
