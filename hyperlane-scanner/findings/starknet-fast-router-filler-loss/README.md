# Starknet FastTokenRouter: every fast-transfer settlement reverts permanently, stranding the liquidity provider's capital

**Target**: `hyperlane-xyz/hyperlane-starknet`
**Component**: `cairo/crates/token/src/components/fast_token_router.cairo`
(reached via `extensions/fast_hyp_erc20.cairo`, `extensions/fast_hyp_erc20_collateral.cairo`)
**Reviewed at**: HEAD of `main` at review time — shallow clone, so **re-pin to an exact commit before submitting**
**Requires misconfiguration, privileged access, or an attacker?** **No.** Broken on the first normal use of the feature.

---

## Summary

`FastTokenRouterComponent` implements fast transfers: a liquidity provider (the
*filler*) fronts tokens to the recipient immediately, and is reimbursed later
when the real Hyperlane settlement message arrives.

Three defects on the settlement path — all within ~20 lines — make that
reimbursement impossible:

| # | Defect | Location | Effect |
|---|---|---|---|
| **A** | Metadata `Bytes` declared as **4** bytes instead of **64** | `_fast_transfer_from_sender` | `concat` truncates the payload to 4 bytes; fee and transfer-id are silently dropped |
| **B** | Second `read_u256` at byte offset **2** instead of **32** | `_get_token_recipient` | Would read overlapping bytes even if A were fixed |
| **C** | Returns the storage **key** instead of reading the filler map | `_get_token_recipient` | Pays a keccak hash cast to an address instead of the filler |

At runtime **A** fires first and panics, so 100% of fast-transfer settlement
messages revert — deterministically and permanently. **B** and **C** are latent
behind it and become the active failure once A is fixed.

`fill_fast_transfer` has already moved the filler's tokens out and paid the
recipient *before* the settlement arrives, so the settlement is the filler's
only reimbursement path — and it can never execute.

The component has **zero test coverage**, which is why none of the three was
caught.

---

## Background: the intended flow

```cairo
// Origin chain — user initiates
fast_transfer_remote(destination, recipient, amount, fast_fee, value)
  └─ _fast_transfer_from_sender(amount, fast_fee, fast_transfer_id)
       ├─ pulls `amount` from the sender
       └─ returns metadata = (fast_fee, fast_transfer_id)      // ← defect A

// Destination chain — filler fronts liquidity immediately
fill_fast_transfer(recipient, amount, fast_fee, origin, fast_transfer_id)
  ├─ key = _get_fast_transfers_key(origin, id, amount, fee, recipient)
  ├─ filled_fast_transfers.write(key, caller)                   // filler recorded
  ├─ pulls (amount - fast_fee) from the filler
  └─ pays (amount - fast_fee) to the recipient

// Destination chain — settlement message arrives, should repay the filler
Mailbox::process → RouterComponent::handle → _handle → _transfer_to
  └─ _get_token_recipient(recipient, amount, origin, metadata)  // ← defects B, C
       └─ should return the filler; pays them `amount`
```

The filler's capital is at risk for exactly the window between
`fill_fast_transfer` and settlement. If settlement never executes, that capital
is simply gone.

---

## Defect A — metadata length is a limb count, not a byte length

```cairo
// _fast_transfer_from_sender
BytesTrait::new(
    4, array![fast_fee.low, fast_fee.high, fast_transfer_id.low, fast_transfer_id.high],
)
```

In `alexandria_bytes` 0.4.0, `Bytes { size, data }` stores `size` as a **byte**
length while `data` holds 16-byte limbs (`BYTES_PER_ELEMENT = 16`):

```cairo
fn new(size: usize, data: Array<u128>) -> Bytes {
    let min_len = (size + BYTES_PER_ELEMENT - 1) / BYTES_PER_ELEMENT;
    assert(data.len() >= min_len, 'Insufficient data');   // guards too LITTLE data only
    Bytes { size, data }
}
```

Two `u256` values are **64 bytes**, so the size must be `64`. The literal `4`
matches the *number of limbs*, not the byte length.

The constructor cannot catch this: its only assert rejects *insufficient* data
(`4 >= 1` passes) and never checks for excess. The `Bytes` is created claiming
4 bytes while carrying 64 bytes of payload.

The damage is done by `concat`, which copies exactly `other.size` bytes:

```cairo
fn concat(ref self: Bytes, other: @Bytes) {
    let mut sub_bytes_full_array_len = *other.size / BYTES_PER_ELEMENT;   // 4/16 = 0
    ...
    let sub_bytes_last_element_size = *other.size % BYTES_PER_ELEMENT;    // 4
```

So `TokenMessageTrait::format` appends **4 of the 64 bytes**. `fast_fee` and
`fast_transfer_id` are truncated away before the message ever leaves the origin
chain.

---

## Defect B — read offset is an element index, not a byte offset

```cairo
// _get_token_recipient
let (_, fast_fee)         = metadata.read_u256(0);
let (_, fast_transfer_id) = metadata.read_u256(2);   // should be 32
```

`read_u256` takes byte offsets. The repository's own working code is the
reference — `token_message.cairo` reads consecutive `u256` fields at **0, 32,
64**:

```cairo
fn recipient(self: @Bytes) -> u256 { let (_, r) = self.read_u256(0);  r }
fn amount(self: @Bytes)    -> u256 { let (_, a) = self.read_u256(32); a }
fn metadata(self: @Bytes)  -> Bytes { let (_, b) = self.read_bytes(64, self.size() - 64); b }
```

Offset `2` reads bytes 2..34 — overlapping the first value by 30 bytes and
straddling into the second. Same limb-index-vs-byte-offset confusion as defect A.

---

## Defect C — the filler map is written but never read

```cairo
fn _get_token_recipient(...) -> u256 {
    if metadata.size() == 0 { return recipient; }

    let (_, fast_fee)         = metadata.read_u256(0);
    let (_, fast_transfer_id) = metadata.read_u256(2);

    let filler_address = self
        ._get_fast_transfers_key(origin, fast_transfer_id, amount, fast_fee, recipient);
    if filler_address != 0 {
        return filler_address;      // ← returns the KEY, not the stored filler
    }
    recipient
}
```

`_get_fast_transfers_key` returns `data.keccak()` — the `u256` used as the
**storage map key**. The variable is named `filler_address`, but no map read
occurs. The missing line:

```cairo
let key = self._get_fast_transfers_key(origin, fast_transfer_id, amount, fast_fee, recipient);
let filler = self.filled_fast_transfers.read(key);   // ← absent
```

`filled_fast_transfers` appears exactly three times in the entire repository:

| Line | Use |
|---|---|
| 45 | declaration — `Map<u256, ContractAddress>` |
| 136 | duplicate-fill guard inside `fill_fast_transfer` |
| 142 | write of the filler's address |

There is **no read on the settlement path**. The value the guard checks
(`filler_address != 0`) is a keccak hash, which is non-zero with overwhelming
probability, so the early-return always triggers.

---

## Runtime behaviour: deterministic, permanent revert

| # | Step | Result |
|---|---|---|
| 1 | `BytesTrait::new(4, [4 limbs])` | declares 4 bytes, carries 64 — constructed silently |
| 2 | `format` → `concat(@metadata)` | copies `other.size` = **4 of 64 bytes**; fee and id truncated |
| 3 | Message layout | 32 (recipient) + 32 (amount) + 4 (metadata) = **68 bytes** |
| 4 | Destination: `message.metadata()` = `read_bytes(64, 68-64)` | a **4-byte** `Bytes` |
| 5 | `_get_token_recipient`: `metadata.size() == 4`, so `!= 0` | proceeds past the early return |
| 6 | `metadata.read_u256(0)` → `assert(0 + 32 <= 4, 'out of bound')` | **PANIC** |

`read_u256` carries an explicit bounds assert:

```cairo
fn read_u256(self: @Bytes, offset: usize) -> (usize, u256) {
    assert(offset + 32 <= self.size(), 'out of bound');
    ...
}
```

So `Mailbox::process` reverts on **every** fast-transfer settlement. The message
content is fixed, so every retry reverts identically — the message is
**permanently undeliverable**, not merely delayed.

Defect C never executes today because the panic in step 6 precedes it. Fixing
only the encoding (A + B) would surface C as the next failure: the payout would
then target a keccak hash cast to an address, which either fails
`u256 → felt252 → ContractAddress` conversion (panic) or lands on an address
nobody controls (tokens burned). **All three must be fixed together.**

---

## Impact

The filler's capital is unrecoverable. `fill_fast_transfer` has already:

- pulled `amount - fast_fee` from the filler (`fast_receive_from_hook`), and
- paid `amount - fast_fee` to the recipient (`fast_transfer_to_hook`)

before the settlement message exists. Settlement is the only path that repays
the filler, and it can never execute. The origin-side collateral backing the
transfer is simultaneously stranded behind an undeliverable message.

This is not an edge case: `fast_transfer_remote` always attaches metadata, so
step 5 always proceeds into the panic. Every fast transfer on such a route
behaves identically.

---

## Reachability — read before assigning severity

Verified from public sources; **re-check before submitting**, as this may change:

- **Compiled and shipped.** `fast_token_router`, `fast_hyp_erc20` and
  `fast_hyp_erc20_collateral` are all declared in
  `cairo/crates/token/src/lib.cairo` — part of the built token crate, not dead
  files excluded from the build.
- **No deployment found.** No warp route in `hyperlane-registry` references any
  fast variant (`grep -rli "fasthyp\|fast_hyp\|fastTransfer" deployments/` →
  no matches), and the monorepo's `starknet/artifacts` contains no fast contract.
- **Zero test coverage.** No test in the Cairo crates references
  `fast_transfer` or `FastHyp`.

**No funds are at risk today.** The accurate framing is *"a shipped, deployable
contract that loses the liquidity provider's funds on first real use"* — not an
active exploit. Do not lead with a Critical claim.

**Scope caveat:** `hyperlane-starknet` is a **separate repository** from
`hyperlane-monorepo`. Confirm it appears in the Immunefi asset list before
submitting. Many programs scope only deployed mainnet contracts for
smart-contract severities, so an undeployed contract in a side repo may be
triaged as Low/Informational or rejected on scope alone.

What still makes it worth submitting: it requires **no misconfiguration, no
privileged access, and no attacker**. This is a defect in the code itself, not a
hardening opinion — which is a materially stronger position than a
configuration-dependent report.

---

## Suggested fix

**A — encode the true byte length** (`_fast_transfer_from_sender`):

```cairo
BytesTrait::new(
    64, array![fast_fee.low, fast_fee.high, fast_transfer_id.low, fast_transfer_id.high],
)
```

Better still, mirror the working path and let the length follow from the writes,
removing any chance of the mismatch recurring:

```cairo
let mut metadata = BytesTrait::new_empty();
metadata.append_u256(fast_fee);
metadata.append_u256(fast_transfer_id);
```

**B — use byte offsets** (`_get_token_recipient`):

```cairo
let (_, fast_fee)         = metadata.read_u256(0);
let (_, fast_transfer_id) = metadata.read_u256(32);
```

**C — read the map that `fill_fast_transfer` writes**:

```cairo
let key = self
    ._get_fast_transfers_key(origin, fast_transfer_id, amount, fast_fee, recipient);
let filler: ContractAddress = self.filled_fast_transfers.read(key);
if filler != starknet::contract_address_const::<0>() {
    return filler.into();
}
recipient
```

The existing `!= 0` guard is correct in intent — unset map entries read as
address 0. Only the value being checked is wrong.

**Add tests.** A single round-trip test — `fast_transfer_remote` →
`fill_fast_transfer` → settlement → assert the filler received the tokens —
would have caught all three defects at once.

---

## How to verify

```bash
git clone https://github.com/hyperlane-xyz/hyperlane-starknet
cd hyperlane-starknet

# Defect C: the map is written but never read
grep -rn "filled_fast_transfers" cairo/crates/
#   → 3 hits: declaration, dup-guard read, write. No settlement-path read.

# Defects A and B
sed -n '224,283p' cairo/crates/token/src/components/fast_token_router.cairo

# The working reference for byte offsets, same repo
cat cairo/crates/token/src/components/token_message.cairo

# No test coverage
grep -rn "fast_transfer\|FastHyp" cairo/crates/*/tests/ ; echo "exit=$?"
```

Library semantics referenced above are from `alexandria_bytes` 0.4.0
(`packages/bytes/src/bytes.cairo`): `new`, `concat`, `read_u256`,
`BYTES_PER_ELEMENT`.
