// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.33;

// Drop this file into `test/` in a local clone of sherlock-scoping/tare-io__tare-contracts
// and run:  forge test --match-contract RescuableDrainsLoanCash -vvvv
//
// Demonstrates: Rescuable.rescueERC20Tokens (inherited unmodified by Loans) can pull the
// entire operating currency out of Loans, desyncing every loan's ACC_CASH ledger entry
// from the contract's real token balance. The ledger keeps asserting funds are present;
// the real ERC20 transfer that should pay them out reverts.

import {Test} from "forge-std/Test.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

import {Loans} from "contracts/Loans.sol";
import {LoansNFT} from "contracts/LoansNFT.sol";
import {Roles} from "contracts/interfaces/ILoans.sol";
import {ACC_CASH, ACC_BORROWER_PAYMENT_CLEARING} from "contracts/interfaces/Accounts.sol";

contract MockUSDC is ERC20 {
  constructor() ERC20("Mock USDC", "USDC") {}

  function mint(address to, uint256 amount) external {
    _mint(to, amount);
  }
}

contract RescuableDrainsLoanCash is Test {
  MockUSDC internal usdc;
  Loans internal loans;
  LoansNFT internal loansNFT;

  address internal guardian = makeAddr("guardian");
  address internal recovery = makeAddr("recovery"); // guardian's own recovery address
  address internal originator = makeAddr("originator");
  address internal investor = makeAddr("investor");
  address internal borrower = makeAddr("borrower");
  address internal servicer = makeAddr("servicer");

  uint64 internal loanId;
  uint128 internal constant PRINCIPAL = 1_000_000e6; // 1,000,000 USDC, 6 decimals
  uint128 internal constant REPAYMENT = 400_000e6; // 400,000 USDC repaid by borrower

  function setUp() public {
    usdc = new MockUSDC();

    // 1. Deploy Loans. `guardian` receives GUARDIAN_ROLE via _initGuardian in the constructor chain.
    loans = new Loans(IERC20(address(usdc)), guardian, recovery);

    // 2. Deploy LoansNFT pointing at Loans, then wire it up (admin/guardian-only, one-shot).
    loansNFT = new LoansNFT(address(loans), "Tare Loans", "https://tare.example/loans/");
    vm.prank(guardian);
    loans.setLoansNFT(address(loansNFT));

    // 3. Guardian approves the originator (the only globally-gated registration in this flow).
    vm.prank(guardian);
    loans.approveOriginator(originator);

    // 4. Originator registers borrower/investor/servicer under its own address book
    //    (permissionless self-registration, exactly as LoansAuth intends).
    vm.startPrank(originator);
    loans.registerAddress(Roles.Borrower, borrower);
    loans.registerAddress(Roles.Investor, investor);
    loans.registerAddress(Roles.Servicer, servicer);
    vm.stopPrank();

    // 5. Originate, fund, and disburse a loan so real USDC flows through Loans legitimately.
    vm.prank(originator);
    loanId = loans.create(borrower, investor, servicer, originator, int128(PRINCIPAL), uint48(block.timestamp));

    usdc.mint(investor, PRINCIPAL);
    vm.startPrank(investor);
    usdc.approve(address(loans), PRINCIPAL);
    loans.fund(loanId, int128(PRINCIPAL), uint48(block.timestamp), "fund");
    vm.stopPrank();

    vm.prank(originator);
    loans.disburse(
      loanId,
      int128(PRINCIPAL), // netDisbursedAmount
      0, // originationFee
      uint48(block.timestamp), // originationDate
      uint48(block.timestamp + 30 days), // nextDueDate
      uint48(block.timestamp + 365 days), // maturityDate
      500, // interestRate (arbitrary)
      0, // expectedMonthlyPayment
      uint48(block.timestamp),
      "disburse"
    );
    // At this point PRINCIPAL has left Loans to `borrower`; Loans' USDC balance and this
    // loan's ACC_CASH are both back to 0 -- the disbursement leg is fully paired.

    // 6. Borrower repays part of the loan. This is real, legitimate custody: Loans now
    //    holds REPAYMENT in USDC, and the loan's ACC_CASH ledger entry says exactly that.
    usdc.mint(borrower, REPAYMENT);
    vm.startPrank(borrower);
    usdc.approve(address(loans), REPAYMENT);
    loans.pay(loanId, int128(REPAYMENT), uint48(block.timestamp), "repayment");
    vm.stopPrank();
  }

  function test_ledgerAndRealBalanceAgreeBeforeRescue() public view {
    assertEq(usdc.balanceOf(address(loans)), REPAYMENT, "real balance should equal the repayment");
    assertEq(
      loans.getLoanAccountBalance(loanId, ACC_CASH),
      int128(REPAYMENT),
      "ledger CASH should equal the repayment"
    );
  }

  /// @notice The actual finding: guardian sweeps the operating currency via the
  /// "accidental token" rescue path, and the ledger has no idea.
  function test_rescueERC20Tokens_drainsLegitimateLoanFunds() public {
    // Precondition: real custody and the ledger agree (proven above).
    assertEq(usdc.balanceOf(address(loans)), REPAYMENT);

    // Guardian calls the documented "accidentally sent tokens" rescue path --
    // but points it at the protocol's own operating currency.
    vm.prank(guardian);
    uint256 rescued = loans.rescueERC20Tokens(address(usdc), type(uint256).max);

    assertEq(rescued, REPAYMENT, "guardian rescues the entire real balance");
    assertEq(usdc.balanceOf(address(loans)), 0, "Loans now holds zero real USDC");
    assertEq(usdc.balanceOf(recovery), REPAYMENT, "swept to the recovery address");

    // The ledger was never touched -- it still asserts the money is there.
    assertEq(
      loans.getLoanAccountBalance(loanId, ACC_CASH),
      int128(REPAYMENT),
      "ledger CASH is unchanged: this is the desync"
    );

    // Prove the bricking: a legitimate servicer action that the LEDGER considers fully
    // valid (there IS enough ACC_CASH on paper) reverts because the real ERC20 transfer
    // can no longer be backed. No amount of on-chain accounting can recover this --
    // the money is gone and every future withdrawal on this loan fails the same way.
    vm.prank(servicer);
    vm.expectRevert(); // reverts inside the ERC20 transfer, not any Loans-level check
    loans.refundBorrower(
      loanId,
      ACC_BORROWER_PAYMENT_CLEARING,
      int128(REPAYMENT),
      uint48(block.timestamp),
      0,
      "attempted-refund-after-rescue"
    );
  }
}
