# Starknet FastTokenRouter is non-functional: every fast-transfer settlement reverts, stranding the liquidity provider's funds

*Three independent defects on the same ~20 lines. Defect 1 was found first and
is described first; defects 2 and 3 were found while chasing it and are what
actually fires at runtime. Read the "Combined effect" table for the runtime
behaviour.*

**Target**: `hyperlane-xyz/hyperlane-starknet`
`cairo/crates/token/src/components/fast_token_router.cairo` → `_get_token_recipient`

**Reviewed commit**: HEAD of `main` at time of review (shallow clone; re-pin before submitting)
**Severity**: **Logic bug causing direct loss of funds — but in code that is compiled and shipped yet, as far as I can verify, not deployed anywhere.** See "Reachability" before choosing a severity in the submission.
**Requires misconfiguration?** **No.** This is broken by default for anyone using the feature as designed.

## The bug

`FastTokenRouterComponent` implements "fast transfers": a liquidity provider
(the *filler*) fronts tokens to the recipient immediately via
`fill_fast_transfer`, and is later reimbursed when the real Hyperlane settlement
message arrives. The filler's identity is recorded here:

```cairo
// fill_fast_transfer
let filled_fast_transfer_key = self
    ._get_fast_transfers_key(origin, fast_transfer_id, amount, fast_fee, recipient);
...
let caller = starknet::get_caller_address();
self.filled_fast_transfers.write(filled_fast_transfer_key, caller);   // filler stored
```

On settlement, `_get_token_recipient` is supposed to look that filler up and pay
them instead of the original recipient. It does not:

```cairo
fn _get_token_recipient(...) -> u256 {
    if metadata.size() == 0 {
        return recipient;
    }

    let (_, fast_fee) = metadata.read_u256(0);
    let (_, fast_transfer_id) = metadata.read_u256(2);

    let filler_address = self
        ._get_fast_transfers_key(origin, fast_transfer_id, amount, fast_fee, recipient);
    if filler_address != 0 {
        return filler_address;      // <-- returns the KEY, not the stored filler
    }

    recipient
}
```

`_get_fast_transfers_key` returns `data.keccak()` — a `u256` **hash used as the
storage map key**. The variable is named `filler_address`, but no map read ever
happens. The missing line is the lookup itself:

```cairo
let key = self._get_fast_transfers_key(origin, fast_transfer_id, amount, fast_fee, recipient);
let filler_address = self.filled_fast_transfers.read(key);   // <-- absent
```

Confirmation that the map is never read on this path — `filled_fast_transfers`
occurs exactly three times in the entire repository:

| Line | Use |
|---|---|
| 45 | declaration (`Map<u256, ContractAddress>`) |
| 136 | duplicate-fill guard inside `fill_fast_transfer` |
| 142 | write of the filler address |

There is **no read** in the settlement path.

## Defect 2: the metadata is encoded with the wrong length, and read at the wrong offsets

Chasing the same ~20 lines turned up two further defects, both verified against
the `alexandria_bytes` 0.4.0 source. **They fire before defect 1 is even
reached.**

`_fast_transfer_from_sender` builds the metadata like this:

```cairo
BytesTrait::new(
    4, array![fast_fee.low, fast_fee.high, fast_transfer_id.low, fast_transfer_id.high],
)
```

In `alexandria_bytes`, `Bytes { size, data }` stores `size` as a **byte** length
and `data` as 16-byte limbs (`BYTES_PER_ELEMENT = 16`):

```cairo
fn new(size: usize, data: Array<u128>) -> Bytes {
    let min_len = (size + BYTES_PER_ELEMENT - 1) / BYTES_PER_ELEMENT;
    assert(data.len() >= min_len, 'Insufficient data');   // only guards *too little* data
    Bytes { size, data }
}
```

Two u256 values are **64 bytes**, so the size should be `64`. Passing `4` looks
like a limb/element count was used instead. The constructor does not catch it —
its assert only rejects *insufficient* data (`4 >= 1` passes), never excess.

The same confusion appears on the read side:

```cairo
let (_, fast_fee)         = metadata.read_u256(0);
let (_, fast_transfer_id) = metadata.read_u256(2);   // should be 32
```

`read_u256` offsets are byte offsets. The repo's own working code proves it —
`token_message.cairo` reads consecutive u256 fields at **0, 32, 64**. Offset `2`
would read bytes 2..34, overlapping the first value by 30 bytes.

### Combined effect: every fast-transfer settlement reverts, deterministically

| # | Step | Result |
|---|---|---|
| 1 | `BytesTrait::new(4, [4 limbs])` | Bytes declares 4 bytes, carries 64. Constructed silently. |
| 2 | `TokenMessageTrait::format` → `bytes.concat(@metadata)` | `concat` copies exactly `other.size` bytes → **only 4 of 64 bytes** are appended; `fast_fee` and `fast_transfer_id` are truncated away. |
| 3 | Message layout | 32 (recipient) + 32 (amount) + 4 (metadata) = 68 bytes |
| 4 | Destination: `message.metadata()` = `read_bytes(64, size-64)` | a 4-byte `Bytes` |
| 5 | `_get_token_recipient`: `metadata.size() == 4`, so `!= 0` → proceeds | |
| 6 | `metadata.read_u256(0)` → `assert(0 + 32 <= 4, 'out of bound')` | **PANIC** |

So `Mailbox::process` reverts on **100%** of fast-transfer settlement messages —
not probabilistically, and not recoverably: the message content is fixed, so
every retry reverts identically. The settlement is **permanently undeliverable**.

This supersedes an earlier estimate in this report that framed the failure as a
~98%/~2% split on the `u256 → ContractAddress` conversion. That conversion is
never reached; the metadata read panics first. Defect 1 (returning the hash key
instead of the filler) is therefore **latent** — it becomes the active failure
only once the encoding is fixed.

## Impact

`fill_fast_transfer` has already moved the filler's tokens out
(`fast_receive_from_hook`) and paid the recipient (`fast_transfer_to_hook`)
*before* the settlement message arrives. The settlement is the filler's only
reimbursement path, and it can never execute.

Result: **the liquidity provider's capital is unrecoverable**, and the
origin-side collateral backing the transfer is stranded behind an
undeliverable message. This affects every fast transfer, not an edge case —
`fast_transfer_remote` always attaches metadata, so step 5 above always
proceeds into the panic.

Three independent defects sit in the same ~20 lines:

1. `_get_token_recipient` returns the storage **key** instead of reading
   `filled_fast_transfers` (latent behind #2/#3).
2. Metadata `Bytes` declared as 4 bytes instead of 64 → payload truncated by
   `concat`.
3. Second `read_u256` offset `2` instead of `32`.

None is caught by a test, because the component has none.

## Reachability — read this before assigning severity

Verified as best I can from public sources; **re-check before submitting**:

- **Compiled and shipped:** `fast_token_router`, `fast_hyp_erc20` and
  `fast_hyp_erc20_collateral` are all declared in
  `cairo/crates/token/src/lib.cairo`, so they are part of the built token crate,
  not dead files excluded from the build.
- **No deployment found:** no warp route in `hyperlane-registry` references any
  fast variant (`grep -rli "fasthyp\|fast_hyp\|fastTransfer" deployments/` →
  no matches). The monorepo's `starknet/artifacts` contains no fast contract.
- **Zero test coverage:** no test file in the Cairo crates references
  `fast_transfer` or `FastHyp`. Nothing would have caught this.

So: no funds are at risk *today*. The honest framing is **"a shipped,
deployable contract that loses the liquidity provider's funds on the first real
use"** — not an active exploit.

**Scope caveat:** `hyperlane-starknet` is a **separate repository** from
`hyperlane-monorepo`. Confirm it appears in the Immunefi asset list. Many
programs scope only deployed mainnet contracts for smart-contract severities; an
undeployed contract in a side repo may be triaged as Low/Informational or
rejected outright. Do not lead with a Critical claim.

What makes it worth submitting anyway, and stronger than a config-hardening
report: it needs **no misconfiguration, no privileged access, and no attacker**.
Anyone using the feature exactly as intended loses money on the first
settlement. That is a defect in the code itself.

## Suggested fix

One line — read the map that `fill_fast_transfer` already writes:

```cairo
let key = self
    ._get_fast_transfers_key(origin, fast_transfer_id, amount, fast_fee, recipient);
let filler: ContractAddress = self.filled_fast_transfers.read(key);
if filler != starknet::contract_address_const::<0>() {
    return filler.into();
}
recipient
```

Note the `!= 0` guard must compare the *stored address* (unset map entries read
as address 0), which is what the current `filler_address != 0` check was clearly
intended to do — the check is correct, the value it checks is not.

And the encoding, which must be fixed for the settlement to execute at all:

```cairo
// _fast_transfer_from_sender — 2 x u256 = 64 bytes, not 4
BytesTrait::new(
    64, array![fast_fee.low, fast_fee.high, fast_transfer_id.low, fast_transfer_id.high],
)

// _get_token_recipient — byte offsets, matching token_message.cairo's 0/32/64
let (_, fast_fee)         = metadata.read_u256(0);
let (_, fast_transfer_id) = metadata.read_u256(32);
```

Cleanest would be to mirror the working path and use
`BytesTrait::new_empty()` + `append_u256(...)`, which makes the length
self-consistent by construction and removes the chance of a size/limb mismatch
recurring.

**Add tests.** The component has none. A single round-trip test —
`fast_transfer_remote` → `fill_fast_transfer` → settlement → assert the filler
received `amount - fast_fee` — would have caught all three defects at once.
