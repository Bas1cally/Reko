# EVM multisig ISM accepts duplicate validators → silent quorum collapse (Solana rejects it)

**Target**: `hyperlane-xyz/hyperlane-monorepo`
- `solidity/contracts/libs/StaticAddressSetFactory.sol` (`StaticThresholdAddressSetFactory.deploy`)
- `solidity/contracts/libs/StaticWeightedValidatorSetFactory.sol` (`deploy` — no validation at all)
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

## The weighted variant is strictly worse

`AbstractStaticWeightedMultisigIsm.verify` uses the identical monotonic cursor,
but **sums weights** instead of counting slots:

```solidity
while (_validatorIndex < _validators.length &&
       _signer != _validators[_validatorIndex].signingAddress) { ++_validatorIndex; }
require(_validatorIndex < _validators.length, "Invalid signer");
_totalWeight += _validators[_validatorIndex].weight;   // <-- summed
++_validatorIndex;
```

So a duplicated entry doesn't merely fill an extra slot — it **adds that
validator's weight a second time**, directly multiplying their voting power.
`[{A, 50%}, {A, 50%}, {B, 50%}]` lets A alone reach a 100% threshold.

And `StaticWeightedValidatorSetFactory.deploy` performs **no validation
whatsoever** — not even the `0 < threshold <= length` guard the plain factory
has. Two consequences, both demonstrated in `WeightedMultisigDuplicate.PoC.t.sol`:

1. `test_duplicateValidator_weightDoubleCounted` — duplicate → one key reaches
   a 100% threshold (with `test_cleanSet_oneValidatorCannotReachFullWeight` as
   the control).
2. `test_factoryAcceptsWeightsExceedingTotalWeight` — validator weights are not
   required to sum to (or stay within) `TOTAL_WEIGHT = 1e10`. A set summing to
   `2 * TOTAL_WEIGHT` with a nominal "60%" threshold (`6e9`) is really a 33%
   threshold. Nothing rejects it.

```
[PASS] test_cleanSet_oneValidatorCannotReachFullWeight()
[PASS] test_duplicateValidator_weightDoubleCounted()
[PASS] test_factoryAcceptsWeightsExceedingTotalWeight()
```

## Cross-VM comparison: two of four implementations are unguarded

Hyperlane ships this ISM on four VMs. Two defend against duplicate validators,
two do not:

| Implementation | Validator set model | Duplicate possible? |
|---|---|---|
| **Sealevel / Solana** | array + explicit `HashSet` uniqueness check in `validate_config` | ❌ rejected at config time, with a comment naming the attack |
| **CosmWasm** | true set semantics — validators managed individually via `enroll_validator` / `unenroll_validator`; the SDK adapter computes `new Set(config.validators.map(v => v.address))` and diffs | ❌ structurally impossible |
| **EVM** | `abi.encode(address[], uint8)` blob baked into MetaProxy bytecode | ✅ **accepted at every layer** |
| **Starknet / Cairo** | `Map<u32, EthAddress>` written positionally by `set_validators` | ✅ **accepted — no dedup** |

This is what makes the finding more than a judgement call about what *ought*
to be validated: the team's own Solana implementation rejects it explicitly and
CosmWasm cannot represent it at all, so the guard is clearly considered
necessary. EVM and Starknet simply lack it. A split like this reads as a
systemic gap, not a deliberate design decision — the same logical flaw was
implemented twice without the guard and twice with it.

EVM carries the overwhelming majority of deployed value here: 983
`merkleRootMultisigIsm` + 981 `messageIdMultisigIsm` instances in the registry.

### Starknet specifics (`hyperlane-xyz/hyperlane-starknet`)

Both Cairo variants —
`cairo/crates/contracts/src/isms/multisig/messageid_multisig_ism.cairo` and
`merkleroot_multisig_ism.cairo` — use the identical monotonic cursor:

```cairo
let is_signer_in_list = loop {
    if (validator_index == validators.len()) { break false; }
    let signer = *validators.at(validator_index);
    if bool_is_eth_signature_valid(digest, signature, signer) { break true; }
    validator_index += 1;
};
assert(is_signer_in_list, Errors::NO_MATCH_FOR_SIGNATURE);
validator_index += 1;   // cursor never resets
```

`set_validators` only rejects an empty span and zero addresses — no uniqueness
check. The whole multisig directory contains no dedup logic (the only
"already"/"unique" wording is unrelated replay protection in
`validator_announce.cairo`).

**Aggravating factor on Starknet:** `set_validators` is invoked only from the
constructor and is not exposed in any public ABI impl (`IValidatorConfiguration`
exposes getters only). Validators are therefore **immutable after deployment**.
A duplicate baked in at deploy time cannot be corrected in place — it requires
redeploying the ISM and repointing every route, or a class upgrade via the
`UpgradeableComponent`. On EVM the storage variant can at least be fixed with
`setValidatorsAndThreshold`.

**Scope note:** `hyperlane-starknet` is a *separate repository* from
`hyperlane-monorepo`. Confirm it is in the Immunefi asset list before including
it in the submission; if it is not, report the EVM portion and mention Starknet
only as corroborating context.

## Could an attacker *engineer* the misconfiguration rather than wait for it?

The fair objection to a config-dependent finding is "that needs a mistake."
So: what would actually stop a duplicate from reaching production? Traced the
whole pipeline — **nothing does, at any layer:**

| Pipeline stage | Guard against duplicate validators |
|---|---|
| `hyperlane-registry` CI (`validate-file-data.js`, `validate-file-path.js`, `validate-svg.js`) | ❌ none — the string "validator" does not appear anywhere in the registry's scripts or `src/` |
| SDK `MultisigConfigSchema` | ❌ none — `z.object({ validators: z.array(ZHash), threshold: z.number() })`, no `.refine()` |
| SDK deploy path (`multisigConfigToIsmConfig`) | passes the config through unchanged (`.map(v => v.address)`) — introduces nothing, filters nothing |
| EVM `StaticThresholdAddressSetFactory.deploy` | ❌ only `0 < threshold <= length` |
| EVM `StaticWeightedValidatorSetFactory.deploy` | ❌ **no validation at all** |
| EVM `AbstractStorageMultisigIsm.setValidatorsAndThreshold` | ❌ only `0 < threshold <= length` |
| Sealevel `validate_config` | ✅ rejects |

No SDK code path *creates* duplicates on its own (`collectValidators` returns a
`Set`, and it is only used for checking/reporting) — so the duplicate has to
enter via the source config. But once it is in the config, **the only thing
between it and a silently halved quorum is a human reading a YAML diff full of
similar-looking hex addresses.**

Realistic threat model, stated honestly: a validator operator who wants
unilateral signing power submits a rotation PR that leaves their address listed
twice; or a duplicate slips in while merging/templating chain configs. Both
produce a set that passes every automated check, deploys cleanly, and reports
the nominal M-of-N everywhere.

**Do not oversell this.** It still depends on a review failure — that is social
engineering / process, not a purely technical exploit, and many Immunefi
programs treat such findings as out of scope or Low. The defensible claim is
narrow and true: *the EVM pipeline has no automated defense at any layer, and
half of the team's own implementations (Solana, CosmWasm) do defend against it,
while EVM and Starknet do not.*

### Ruled out: "just simulate the admin with a script"

Checked, because it is the obvious next thought — it does not work, and the
reason is worth stating in the report so a triager doesn't have to ask:

- Every path that could point a live route at a duplicate-bearing ISM is
  cryptographically gated, not UI-gated:
  `MailboxClient.setInterchainSecurityModule` → `onlyOwner`,
  `DomainRoutingIsm.set` / `.remove` → `onlyOwner`,
  `AbstractStorageMultisigIsm.setValidatorsAndThreshold` → `onlyOwner`.
  `onlyOwner` compares `msg.sender` against stored state; `msg.sender` is
  derived from an ECDSA signature at the protocol level. A script cannot
  forge it — that is not an application-layer check to bypass.

- **The decisive point: if you could act as the owner, you would not need this
  bug.** With owner access you would simply call
  `setInterchainSecurityModule(noopIsm)` or install a single-key multisig. The
  duplicate trick is strictly *weaker* than the access it would require, so
  admin-impersonation is self-defeating as a delivery vector. Anything
  requiring owner keys is a key-compromise scenario, which every Immunefi
  program lists as out of scope.

- **What genuinely is permissionless — and why it is still safe:**
  `StaticThresholdAddressSetFactory.deploy()` is `public`, so anyone may deploy
  an ISM with a duplicated validator set. That is harmless by construction. The
  CREATE2 salt is `keccak256(abi.encode(values, threshold))` and the metadata is
  baked into the MetaProxy bytecode, so the address is a pure function of its
  contents; the factory reuses an existing deployment (`if (!Address.isContract(_set))`).
  Front-running a legitimate deployment therefore deploys the *identical*
  contract — no squatting, no substitution. A maliciously deployed weak ISM
  just sits there, inert, until an owner chooses to point at it.

Net: the attacker can freely *create* the weak ISM; they cannot make anyone
*use* it. The gap is and remains "a duplicate reaches the owner's config, and
nothing automated flags it."

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
