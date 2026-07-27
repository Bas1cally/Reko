// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.33;

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
