# RateLimitedIsm: `verify()`'s only check is always-true, dead code

**Target**: `hyperlane-xyz/hyperlane-monorepo`, `solidity/contracts/isms/warp-route/RateLimitedIsm.sol`
**Reviewed commit**: `1a31d0425f060339e1c14980f552c976d408ec91` (2026-07-24)
**Severity (suggested)**: Medium as currently deployed / Critical if misconfigured — see "Real-world deployment check" below, read this before submitting.
**Status**: Verified locally with a passing Foundry PoC against the real, unmodified contracts (see `RateLimitedIsm.AuthBypass.PoC.t.sol`).

## Real-world deployment check (do this before submitting — updates the severity above)

Checked `hyperlane-xyz/hyperlane-registry` (the separate repo listing actual
mainnet deployments). Exactly two warp routes reference `rateLimitedIsm`
today, both on BSC (`deployments/warp_routes/PB/eni-deploy.yaml` and
`deployments/warp_routes/evENI/bsc-deploy.yaml`). Both configure it inside a
`staticAggregationIsm` with **`threshold` equal to the total module count
(3 of 3)**, alongside a `defaultFallbackRoutingIsm` (real per-domain
signature verification) and a `pausableIsm`:

```yaml
modules:
  - type: rateLimitedIsm              # the broken check described below
  - type: defaultFallbackRoutingIsm   # real verification
  - type: pausableIsm
threshold: 3
```

`AbstractAggregationIsm.verify()` requires `_threshold` to reach exactly 0,
decrementing once per module that has metadata supplied **and** returns
`true`. With `threshold == module count`, every module — including the real
`defaultFallbackRoutingIsm` — must independently verify; an attacker cannot
satisfy the aggregation by omitting metadata for the real ISM and only
supplying it for `rateLimitedIsm`, because that would leave `_threshold`
non-zero. **So for these two live deployments, the bug below is not
independently exploitable today** — the real ISM still gates security.

The bug itself is still real (confirmed by the PoC): `RateLimitedIsm`'s own
check contributes nothing, is dead code, and does not do what its author's
doc comment claims. The risk is latent/architectural, not "funds at risk
right now": nothing in the contract or the SDK config schema prevents a
*future* deployer from using it standalone (exactly as the project's own
`RateLimitedIsm.t.sol` does) or inside an aggregation with a lower
threshold that `rateLimitedIsm` alone (or with only non-verifying modules)
could satisfy — either of those would reproduce the full critical bypass
demonstrated in the PoC. Frame the submission accordingly: a real logic bug
in a shipped, SDK-exposed ISM type, currently mitigated by how two
deployers happened to compose it, not by anything the contract enforces.

## Summary

`RateLimitedIsm` is a first-class ISM type (`IsmType.RATE_LIMITED` in the SDK,
selectable standalone via `hyperlane warp` config, exactly like `MerkleRootMultisigIsm`
or `AggregationIsm`) meant to cap the token volume a warp route can process per
day. Its `verify()` performs **no check on message origin, sender, or any
validator/relayer attestation**. The only guard that looks like a security
check is:

```solidity
require(_isDelivered(_message.id()), "InvalidDeliveredMessage");
```

`_isDelivered(id)` calls `mailbox.delivered(id)`, which is
`deliveries[_id].blockNumber > 0`. But in `Mailbox.process()`
(`solidity/contracts/Mailbox.sol:202-246`):

```solidity
/// EFFECTS ///
deliveries[_id] = Delivery({processor: msg.sender, blockNumber: uint48(block.number)});
...
/// INTERACTIONS ///
require(ism.verify(_metadata, _message), "Mailbox: ISM verification failed");
```

`deliveries[_id]` — and therefore `delivered(_id)` — is set to true **before**
`ism.verify()` is ever called, for every message, on every ISM, regardless of
whether the message is legitimate. It's a checks-effects-interactions
safeguard against re-entrant re-processing, not a signal that verification
already happened. `RateLimitedIsm.verify()`'s only apparent authenticity
check is therefore **always true** and contributes nothing.

The consequence: since `Mailbox.process()` is a fully permissionless,
public function, anyone can call it with a **completely forged message**
(fake origin domain, sender field impersonating a real router — which is
public on-chain data, not a secret — and an arbitrary token amount/recipient
in the body) with `_metadata = ""` (no merkle proof, no validator signatures)
and have `RateLimitedIsm.verify()` return `true`, as long as the amount fits
in the current rate-limit bucket. The Mailbox then calls
`recipient.handle(origin, sender, body)` as if the message had been
legitimately validated — for a minting token router (`HypERC20`, `HypXERC20`,
etc.) this mints attacker-controlled amounts to an attacker-controlled
address, and repeats every refill window (`capacity / 1 day`), indefinitely.

This is exactly the configuration exercised by the project's own
`solidity/test/isms/RateLimitedIsm.t.sol`
(`testRecipient.setInterchainSecurityModule(address(rateLimitedIsm))`,
`localMailbox.process(bytes(""), ...)`) — i.e., using `RateLimitedIsm` as a
recipient's sole ISM, with empty metadata, is the pattern the authors
themselves test and the SDK exposes as a standalone `IsmType.RATE_LIMITED`
config option.

## The same pattern done correctly elsewhere (proof this is a real defect, not a design choice)

Hyperlane's own `TimelockRouter`
(`solidity/contracts/isms/routing/TimelockRouter.sol`) implements the exact
same "pre-verify on one message, then let `verify()` just check a stored
flag" pattern — but does it **correctly**, which shows `RateLimitedIsm` is
genuinely broken rather than following an accepted convention:

```solidity
// TimelockRouter: the flag (readyAt) is set only via Router._handle,
// which runs behind onlyMailbox + _mustHaveRemoteRouter(_origin) == _sender.
function _handle(uint32, bytes32, bytes calldata _message) internal override {
    bytes32 messageId = abi.decode(_message, (bytes32));
    require(readyAt[messageId] == 0, "...already preverified");
    readyAt[messageId] = uint48(block.timestamp) + timelockWindow;
}
// verify() then only checks the timelock elapsed — safe, because the flag
// could only be set by a validator-attested message from the enrolled router.
```

`TimelockRouter`'s "just check a flag" `verify()` is safe because the flag is
written **only** by a message that itself passed a real ISM (`Router.handle`
is `onlyMailbox` and requires `_mustHaveRemoteRouter(_origin) == _sender`).
`RateLimitedIsm` skips precisely this step: its flag (`delivered()`) is
written by the Mailbox for *every* message before *any* verification, so the
check authenticates nothing. Same pattern, one guarded by a real
router/validator check and one not — that asymmetry is the bug.

## Root cause

Author intent, per the doc comment on `verify()`:

```solidity
/**
 * Verify a message, rate limit, and increment the sender's limit.
 * @dev ensures that this gets called by the Mailbox
 */
```

The `_isDelivered` check appears meant to guarantee "this only runs as part
of a genuine Mailbox delivery," but `delivered()` becomes true as a
mechanical side effect of `process()` starting, not as a result of anything
having been verified. It does not, and cannot, distinguish a forged message
from a legitimate one.

## Impact

Any warp route (token bridge) that configures `RateLimitedIsm` as its ISM —
alone, or as one leg of an `AggregationIsm` whose threshold can be satisfied
without a real signature-checking ISM — accepts forged cross-chain messages.
For a minting/synthetic token router this is unauthenticated, unlimited
(bounded only by `refillRate * elapsed time`) token creation: a complete
break of the bridge's security model, no relayer/validator/private key
involved on the attacker's side.

As shown above, the two currently-deployed routes avoid this by requiring
`threshold == module count`, so this specific class of impact is not live
against them today. The impact statement above describes what happens
under the standalone/low-threshold configuration the contract itself does
nothing to prevent — call it out as a design/logic flaw with critical
*potential* impact rather than an active drain, unless further checking
turns up a deployment configured differently than the two found here.

## Proof of Concept

`RateLimitedIsm.AuthBypass.PoC.t.sol` (Foundry test, run against the
unmodified upstream contracts):

1. Deploys a real `Mailbox` (`TestMailbox`, a thin subclass that changes
   nothing about `process()`), a real `HypERC20` warp-route token, and a real
   `RateLimitedIsm`.
2. Configures the token's ISM to `RateLimitedIsm` alone — the same setup as
   the project's own unit test — and enrolls one legitimate remote router
   address (public data, as it would be in the Hyperlane registry).
3. An unrelated `attacker` address — holding no keys for the enrolled router,
   no validator role, nothing — calls the mailbox's public `process()` with
   a self-crafted message: origin/sender copied verbatim from the public
   enrolled-router record, recipient set to the attacker's own address,
   amount `500_000 ether`, and **empty ISM metadata**.
4. The call succeeds. `attacker`'s token balance goes from `0` to
   `500_000 ether`.
5. A second test shows the same attack repeating after `vm.warp(+1 days)`,
   demonstrating the bucket refill lets this run indefinitely rather than
   being a one-off.

### Running it

```bash
# from solidity/ inside a hyperlane-monorepo checkout at the commit above
forge test --match-contract RateLimitedIsm_AuthBypass_PoC -vvv
```

Both tests pass against the unmodified upstream code:

```
Ran 2 tests for test/isms/RateLimitedIsm.AuthBypass.PoC.t.sol:RateLimitedIsm_AuthBypass_PoC
[PASS] test_canRepeatUpToRefillRateForever() (gas: 241999)
[PASS] test_forgedMessageMintsTokensWithNoValidSignature() (gas: 171104)
```

The trace for the main test shows `RateLimitedIsm::verify()` returning
`true` off nothing but `TestMailbox::delivered() -> true` and the rate-limit
check — no signature, no merkle proof, no metadata — followed by
`HypERC20::handle()` minting to the attacker.

## Suggested fix

`_isDelivered` cannot be fixed in place — no ordering of Mailbox state
changes lets a "delivered" flag double as an authenticity check, since it is
set before the ISM even runs. Options for the Hyperlane team to consider:

1. **Turn `RateLimitedIsm` into a wrapping/combinator ISM** that takes an
   inner ISM address at construction and requires
   `innerIsm.verify(metadata, message) && rateLimitOk`, instead of trying to
   infer "already verified" from mailbox state it doesn't control.
2. If (1) is too large a change, at minimum remove the `_isDelivered` check
   (it provides no security value) and make extremely explicit — in the
   contract's NatSpec, and ideally enforced by the SDK/CLI config validator
   — that `RateLimitedIsm` must never be deployed as a recipient's sole ISM
   or as a satisfiable branch of an aggregation without a real
   signature-checking ISM also required.
3. Add a CI/config-time check to `typescript/sdk/src/ism/types.ts` (where
   `RateLimitedIsmConfigSchema` is defined) rejecting any `IsmConfig` tree
   where `RATE_LIMITED` is reachable without being AND-ed with a real
   verification ISM.

## Notes for submission

- KYC and the actual Immunefi submission are being handled by the user, not
  this tool — this write-up plus the passing PoC is the technical package.
- Registry checked on the date of this report; deployments can change.
  Re-check `hyperlane-registry` for new `rateLimitedIsm` usages (and their
  aggregation thresholds) right before submitting, in case a third
  deployment appeared with a lower threshold or standalone config — that
  would upgrade this from "logic bug" to "actively exploitable, funds at
  risk," which is a materially stronger submission.
- Don't lead with "critical, drains any bridge" — Immunefi triagers will
  check the registry too, and an overstated impact claim that doesn't
  survive that check costs credibility. Lead with the honest framing above:
  confirmed broken security check in a shipped ISM type + working PoC,
  currently not exploitable against the two live deployments because of how
  they're composed, but exploitable the moment it's used the way the
  project's own unit test uses it.
