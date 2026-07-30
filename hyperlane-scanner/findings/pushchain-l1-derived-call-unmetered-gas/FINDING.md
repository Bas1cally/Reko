# Critical — Unmetered EVM CPU on the derived-call failure path enables a free, permissionless consensus DoS

**Program:** HackenProof "Push Chain — L1" ($70k, up to $15k/critical).
**In scope:** `push-chain-evm` @ `96231e7` (the fork — root cause) + `push-chain-node`
@ `0648551` (`x/uexecutor`, `app/ante` — the permissionless free trigger).
**Impact class:** DoS that overloads nodes / "inability to process and finalize new
transactions" (explicit L1 Critical criteria). Permissionless, zero funding.

## Root cause (push-chain-evm)

`x/vm/keeper/call_evm.go`, end of `DerivedEVMCallWithData`:

```go
if res.Failed() {
    return res, errorsmod.Wrapf(types.ErrVMExecution, "%s: ret 0x%x", res.VmError, res.Ret)
}
ctx.GasMeter().ConsumeGas(res.GasUsed, "apply evm message")   // <-- only on SUCCESS
return res, nil
```

On a **failed** derived execution (EVM `REVERT` or out-of-gas), the function returns
**before** `ctx.GasMeter().ConsumeGas(res.GasUsed)`. The EVM *computational* gas of a
failed derived call is therefore **never charged to the cosmos block gas meter**. Only
the incidental KV-store gas (loading code/accounts) is charged.

A standard `MsgEthereumTx` does not have this hole (its ante meters gas up front); the
**derived** path is a Push Chain fork addition and meters gas itself — but only on the
success branch.

## Proof of Concept (runnable, PASSES)

`poc/test_gas_metering_poc.go` — a test on the fork's own integration harness. Run:

```bash
cd push-chain-evm/evmd
go test -tags=test ./tests/integration/ \
  -run 'TestKeeperTestSuite/TestPoCDerivedCallCosmosGasNotMetered' -v
```

It deploys a pure-compute infinite-loop contract (runtime `5b600056` =
`JUMPDEST PUSH1 0 JUMP`) and calls it via `DerivedEVMCallWithData` with an 8,000,000
gas limit, measuring the surrounding `ctx.GasMeter().GasConsumed()` delta.

Measured output (`poc/RESULT.txt`):

```
[SUCCESS] balanceOf: EVM res.GasUsed=24302    cosmos delta=94850    (metered: cosmos >= EVM)
[SUCCESS] deploy:    EVM res.GasUsed=1883312  cosmos delta=2246460  (metered: cosmos >= EVM)
[REVERT/OOG] EVM res.GasUsed=8000000  cosmos ctx.GasMeter delta=27637
>>> 7,972,363 gas of EVM CPU went UNMETERED (free)
```

**8,000,000 gas of real EVM CPU work → 27,637 gas charged to the cosmos block meter
(99.65% unmetered).** On the success paths the cosmos meter correctly charges ≥ the EVM
gas; the gap exists **only** on the failure path — exactly matching the code.

## Permissionless, zero-cost trigger (push-chain-node)

`MsgExecutePayload` is (a) **gasless** — `app/txpolicy/gasless.go` lists it and
`app/ante/fee.go:DeductFeeDecorator` skips fee deduction for it — and (b) **not
validator-gated** (`x/uexecutor/types/msg_execute_payload.go` `ValidateBasic` checks
only structure; any account may sign). Its handler
(`x/uexecutor/keeper/msg_execute_payload.go`) routes to
`CallUEAExecutePayload` → `DerivedEVMCallWithData` with the **payload's own GasLimit**.

Attack (one-time setup: deploy one attacker-owned UEA, permissionless):
1. Attacker signs a `UniversalPayload` (valid sig — their own UEA) whose execution calls
   a gas-burning-then-reverting contract, with `GasLimit` set high (e.g. 8M).
2. Submit it as a **gasless** `MsgExecutePayload`. The UEA executes the payload, burns ~8M
   EVM gas, reverts → `res.Failed()` → the 8M is **not** charged to the cosmos meter.
3. The handler returns the exec error, so the whole cosmos tx rolls back — the UEA gas
   deduction (`DeductGasFeesFromReceipt`) is undone and the outer tx paid no fee. **Net
   attacker cost: zero.** The 8M EVM CPU was still executed by every validator.
4. Because each such tx consumes only ~30k cosmos gas, the block gas limit does **not**
   bound them: an attacker packs thousands per block → tens of billions of EVM-gas-worth
   of real CPU per block → validators cannot execute/finalize within the block time →
   **network stalls / cannot finalize new transactions.**

## Impact

Permissionless, zero-cost, repeatable amplification of validator CPU that is invisible to
block gas accounting → consensus-level DoS (nodes overloaded, blocks miss their time
budget). Matches the program's Critical DoS wording directly.

### Anticipated objection: "this is sustained griefing, not a single permanent halt"

Correct that it is sustained — and pre-empted on the three grounds a DoS is normally
rejected on:

1. **No honest operation clears it while the attack runs.** This is not a
   restart-that-a-manager-can-complete-in-between shape. The system's *own* bounding
   mechanism — the block gas meter — is precisely what fails: it charges ~27k for ~8M of
   real EVM CPU, so it does not bound the attacker at all. There is no in-between window an
   operator can use to "finish the computation"; every block stays saturated for as long as
   the attacker submits.
2. **Sustaining costs the attacker zero.** Gasless message + full cosmos-tx rollback on the
   revert ⇒ each trigger is free and infinitely repeatable. The cost asymmetry is the whole
   finding: ~8M EVM-gas of validator CPU per tx for 0 attacker fee, quantified by the passing
   PoC (8,000,000 → 27,637).
3. **It hits a non-discretionary, time-sensitive function.** The victim is block
   finalization / consensus liveness — not a discretionary operator action with no deadline.
   "Inability to process and finalize new transactions" is the program's explicit Critical
   criterion. The severity does not rest on any single tx locking funds for a week; it rests
   on the network being unable to finalize for the duration of a zero-cost, unbounded attack.

## Hardening — full reachability chain verified from source (30 Jul 2026)

Applied the same adversarial re-verification that reshaped finding #2, this time
link-by-link against the actual `push-chain-node` + `push-chain-evm` source. Every
link holds; unlike #2 there is **no weak link**:

1. **Gasless** — `app/txpolicy/gasless.go` lists `MsgExecutePayload` (and
   `MsgMigrateUEA`); `app/ante/fee.go:63` returns `next(ctx, tx, simulate)` for a
   gasless tx, skipping fee deduction entirely. (It still requires `GetGas() > 0`,
   so the attacker declares a low `GasWanted` ≈ the ~27k actually metered.)
2. **Permissionless** — `x/uexecutor/types/msg_execute_payload.go:49` `ValidateBasic`
   only checks the signer is a valid bech32 address; any account can sign. (One-time
   setup: deploy an attacker-owned UEA; every attack tx afterward is free.)
3. **Attacker controls the gas limit** — `x/uexecutor/keeper/evm.go:173`
   `gasLimit.SetString(universal_payload.GasLimit, 10)` takes the limit from the
   attacker-supplied payload, then passes it to `DerivedEVMCall`.
4. **The reachable call IS the buggy one** — `call_evm.go:108` `DerivedEVMCall` is a
   thin wrapper that calls `DerivedEVMCallWithData` at `call_evm.go:126` — the exact
   function the PoC tests. Its failure path (`call_evm.go:325`) returns before
   `ctx.GasMeter().ConsumeGas(...)` at line 329.
5. **Unmetered on failure** — proven by the passing test (8,000,000 → 27,637).
6. **Net-zero cost on revert** — `x/uexecutor/keeper/msg_execute_payload.go:87-97`:
   the handler runs `CallUEAExecutePayload`, then `DeductGasFeesFromReceipt`, then
   `if execErr != nil { return execErr }`. Returning the error rolls back the whole
   Cosmos tx (cached store discarded), which **undoes the UEA gas deduction too** —
   so the reverting attacker pays nothing, while every validator executed the ~8M
   EVM CPU.

**The load-bearing number is measured, not argued:** amplification =
8,000,000 / 27,637 = **~289×**. Each unit of block-gas budget buys the attacker ~289
units of real EVM CPU. A block packed with these txs therefore takes ~289× its
gas-budgeted execution time, so validators cannot execute/finalize it within the
block interval → consensus stalls. This holds for any `MaxGas` value.

**Honest residual:** the accounting bug + every reachability link are confirmed from
code and a passing test; a full live e2e (pack a real block on `pchaind`, measure
wall-clock execution vs block time) would be *confirmatory*, not exploratory, and is
the one step not yet run (it needs the UEA genesis setup). This is the finding's
stated weakest point — stated, not hidden.

## Suggested fix

Charge the EVM gas to the cosmos meter regardless of execution result — move the
`ConsumeGas` above the `if res.Failed()` return (mirroring how `ApplyTransaction` meters
failed EVM txs):

```go
ctx.GasMeter().ConsumeGas(res.GasUsed, "apply evm message")
if res.Failed() {
    return res, errorsmod.Wrapf(types.ErrVMExecution, "%s: ret 0x%x", res.VmError, res.Ret)
}
return res, nil
```

## Notes / honesty
- The PoC proves the **core accounting flaw** directly at the fork level (8M→27k). The
  end-to-end `MsgExecutePayload` chain is argued from the in-scope handler code above.
  The accounting bug + the gasless/permissionless reachability are each shown from code
  plus a passing test. (`pchaind` also builds here without `dkls23-rs` — see the Update
  section — so a full-node e2e is feasible if required for triage.)
- Distinct from the disclosed derived-call findings F-2026-17738 (bloom-on-revert) and
  F-2026-17736 (failed-execution-commit); this is the **gas-metering** gap on the same
  failure branch, not covered by those regression tests.

## Update — full-node e2e is feasible in this env
`pchaind` builds **without** `dkls23-rs` (that private repo backs only the off-chain
`puniversald`/Universal Client TSS; `go list -deps ./cmd/pchaind` shows no `go-wrapper`
import). A 207 MB `pchaind` was built and runs here. A full-protocol e2e (register a
chain in `uregistry`, deploy the UEA factory, deploy an attacker UEA, submit a gasless
`MsgExecutePayload` whose signed payload burns gas then reverts, and observe block gas
vs execution) is therefore possible; it just requires replicating the UEA genesis setup.
The core accounting flaw is already proven directly by the passing fork test above.
