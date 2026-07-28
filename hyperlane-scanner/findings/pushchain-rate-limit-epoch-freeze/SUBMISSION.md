# Permanent lockout of outbound execute funds via permissionless `StoredIxData` squat-and-close

**Severity:** Critical (permanent lockout of end-user funds)
**Target:** `programs/universal-gateway/src/instructions/execute.rs` @
`5a23518e934cae186c3929f5e5bb736e7e11b574`
**Affected instructions:** `store_execute_ix_data`, `close_stored_ix_data`,
`finalize_universal_tx_with_ix_data_ref`

---

## Summary

The tx-size ref-finalize route lets any unprivileged account occupy the `StoredIxData` PDA for a
known `sub_tx_id` and then close it again at will, for the price of transaction fees only. For any
outbound `execute` whose finalize transaction exceeds Solana's 1232-byte limit — where the docs state
the ref route is the **only** route — an attacker can keep the stored `ix_data` permanently
unavailable, so the execute can never be finalized. The bridged funds behind that execute are
permanently locked.

## Root cause

`store_execute_ix_data` (`execute.rs`) has **no authorisation of any kind** — no TSS signature, no
config check, no privileged role:

```rust
pub struct StoreExecuteIxData<'info> {
    #[account(mut)]
    pub caller: Signer<'info>,          // any keypair
    #[account(
        init, payer = caller,
        space = StoredIxData::LEN_BASE + ix_data.len(),
        seeds = [STORED_IX_DATA_SEED, sub_tx_id.as_ref(), ix_data_hash.as_ref()],
        bump
    )]
    pub stored_ix_data: Account<'info, StoredIxData>,
    pub system_program: Program<'info, System>,
}
```

Both PDA seeds are caller-supplied, and the body validates only that `ix_data` is non-empty and hashes
to `ix_data_hash`. It records the caller as the slot's owner:

```rust
stored.store_refund_recipient = ctx.accounts.caller.key();
```

`close_stored_ix_data` then permits that same account to close the slot at any time **before**
finalize has succeeded:

```rust
if !executed_sub_tx_exists
    && ctx.accounts.caller.key() != ctx.accounts.store_refund_recipient.key()
{
    return err!(GatewayError::StoredIxDataNotClosable);
}
```

Since the account is closed with `close = store_refund_recipient`, the rent is refunded to the
attacker on every close. Occupying and vacating the slot is therefore free and unlimited.

`sub_tx_id` is not secret. `INTEGRATION_GUIDE.md` requires it to be deterministic and recommends
`keccak256(event_tx_hash || log_index)`, both derived from a **public source-chain event**; `ix_data`
is built from the same public fields. An attacker watching the source chain computes
`(sub_tx_id, ix_data_hash)` and acts before the relayer begins — this is pre-registration on public
data, not front-running.

## Why it locks funds

`docs/6-TX-SIZE-REF-ROUTE.md` states the routing rule:

> | Serialized finalize tx ≤ 1232 bytes | Direct `finalize_universal_tx` |
> | Serialized finalize tx > 1232 bytes | Store + `finalize_universal_tx_with_ix_data_ref` |

For a large-payload execute (payload size and remaining-account count together push the finalize tx
over 1232 bytes) the ref route is the only route. The attacker selects such a transaction — the ref
route exists precisely because these are routine — and keeps its `StoredIxData` slot empty whenever
finalize would run. The execute can never complete, and the funds committed to it stay locked.

Note the squat by itself is not the lock: `finalize_universal_tx_with_ix_data_ref` validates
`store_refund_recipient` against the stored value, so a relayer facing an occupied slot could finalize
by passing the attacker's address — losing only the 5,000-lamport upload fee to them. The lock is the
**close**: the attacker vacates the slot immediately before each finalize attempt, so the data is
never present when the ref route reads it.

## Impact

- **Permanent lockout of end-user funds** — the programme's top-tier impact.
- The affected amount is the full value of any outbound execute the attacker targets, with no upper
  bound. It exceeds 1% of the targeted user's deposit by construction (it is 100% of it).

## Likelihood (against the programme's Critical criteria)

- **No privileged role** — `store_execute_ix_data` and `close_stored_ix_data` are permissionless.
- **No significant balance** — rent is recovered on every close; measured net cost for a 4-cycle
  campaign is 40,000 lamports, i.e. transaction fees only.
- **No computation or extended time** — two ordinary transactions per cycle.
- **Limited conditions** — one: the target's finalize transaction exceeds 1232 bytes, which the
  attacker selects for.

## Proof of Concept

Runnable, and it drives the **real compiled program** (`universal_gateway.so`) inside LiteSVM — no
logic is reimplemented. Files: `poc/poc.rs`, `poc/Cargo.toml`.

```
cargo-build-sbf --manifest-path programs/universal-gateway/Cargo.toml   # produces target/deploy/universal_gateway.so
# place poc.rs + Cargo.toml adjacent to the gateway checkout (paths in the harness) and:
cargo run --release
```

Output:

```
[1] attacker occupied the slot (no privileged role, no TSS signature)
[2] relayer's own store of the same slot FAILED (init on a live account)
[3] attacker closed the slot, refunded 9773800 lamports of rent
[4.0] re-occupied and released again; slot empty
[4.1] re-occupied and released again; slot empty
[4.2] re-occupied and released again; slot empty
>>> net attacker cost: 40000 lamports (tx fees only; rent recovered every cycle).
ALL ASSERTIONS PASSED
```

Step 1 shows the permissionless occupation, step 2 shows the honest relayer's own store failing on the
live account, step 3 shows the attacker closing and recovering the full rent, and step 4 shows the
cycle repeating indefinitely at the cost of fees alone.

## Suggested fix

Remove the revocation primitive. Two options, smallest first:

1. **Drop the pre-execution close branch.** Reclaim rent only via the post-execution path
   (`executed_sub_tx_exists == true`), which is already permissionless and already refunds the
   original storer. Once a slot is taken it cannot be vacated until the execute finalises, so squatting
   an intent gains nothing — the legitimate finalize consumes the very data the attacker stored.
2. **Authorise the store.** Require a valid TSS signature over `(sub_tx_id, ix_data_hash)` in
   `store_execute_ix_data`, so only genuinely authorised payloads can occupy a slot.

Option 1 is the smaller change and closes the issue without touching the happy path.

---

*Reported via HackenProof. Not disclosed elsewhere. Verified against the README (no known-issues
section) and the GitHub issue tracker (12 issues, none concerning `StoredIxData` or the ref route).*
