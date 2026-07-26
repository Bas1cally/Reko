# Deep manual review — coverage log

Reviewed commit: `1a31d0425f060339e1c14980f552c976d408ec91` (2026-07-24),
`hyperlane-xyz/hyperlane-monorepo`, `solidity/contracts`. This log records
what was manually read and reasoned through, so the bounty submission is
backed by an auditable trail rather than a single lucky grep. Honest bottom
line: **one real defect found (`RateLimitedIsm`, see its folder); everything
else below was examined and judged sound** within its trust model.

## Reviewed and judged sound

| Area | Files | Why it holds |
|---|---|---|
| Multisig verification | `AbstractMultisigIsm`, `AbstractWeightedMultisigIsm`, `AbstractMerkleRootMultisigIsm` | Two-pointer signer loop uses a monotonic validator index (no double-count), final threshold/weight check is correct; digest binds origin + merkle-tree hook. |
| Aggregation | `AbstractAggregationIsm` | `verify` requires `_threshold` to reach exactly 0; a branch can only be skipped by omitting its metadata, which cannot reduce the required count below threshold. This is what mitigates the RateLimitedIsm bug in the two live deployments. |
| CCTP bridge | `TokenBridgeCctpBase`, `TokenBridgeCctpV1/V2`, `CctpMessageV1/V2` | Real mint is gated by Circle's attested `messageTransmitter.receiveMessage`; Hyperlane cross-checks burn sender/amount/mint-recipient against the CCTP message; replay handled by Circle nonces; `_postDispatch` explicitly blocks the self-sender backrun. |
| Interchain accounts | `InterchainAccountRouter`, `AbstractInterchainAccountRouter`, `OwnableMulticall` | ICA address = f(origin, owner, sender, ism, salt); the non-forgeable parts (origin, sender) come from the verified delivery, so a forged owner/ism yields a *different* unfunded ICA. Isolation holds. |
| Commit-reveal ICA | `OwnableMulticall.revealAndExecute`, `CommitmentReadIsm` | Commitment is content-addressed (`keccak256(salt‖calls)`), so an attacker cannot inject their own calls; a mismatched `_ica` in metadata just fails the per-ICA `commitments[...]` check. Permissionless reveal only runs the owner's own committed calls. |
| Timelock ISM | `TimelockRouter` | Correct version of the "pre-verify then check a flag" pattern: the flag is written only behind `onlyMailbox` + `_mustHaveRemoteRouter == _sender`. Directly contrasts the RateLimitedIsm defect. |
| OP/Arb native ISMs | `AbstractMessageIdAuthorizedIsm`, `ArbL2ToL1Ism` | Verification bit set only via `preVerifyMessage` behind `_isAuthorized` (cross-domain sender == authorized hook); the fallback outbox call is gated by Arbitrum's own merkle proof; a wrong `to` reverts rather than spoofs. |
| Offchain fee quotes | `AbstractOffchainQuoter`, `OffchainQuotedLinearFee` | EIP-712 digest binds `chainid` + `address(this)` (no cross-chain/contract replay); transient-quote front-running risk is already documented in-code with a mitigation. |
| Collateral rebalancing | `MovableCollateralRouter` | `rebalance` is `onlyRebalancer` + `onlyAllowedBridge`; recipient is owner-set or the enrolled router. Sound within its trusted-rebalancer model. |
| Core dispatch/delivery | `Mailbox.process`, `Router.handle` | CEI ordering is correct; `delivered()` is replay protection, not authentication — which is exactly what `RateLimitedIsm` misuses. |
| Static analysis | full Slither pass, all 389 in-scope contracts, detectors unfiltered | Only 2 results, both `shadowing-abstract` (Medium) on by-design OZ-upgradeable storage gaps. No automatic High/Critical. |

## Examined more briefly / trusted by model

- `AbstractPredicateWrapper` (compliance attestation layer) — transient
  reentrancy guard + pending-attestation handshake are coherent; it is a
  policy gate, not fund custody.
- `RateLimited` library — the `_validateAndConsumeFilledLevel` is internal
  (the public variant that once allowed a DoS was already removed in #6355).

## Not yet reviewed (candidate next steps, honest gaps)

- `CheckpointFraudProofs` / `AttributeCheckpointFraud` (fraud-proof math).
- `MerkleLib.branchRoot` internals (proof reconstruction edge cases).
- The Rust validator/relayer agents and offchain CCIP-read servers — these
  are in the Immunefi scope too and are where "the ISM says verified" trust
  actually originates; a bug there can be as severe as a contract bug.
- Cross-VM (Tron/Starknet) specific overrides.

## Attacker-mindset pass ("think like a thief", not "is this function correct")

Second pass framed around how to actually extract funds, not intended-model
correctness. Targets and verdicts:

| Thief angle | Where | Verdict |
|---|---|---|
| ERC4626 share-price / exchange-rate manipulation, out-of-order rate updates | `HypERC4626`, `HypERC4626Collateral` | Accounting is share-based; rate updates are monotonic by `rateUpdateNonce` and written only by the enrolled collateral router. Inflating the synthetic rate hurts the user, never lets you redeem more real assets. |
| Cross-decimal / scale extraction | `TokenRouter._outbound/_inboundAmount`, `CrossCollateralRouter` | Both directions round down (protocol-favor); scale is owner-config, not attacker-influenced. |
| Stuck-funds sweep, value-accounting in the command router | `QuotedCalls` | Universal-Router pattern: caller-scoped, `nonReentrant`, holds nothing between txs. Idle funds are sweepable-by-design (don't park funds in it) — accepted, not a protocol theft. |
| Native-value reentrancy | all `.call{value}` / `sendValue` sites | Sends go to `msg.sender`/message recipient; no cross-user custody in the value paths. |
| Permissionless approve / fee-hook approval abuse | `AbstractInterchainAccountRouter.approveFeeTokenForHook`, TokenRouter fee hook | Router holds no funds (ICAs do); approval targets an empty balance. |
| Rate-limit bucket griefing (drain the limit to DoS legit transfers) | `RateLimitedIsm` in the live 3-of-3 aggregation | The `delivered()` gate ironically blocks pre-consumption; `validateMessageOnce` blocks double-consume. No free DoS. |
| Amount-routing: structure theft as sub-threshold amounts to hit the weak ISM | `AmountRoutingIsm` + the 2 live `oUSDT` routes | Live "lower" ISM (< 250k USDT) is still the real default multisig, wrapped in a 2-of-2 aggregation with pausable. The "weak" path isn't weak. |
| Low-threshold aggregations as OR-bypass | registry scan, all 231 warp routes | Every `threshold: 1/2` aggregation found is the standard "merkleRoot OR messageId multisig" (both real 3-of-5) or N-of-N with pausable. None reduces to a forgeable branch. |

Registry composition scan (231 deployed warp routes): ISM usage is dominated
by real multisig/aggregation (1113 aggregation, 983 merkleRoot, 981
messageId). The 4 `rateLimitedIsm` occurrences are all AND-composed
(threshold == module count) with a real verifying ISM; the 8 `trustedRelayerIsm`
uses are a by-design trusted-relayer choice; no route was found where the
RateLimitedIsm defect is independently reachable.

## What this means for a submission

The RateLimitedIsm finding is real and PoC-backed, but currently mitigated
by deployment composition. It is worth submitting as a logic/defense-in-depth
bug with critical *potential* impact, framed honestly. No second independent
vulnerability was found in this pass — stating that plainly is the point of
"no fantasies."
