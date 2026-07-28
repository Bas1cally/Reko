# Push Chain SVM Gateway: raising `epoch_duration_sec` freezes the rate-limit epoch and blocks withdrawals

**Target**: `pushchain/push-chain-gateway-contracts` @ `5a23518e934cae186c3929f5e5bb736e7e11b574`,
`contracts/svm-gateway/programs/universal-gateway/src`. 4,191 nSLOC Rust/Anchor.
**Programme**: HackenProof DualDefence Audit. Critical-only. Mandatory runnable PoC + suggested fix.
Reputation penalty for a report without a valid PoC.
**Status**: mechanism traced end to end in source. **Severity is genuinely uncertain — read the
assessment before submitting.** No PoC built yet, and this programme closes reports that lack one.

## The defect

`utils/rate_limit.rs` contains two reset guards written by the same hand, and only one of them is
robust:

```rust
// check_block_usd_cap — resets on ANY slot change
if current_slot != rate_limit_config.last_slot { ... }

// consume_rate_limit — resets only on STRICTLY GREATER
if current_epoch > token_rate_limit.epoch_usage.epoch {
    token_rate_limit.epoch_usage.epoch = current_epoch;
    token_rate_limit.epoch_usage.used = 0;
}
```

`current_epoch` is `clock.unix_timestamp as u64 / epoch_duration_sec`, and `epoch_duration_sec` is
mutable via `admin::update_epoch_duration`, which assigns it with no migration of any stored epoch:

```rust
rate_limit_config.epoch_duration_sec = epoch_duration_sec;
```

Because the divisor grows, **increasing the epoch duration makes `current_epoch` smaller**. The stored
epoch is then in the future relative to every subsequent computation, `current_epoch > stored` is
false, and `used` is never reset again:

| change | stored epoch | new current epoch | next reset |
|---|---|---|---|
| 1h → 1d | 495,833 | 20,659 | year **3327** |
| 1d → 1w | 20,659 | 2,951 | year **2365** |
| 1h → 1w | 495,833 | 2,951 | past year 9999 |

Once `used` reaches `limit_threshold`, `consume_rate_limit` fails permanently for that token.

## Why that locks user funds

`validate_token_and_consume_rate_limit` is called at `instructions/withdraw.rs:132` — the **outbound
path users take to get their money out**. A permanently exhausted counter means every withdrawal of
that token reverts with `RateLimitExceeded`. That is the programme's top impact category, *permanent
lockout of end-user funds*.

## The obvious repair is deliberately closed

`admin::set_token_rate_limit` would be the natural fix — except it explicitly refuses to touch the
counter:

```rust
// epoch_usage is NOT reset here — preserving accumulated usage prevents an admin
// threshold update from inadvertently clearing the current-epoch counter (EVM parity).
```

Confirmed by grep: `epoch_usage` is written in exactly one place outside its own struct definition —
the reset inside `consume_rate_limit`. There is no admin reset instruction.

Two escapes remain, and both are bad:
1. `update_epoch_duration(0)` — disables epoch rate limiting **protocol-wide for every token**. A
   security downgrade, not a fix.
2. Revert to the previous, smaller duration — works, but means the duration can never be raised.

## Honest severity assessment — the reason this is a LEAD and not a submission

**For Critical:** impact is exactly "permanent lockout of end-user funds". The trigger is not a
mistake and not malice: raising a rate-limit window is an ordinary operations action, and the
contract simply fails to handle it. The asymmetry with `check_block_usd_cap` in the same file shows
the robust pattern was known and not applied here.

**Against Critical, and this is real:**
- The programme's own likelihood bar reads *"the attack can be executed **without requiring
  privileged roles**"*. This one needs `update_epoch_duration`, which is admin-gated.
- The rules exclude *"human-based errors and rogue privileged users"*. A triager can plausibly file
  this there, even though the argument is that the code is wrong rather than the admin.
- "Permanent" is arguable while escape (1) and (2) exist.

**What would make it unambiguous:** a path where a *non-privileged* party pushes `epoch_usage.epoch`
into the future. That is the next thing to look for, and until it is found this stays a lead. Note
that `update_epoch_duration(u64::MAX)` produces `current_epoch == 0` and is the same defect class,
so the bug is about the missing invariant, not about one specific value.

## Suggested fix (required at submission time by this programme)

Make the guard robust to a non-monotonic divisor, matching the sibling function:

```rust
if current_epoch != token_rate_limit.epoch_usage.epoch {
    token_rate_limit.epoch_usage.epoch = current_epoch;
    token_rate_limit.epoch_usage.used = 0;
}
```

Alternatively, have `update_epoch_duration` bump a config generation counter that `TokenRateLimit`
snapshots, so a duration change invalidates every stored epoch by construction.

## Next steps

1. **Hunt the permissionless variant.** Without it the severity argument is weak, and this programme
   penalises weak reports. Check whether any public entry point (`deposit`) can influence
   `epoch_usage.epoch`.
2. **Build the PoC with LiteSVM.** `cargo` and `rustc` are present; `anchor` and `solana` CLI are
   not. LiteSVM runs the SVM in-process from plain cargo, which satisfies the runnable-PoC rule
   without a validator.
3. **Check the remaining candidate from the same pass**: the `ExecutedSubTx` replay PDA
   (`sub_tx_id` uniqueness). If an unprivileged party can pre-create that PDA for a chosen
   `sub_tx_id`, the corresponding real outbound release is permanently blocked. That would be
   permissionless and would not be front-running if it can be done ahead of time.
4. Get the bounty pool size — it was not in the scope text and decides how much time this deserves.

## Scope notes for this programme

- Out of scope includes *"Known issues in README.md"* and *"known issues on GitHub issue tracker"* —
  check both before writing anything up. `docs/THREAT_MODEL.md` §6 already declares two liveness
  gaps as accepted non-goals ("no user-driven timeout recovery path if off-chain relay never
  executes", "no automatic FeeVault replenishment"). Do not report those.
- Front-running is out of scope. PDA pre-creation is arguably not front-running, but expect the
  objection and pre-empt it.
- Only 3 hackers registered at the time of writing, and the pool is split per unique issue with a
  single valid finding taking 100%. Depth beats breadth here.
