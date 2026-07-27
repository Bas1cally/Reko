// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.33;

// =============================================================================
//  NOT EXECUTED. READ THIS BEFORE RUNNING.
// =============================================================================
//
//  This test was written after the repo clone was lost with the execution
//  container, so it has NEVER been compiled or run. Constructor arities and a
//  handful of function signatures are reconstructed from the source as read in
//  session and are flagged inline with `// SIG?`. Every `// SIG?` needs to be
//  checked against the contest commit before this compiles.
//
//  What is NOT reconstructed, and what the finding actually rests on, is the
//  assertion in `test_chargedOffLoan_doesNotInvalidateNav`: that a servicer
//  charge-off of a vault-held loan leaves `_requireFreshNav()` passing. That
//  assertion is expressed through public state only (ownershipNonce,
//  configurationVersion, lastNavUpdate) precisely so it survives signature
//  drift elsewhere in the file.
//
//  Run:  forge test --match-contract NavStalenessLoanLedger -vvv
// =============================================================================

import {Test} from "forge-std/Test.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

import {Loans} from "contracts/Loans.sol";
import {LoansNFT} from "contracts/LoansNFT.sol";
import {PortfolioVault} from "contracts/PortfolioVault.sol";
import {NavCalculator} from "contracts/NavCalculator.sol";
import {Roles, LoanStatus} from "contracts/interfaces/ILoans.sol";

contract MockUSDC is ERC20 {
  constructor() ERC20("Mock USDC", "USDC") {}

  function mint(address to, uint256 amount) external {
    _mint(to, amount);
  }
}

contract NavStalenessLoanLedger is Test {
  MockUSDC internal usdc;
  Loans internal loans;
  LoansNFT internal loansNFT;
  PortfolioVault internal vault;
  NavCalculator internal calculator;

  address internal guardian = makeAddr("guardian");
  address internal recovery = makeAddr("recovery");
  address internal operator = makeAddr("operator"); // approves deposits/redemptions
  address internal originator = makeAddr("originator");
  address internal servicer = makeAddr("servicer");
  address internal borrower = makeAddr("borrower");

  address internal alice = makeAddr("alice"); // exits at the stale price
  address internal bob = makeAddr("bob"); // stays, and eats the loss

  uint64 internal loanId;
  uint128 internal constant PRINCIPAL = 1_000_000e6;
  uint256 internal constant SEED_DEPOSIT = 1_000_000e6;

  function setUp() public {
    usdc = new MockUSDC();

    loans = new Loans(IERC20(address(usdc)), guardian, recovery);
    loansNFT = new LoansNFT(address(loans), "Tare Loans", "https://tare.example/loans/");
    vm.prank(guardian);
    loans.setLoansNFT(address(loansNFT));

    calculator = new NavCalculator(guardian); // SIG?
    vault = new PortfolioVault(IERC20(address(usdc)), address(loans), address(loansNFT), address(calculator), guardian); // SIG?

    vm.startPrank(guardian);
    vault.grantRole(vault.OPERATOR_ROLE(), operator); // SIG?
    loans.approveOriginator(originator);
    vm.stopPrank();

    vm.startPrank(originator);
    loans.registerAddress(Roles.Borrower, borrower);
    loans.registerAddress(Roles.Investor, address(vault));
    loans.registerAddress(Roles.Servicer, servicer);
    vm.stopPrank();

    // Alice and Bob seed the vault with equal stakes, before any loan exists.
    _deposit(alice, SEED_DEPOSIT);
    _deposit(bob, SEED_DEPOSIT);

    // Originate a loan with the vault as investor, so the vault ends up holding the NFT.
    vm.prank(originator);
    loanId = loans.create(borrower, address(vault), servicer, originator, int128(PRINCIPAL), uint48(block.timestamp));

    vm.prank(operator);
    vault.addLoansToNav(_singleton(loanId)); // SIG? -- curated list, this DOES invalidate

    vm.prank(operator);
    vault.fundLoans(_singleton(loanId)); // SIG? -- moves idle USDC into the loan, DOES invalidate

    vm.prank(originator);
    loans.disburse(
      loanId,
      int128(PRINCIPAL),
      0,
      uint48(block.timestamp),
      uint48(block.timestamp + 30 days),
      uint48(block.timestamp + 365 days),
      500,
      0,
      uint48(block.timestamp),
      "disburse"
    );

    _refreshNav();
  }

  // ---------------------------------------------------------------------------
  //  The finding.
  // ---------------------------------------------------------------------------

  /// @notice A servicer charge-off destroys most of the loan's value, and every
  ///         guard in `_requireFreshNav()` still passes. This is the bug: the
  ///         loan ledger is the one documented NAV input with no invalidation.
  function test_chargedOffLoan_doesNotInvalidateNav() public {
    uint256 navBefore = vault.lastNav();
    uint256 nonceBefore = loansNFT.ownershipNonce(address(vault));
    uint256 versionBefore = calculator.configurationVersion();
    uint256 updatedAtBefore = vault.lastNavUpdate();

    // Servicer charges the loan off. Entirely within its own per-loan authority.
    vm.prank(servicer);
    loans.updateLoanData(
      loanId,
      LoanStatus.ChargedOff,
      uint48(block.timestamp + 30 days), // nextDueDate unchanged
      uint48(block.timestamp + 365 days), // maturityDate unchanged
      uint48(block.timestamp)
    );

    // --- the three assertions that carry the finding ---
    assertEq(
      loansNFT.ownershipNonce(address(vault)), nonceBefore, "NFT never moved: ownership nonce guard is blind to this"
    );
    assertEq(
      calculator.configurationVersion(), versionBefore, "calculator untouched: config version guard is blind to this"
    );
    assertEq(vault.lastNavUpdate(), updatedAtBefore, "no invalidation happened: maxNavAge is the ONLY remaining guard");
    assertEq(vault.lastNav(), navBefore, "cached NAV still reports the pre-charge-off value");

    // And the cache is still inside its age window, so `_requireFreshNav()` passes outright.
    assertLe(block.timestamp - vault.lastNavUpdate(), vault.maxNavAge(), "cached NAV is still considered fresh");

    // Prove the cache is wrong: recompute and compare.
    uint256 staleNav = vault.lastNav();
    _refreshNav();
    uint256 trueNav = vault.lastNav();
    assertLt(trueNav, staleNav, "true NAV is strictly lower after the charge-off");
    emit log_named_uint("stale NAV (used for pricing)", staleNav);
    emit log_named_uint("true NAV  (after refresh)   ", trueNav);
    emit log_named_uint("overstatement              ", staleNav - trueNav);
  }

  /// @notice The consequence: Alice exits at the stale price, Bob absorbs her share
  ///         of a loss that had already occurred before she was paid.
  function test_redemptionAtStaleNav_transfersLossToRemainingHolder() public {
    // Alice queues her exit while the loan is still healthy.
    uint256 aliceShares = vault.balanceOf(alice);
    vm.startPrank(alice);
    vault.approve(address(vault), aliceShares); // SIG?
    vault.requestRedeem(aliceShares, alice, alice); // SIG?
    vm.stopPrank();

    // Charge-off lands. No invalidation (proven above).
    vm.prank(servicer);
    loans.updateLoanData(
      loanId,
      LoanStatus.ChargedOff,
      uint48(block.timestamp + 30 days),
      uint48(block.timestamp + 365 days),
      uint48(block.timestamp)
    );

    // Operator approves in the ordinary course of business, inside maxNavAge.
    vm.prank(operator);
    vault.approveRedemption(alice); // SIG?

    vm.prank(alice);
    uint256 alicePayout = vault.redeem(aliceShares, alice, alice); // SIG?

    // Now refresh and look at what Bob is left holding.
    _refreshNav();
    uint256 bobShares = vault.balanceOf(bob);
    uint256 bobValue = (bobShares * vault.lastNav()) / vault.totalSupply();

    emit log_named_uint("alice paid out (stale price)", alicePayout);
    emit log_named_uint("bob's remaining value       ", bobValue);
    emit log_named_uint("bob's original deposit      ", SEED_DEPOSIT);

    // Alice and Bob deposited identically and held identical stakes through the
    // same loss. A correctly-priced exit splits the charge-off between them.
    // Here Alice exits whole and Bob carries all of it.
    assertGt(alicePayout, bobValue, "alice exited at a better price than bob is left with");
    assertLt(bobValue, SEED_DEPOSIT, "bob's stake absorbed the full charge-off");
  }

  // ---------------------------------------------------------------------------
  //  Helpers. All `// SIG?` -- adjust to the contest commit's actual interface.
  // ---------------------------------------------------------------------------

  function _deposit(address who, uint256 amount) internal {
    usdc.mint(who, amount);
    vm.startPrank(who);
    usdc.approve(address(vault), amount);
    vault.requestDeposit(amount, who, who); // SIG?
    vm.stopPrank();
    vm.prank(operator);
    vault.approveDeposit(who); // SIG?
    vm.prank(who);
    vault.deposit(amount, who); // SIG?
  }

  function _refreshNav() internal {
    vm.startPrank(operator);
    vault.startNavComputation(); // SIG?
    vault.computeNav(type(uint256).max); // SIG? -- batched; max processes all in one call
    vm.stopPrank();
  }

  function _singleton(uint64 id) internal pure returns (uint64[] memory arr) {
    arr = new uint64[](1);
    arr[0] = id;
  }
}
