// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity ^0.8.13;

import "forge-std/Test.sol";
import {TransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

import {TypeCasts} from "contracts/libs/TypeCasts.sol";
import {MockMailbox} from "contracts/mock/MockMailbox.sol";
import {ERC20Test} from "contracts/test/ERC20Test.sol";
import {CrossCollateralRouter} from "contracts/token/CrossCollateralRouter.sol";
import {HypERC20Collateral} from "contracts/token/HypERC20Collateral.sol";

/**
 * Thief invariant: no value creation across a same-chain cross-token transfer.
 *
 * Two CrossCollateralRouters on the same local domain, different tokens with
 * different scales. Alice deposits `amount` of token A; Bob receives token B
 * from the target router. The canonical (scale-normalized) value delivered to
 * Bob must never exceed the canonical value charged to Alice. If the fuzzer
 * finds any (amount, scaleA, scaleB) where Bob's canonical > Alice's canonical,
 * that's minting value out of rounding — a real economic bug.
 *
 * Canonical value := local * scaleNumerator / scaleDenominator  (the units the
 * cross-collateral message travels in). We compare in the shared canonical unit.
 */
contract CCR_Conservation_Fuzz is Test {
    using TypeCasts for address;

    uint32 constant LOCAL = 1;
    address constant PROXY_ADMIN = address(0xADAD);
    address constant ALICE = address(0xA11CE);
    address constant BOB = address(0xB0B);

    MockMailbox mailbox;

    function setUp() public {
        mailbox = new MockMailbox(LOCAL);
    }

    function _deploy(
        address token,
        uint256 num,
        uint256 den
    ) internal returns (CrossCollateralRouter r) {
        CrossCollateralRouter impl = new CrossCollateralRouter(
            token,
            num,
            den,
            address(mailbox)
        );
        TransparentUpgradeableProxy proxy = new TransparentUpgradeableProxy(
            address(impl),
            PROXY_ADMIN,
            abi.encodeWithSelector(
                HypERC20Collateral.initialize.selector,
                address(0),
                address(0),
                address(this)
            )
        );
        r = CrossCollateralRouter(address(proxy));
    }

    function _enrollLocal(
        CrossCollateralRouter r,
        CrossCollateralRouter peer
    ) internal {
        uint32[] memory d = new uint32[](1);
        bytes32[] memory a = new bytes32[](1);
        d[0] = LOCAL;
        a[0] = address(peer).addressToBytes32();
        r.enrollCrossCollateralRouters(d, a);
    }

    function testFuzz_noValueCreation_sameChainCrossToken(
        uint256 amount,
        uint8 decA,
        uint8 decB,
        uint64 numA,
        uint64 numB
    ) public {
        // Bound decimals and scales to realistic ranges.
        decA = uint8(bound(decA, 2, 24));
        decB = uint8(bound(decB, 2, 24));
        numA = uint64(bound(numA, 1, 1e18));
        numB = uint64(bound(numB, 1, 1e18));
        // keep amount in a sane range so mulDiv doesn't trivially overflow
        amount = bound(amount, 0, 1e30);

        ERC20Test tokenA = new ERC20Test("A", "A", 0, decA);
        ERC20Test tokenB = new ERC20Test("B", "B", 0, decB);

        // scaleDen = 1 for both: canonical = local * num
        CrossCollateralRouter rA = _deploy(address(tokenA), numA, 1);
        CrossCollateralRouter rB = _deploy(address(tokenB), numB, 1);

        // No fees: isolate the scale/rounding math.
        _enrollLocal(rA, rB);
        _enrollLocal(rB, rA);

        // Fund target router B with plenty of collateral and Alice with token A.
        tokenB.mintTo(address(rB), type(uint128).max);
        tokenA.mintTo(ALICE, amount);
        vm.prank(ALICE);
        tokenA.approve(address(rA), type(uint256).max);

        uint256 bobBefore = tokenB.balanceOf(BOB);

        // Same-chain cross-token transfer: Alice -> Bob, A-router -> B-router.
        vm.prank(ALICE);
        try
            rA.transferRemoteTo(
                LOCAL,
                BOB.addressToBytes32(),
                amount,
                address(rB).addressToBytes32()
            )
        {
            uint256 bobGot = tokenB.balanceOf(BOB) - bobBefore;

            // Canonical value charged to Alice vs delivered to Bob.
            // canonical = local * num  (den == 1)
            uint256 canonicalIn = amount * uint256(numA);
            uint256 canonicalOut = bobGot * uint256(numB);

            assertLe(
                canonicalOut,
                canonicalIn,
                "VALUE CREATED: recipient canonical > sender canonical"
            );
        } catch {
            // reverts (overflow, dust-to-zero, etc.) are fine — no value moved
        }
    }
}
