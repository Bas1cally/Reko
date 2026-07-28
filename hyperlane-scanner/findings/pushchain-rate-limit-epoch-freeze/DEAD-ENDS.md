# Push Chain — permissionless surface swept, dead ends recorded

Thinking like a crook, not a dev: what can an **unprivileged** party do that steals funds or locks
them permanently? Every permissionless entry point was checked. One payload (the StoredIxData squat,
see SUBMISSION.md). The rest, recorded so the ground is not re-tread:

## DEAD — pre-fund the replay PDA to brick `init` (tested, not assumed)

The natural crook move against `init` on `ExecutedSubTx` (used in execute/revert/rescue) and
`StoredIxData`: transfer 1 lamport to the PDA address before the legitimate `init`, so the on-chain
`init` fails on an already-existing account. That would brick every finalize/revert/rescue for a
chosen `sub_tx_id`, permissionless, for 1 lamport — far bigger than the squat.

**Defeated by Anchor 0.31.1.** Tested against the real compiled program (`poc/prefund-test.rs`): the
attacker's only primitive against an off-curve PDA is a bare `system_program::transfer` (nobody can
sign `create_account` for a PDA), which leaves it system-owned with zero data. Anchor 0.31.1 handles
exactly that case with allocate+assign instead of create_account, so the victim's `init` succeeds:

```
-- pre-funded PDA with 1 lamports (owner 111..., data 0 bytes)
   victim init SUCCEEDED (owner DJoF..., data 141 bytes). Pre-fund did NOT brick init.
-- pre-funded PDA with 890880 lamports (rent-exempt)
   victim init SUCCEEDED. Pre-fund did NOT brick init.
```

If the program were on an older Anchor (< ~0.24) this would be a critical. It is not. Recorded
because it is the first thing a reviewer of this program should check and now doesn't have to.

## NOT CRITICAL HERE — deposit exhausts the shared per-token rate limit

`deposit` (`send_universal_tx`) and `withdraw` both call `validate_token_and_consume_rate_limit` on
the same `TokenRateLimit` account (seeded by token). A crook can deposit up to `limit_threshold` to
exhaust `epoch_usage.used`, blocking all **withdrawals** of that token — permissionless, and the
crook keeps bridged credit for the deposit so it costs them little.

But the counter resets automatically on the next epoch (`consume_rate_limit` resets when
`current_epoch > stored`), so this is a **temporary** lockout. This programme's Critical impact list
contains only *permanent* lockout — temporary freezes are not eligible. It becomes permanent only if
combined with the epoch-freeze, which needs admin (Lead 1, closed). Not submittable here; would be a
valid Medium/High elsewhere.

## CLEAN — deposit has no theft primitive

`send_universal_tx` moves the user's **own** lamports into the vault (`system_program::transfer` from
`user`), collects the inbound fee to the fee vault first, and credits the bridge off-chain by the
deposited amount. To extract more than deposited a caller needs a TSS-signed outbound, which is
gated. No permissionless over-credit or vault extraction.

## CLEAN — revert / rescue tightly TSS-bound

Both take a permissionless `caller: Signer` but gate the release on `validate_message` over the exact
tuple: `rescue` binds `(instruction_id=4, amount, sub_tx_id, universal_tx_id, (mint,) recipient,
gas_fee)` and additionally enforces `recipient_token_account.owner == recipient` and mint
consistency; `revert` binds the analogous set. The SPL transfer signs as the vault PDA, so a
crook-supplied `token_vault` whose authority is not the vault PDA makes the CPI fail. No redirection
of vault funds, no amount/recipient substitution.

## Conclusion

One permissionless Critical: the StoredIxData squat-and-close (SUBMISSION.md, PoC passing against the
real program). The remaining permissionless surface is either clean, defeated by the Anchor version,
or only temporary — each checked rather than assumed, several with a runnable test.
