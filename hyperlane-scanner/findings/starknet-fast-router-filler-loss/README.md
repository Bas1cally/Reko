# Starknet FastTokenRouter: settlement pays the hash key instead of the filler — liquidity provider funds lost

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

## Impact

`_transfer_to` passes the returned value straight to the payout hook:

```cairo
let token_recipient = self._get_token_recipient(recipient, amount, origin, metadata);
FTRHooks::fast_transfer_to_hook(ref self, token_recipient, amount);
```

and the hook converts it to an address:

```cairo
.transfer(recipient.try_into().expect('u256 to ContractAddress failed'), amount)
```

`U256TryIntoContractAddress` goes `u256 → felt252 → ContractAddress`, so a
uniformly random keccak output lands in one of two failure modes:

1. **~98% — the value exceeds the felt252 prime (~2²⁵¹·⁵):** `try_into` returns
   `None`, `.expect(...)` panics, the whole `Mailbox::process` reverts. The
   settlement message becomes **permanently undeliverable** (it is deterministic
   — retrying always reverts). The filler is never reimbursed and the origin-side
   collateral is stranded.
2. **~2% — the value happens to be a valid address:** the tokens are transferred
   to an address derived from a keccak hash, which no one controls.
   **Permanently lost.**

In both branches the filler loses the capital they fronted, and every fast
transfer on the route is affected — this is not an edge case, it is the normal
path whenever `metadata.size() != 0`, which `fast_transfer_remote` always
produces.

Note the asymmetry that makes it a *loss* rather than merely a stuck message:
`fill_fast_transfer` has already moved the filler's tokens out
(`fast_receive_from_hook`) and paid the recipient
(`fast_transfer_to_hook`) before the settlement message ever arrives.

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

Worth flagging alongside the fix:

- **Add tests.** The component has none. A single round-trip test
  (`fill_fast_transfer` → settlement → assert the filler received the tokens)
  would have caught this immediately.
- **Adjacent smell to review while fixing:** the metadata `Bytes` is constructed
  as `BytesTrait::new(4, array![fast_fee.low, fast_fee.high, id.low, id.high])`
  — a declared length of `4` alongside four `u128` limbs (64 bytes of payload),
  and it is then read with `read_u256(0)` / `read_u256(2)`. The declared size
  and the offsets do not obviously agree with `alexandria_bytes` byte-oriented
  semantics. I did not chase this to a conclusion, and it may be a second defect
  on the same path; the team should verify it when adding the tests above.
