# EVM multisig ISM accepts duplicate validators → silent quorum collapse (Solana rejects it)

**Target**: `hyperlane-xyz/hyperlane-monorepo`
- `solidity/contracts/libs/StaticAddressSetFactory.sol` (`StaticThresholdAddressSetFactory.deploy`)
- `solidity/contracts/isms/multisig/StorageMultisigIsm.sol` (`AbstractStorageMultisigIsm.setValidatorsAndThreshold`)
- `typescript/sdk/src/ism/types.ts` (`MultisigConfigSchema`)

**Reviewed commit**: `1a31d0425f060339e1c14980f552c976d408ec91` (2026-07-24)
**Severity (honest)**: **Low / hardening.** Requires a deployer misconfiguration; **no live deployment is affected** (verified — see below). Submit as a defense-in-depth / consistency finding with a concrete PoC, not as a live-funds-at-risk report.
**Status**: Demonstrated with a passing Foundry PoC **including a negative control** (`MultisigDuplicateValidator.PoC.t.sol`, 2/2 passing).

## What it is

`AbstractMultisigIsm.verify` walks the validator array with a single
monotonically increasing cursor (a two-pointer scan, for gas):

```solidity
uint256 _validatorIndex = 0;
for (uint256 i = 0; i < _threshold; ++i) {
    address _signer = ECDSA.recover(_digest, signatureAt(_metadata, i));
    while (_validatorIndex < _validatorCount && _signer != _validators[_validatorIndex]) {
        ++_validatorIndex;
    }
    require(_validatorIndex < _validatorCount, "!threshold");
    ++_validatorIndex;
}
```

The scan guarantees each signature consumes a *distinct array slot* — but not a
distinct *key*. If the same address occupies two slots, one validator's single
signature, repeated in the metadata, satisfies two slots.

With `validators = [A, A, B]`, `threshold = 2`:

| step | signature | cursor | matches | result |
|---|---|---|---|---|
| i=0 | A | 0 | `validators[0] == A` | cursor → 1 |
| i=1 | **same A sig** | 1 | `validators[1] == A` | cursor → 2 |

→ `verify` returns `true`. A nominal **2-of-3 is satisfied by one key**.

Note the attacker doesn't even need two distinct signatures: `signatureAt`
reads independent 65-byte windows and each is recovered separately, so the
identical signature bytes pasted twice work.

## Why this is a defect and not a design choice

**Hyperlane enforces exactly this check in their own Solana implementation.**
`rust/sealevel/programs/ism/composite-ism/src/processor.rs`, `validate_config`:

```rust
// Reject duplicate validators: with [A, A, B] and threshold 2, the
// ascending-index scan in verify_node would accept two sigs from A as
// quorum, collapsing "2-of-3" into "1-of-2 unique". Matches the check
// in the standalone multisig-ism-message-id program.
let mut seen = HashSet::with_capacity(validators.len());
for v in validators {
    if !seen.insert(v) {
        return Err(Error::InvalidConfig.into());
    }
}
```

Their own code documents the attack and guards it — on Sealevel. The EVM path
has no equivalent guard at **any** layer:

| Layer | Check performed | Duplicate rejected? |
|---|---|---|
| Sealevel `validate_config` | HashSet uniqueness | ✅ yes |
| Sealevel standalone `multisig-ism-message-id` | (same, per the comment) | ✅ yes |
| EVM `StaticThresholdAddressSetFactory.deploy` | `0 < threshold <= values.length` | ❌ **no** |
| EVM `AbstractStorageMultisigIsm.setValidatorsAndThreshold` | `0 < threshold <= validators.length` | ❌ **no** |
| SDK `MultisigConfigSchema` | `z.object({ validators: z.array(ZHash), threshold: z.number() })` | ❌ **no** |

The static factory is the dominant deployment path: the registry shows 983
`merkleRootMultisigIsm` and 981 `messageIdMultisigIsm` instances.

## Impact

A duplicate entry silently reduces the real security threshold while every
surface — the config file, the registry, the on-chain `validatorsAndThreshold()`
getter — still reports the nominal M-of-N. There is no error, no event, no
signal. A "3-of-5" containing one duplicate is really 2 unique keys; with two
duplicates, 1.

Plausible ways this happens in practice: validator rotation (new key added
before the old entry is removed), merging or templating chain configs, the same
operator listed under two entries, or plain copy-paste. None of these produce a
warning today.

This is **not** directly attacker-triggerable: it needs the misconfiguration
first. That is why the honest severity is Low/hardening.

## Live exposure: none (verified)

Scanned the entire `hyperlane-xyz/hyperlane-registry` — **1,964 validator sets,
3,940 addresses across 1,264 files** (all warp routes and chain default ISM
configs): **zero duplicates**. No deployment is currently degraded. The gap is
latent, held closed only by operator discipline, not by code.

Re-run before submitting (registry changes):

```bash
git clone --depth 1 https://github.com/hyperlane-xyz/hyperlane-registry
# then the duplicate scan over `validators:` blocks (see report notes)
```

## Proof of Concept

`MultisigDuplicateValidator.PoC.t.sol` — real `StaticMessageIdMultisigIsmFactory`,
unmodified contracts, with a negative control so the result isn't a test artifact:

```
[PASS] test_cleanSet_singleValidatorCannotReachQuorum()   (control: [A,B,C] thr=2 → reverts "!threshold")
[PASS] test_duplicateValidator_oneKeySatisfiesQuorum()    (bug:     [A,A,B] thr=2 → verify() == true)
```

Run from `solidity/` in a monorepo checkout at the commit above:

```bash
forge test --match-contract MultisigDuplicateValidator_PoC -vv
```

The PoC also asserts the factory genuinely persisted the duplicate set on-chain
(`got[0] == got[1]`), so the collapse is a property of deployed state, not of
the test harness.

## Suggested fix

Mirror the Sealevel guard on the EVM path. The cleanest option also solves a
second problem the codebase already wants solved — `StaticAddressSetFactory`
carries the comment *"Consider sorting addresses to ensure contract reuse"*:

**Require strictly ascending validator addresses** in
`StaticThresholdAddressSetFactory.deploy` and
`AbstractStorageMultisigIsm.setValidatorsAndThreshold`:

```solidity
for (uint256 i = 1; i < _values.length; ++i) {
    require(_values[i - 1] < _values[i], "validators must be sorted, unique");
}
```

That is O(n) (vs. O(n²) for a nested-loop dedup), rejects duplicates by
construction, and canonicalizes the CREATE2 salt so identical sets reuse the
same deployment — the reuse benefit the existing comment asks for.

Additionally, add a `.refine()` to `MultisigConfigSchema` in the SDK so the
CLI rejects duplicate sets before any transaction is signed.

**Backwards compatibility caveat worth flagging in the report:** enforcing
sorted order changes the CREATE2 addresses for unsorted-but-valid sets, so it
must be gated on new factory deployments, not retrofitted onto the existing
factory. A plain uniqueness check (nested loop) avoids that at the cost of gas
and keeps existing addresses stable — offer both and let the team choose.

## Notes for submission

- Lead with the cross-implementation inconsistency and their own Sealevel
  comment; that is what makes this a defect rather than an opinion.
- State plainly, up front, that no live deployment is affected and that
  exploitation requires a misconfiguration. Many Immunefi programs exclude
  admin-misconfiguration issues outright — expect Low or Informational, and
  don't claim economic damage.
- The negative control in the PoC matters: it pre-empts the "your test just
  passes two signatures, of course it works" dismissal.
