# HackenProof submission — copy/paste per field

---

## TITLE

```text
Unmetered EVM CPU on the derived-call failure path lets any user halt consensus for free via gasless MsgExecutePayload
```

---

## CATEGORY / IMPACT

L1 — Denial of Service / network disruption: "DoS attacks that overload nodes to the
point where they cannot participate" + "Inability to process and finalize new
transactions". Likelihood: no privileged role, no funding, no extended time.

---

## VULNERABILITY DETAILS

**Scope:** root cause in `push-chain-evm` @ `96231e7`
(`x/vm/keeper/call_evm.go`); permissionless, zero-cost trigger in `push-chain-node`
@ `0648551` (`x/uexecutor`, `app/ante`). All in scope.

**Root cause.** The fork's derived-EVM primitive meters its EVM gas against the cosmos
block gas meter **only on the success branch**. At the end of `DerivedEVMCallWithData`
(`x/vm/keeper/call_evm.go`):

```go
if res.Failed() {
    return res, errorsmod.Wrapf(types.ErrVMExecution, "%s: ret 0x%x", res.VmError, res.Ret)
}
ctx.GasMeter().ConsumeGas(res.GasUsed, "apply evm message")   // <-- reached ONLY on success
return res, nil
```

On any **failed** derived execution (EVM `REVERT` or out-of-gas), the function returns
**before** `ctx.GasMeter().ConsumeGas(res.GasUsed)`. The EVM *computational* gas burned
by a failed derived call is therefore never charged to the cosmos block gas meter — only
the incidental KV-store gas (loading code/accounts) is. A normal `MsgEthereumTx` does not
have this hole because its ante meters gas up front; the derived path meters itself, but
only on success.

**Why it is reachable permissionlessly and for free.** `MsgExecutePayload` is:
- **gasless** — listed in `app/txpolicy/gasless.go`, and `app/ante/fee.go:DeductFeeDecorator`
  returns early (skips fee deduction) when `IsGaslessTx(tx)` is true; and
- **not validator-gated** — `x/uexecutor/types/msg_execute_payload.go:ValidateBasic`
  checks only structure, and `GetSigners` returns the tx signer; any account may send it.

Its handler `x/uexecutor/keeper/msg_execute_payload.go:ExecutePayload` routes to
`CallUEAExecutePayload`, which calls `DerivedEVMCallWithData` with the **payload's own,
attacker-chosen `GasLimit`** (`x/uexecutor/keeper/evm.go`: `gasLimit.SetString(
universal_payload.GasLimit, 10)`). If that execution fails, `ExecutePayload` returns the
error, so the whole cosmos tx rolls back — the per-UEA gas deduction
(`DeductGasFeesFromReceipt`) is undone and the gasless outer tx paid no fee. **Net cost to
the attacker: zero.** But the EVM CPU was already executed by every validator, and it was
not charged to the block gas meter.

**Impact.** The attacker (one-time: deploy one attacker-owned UEA, permissionless) signs a
`UniversalPayload` whose execution calls a gas-burning-then-reverting contract with a high
`GasLimit` (e.g. 8,000,000), and submits it as a gasless `MsgExecutePayload`. Each such tx
does ~8M gas of real validator CPU while consuming only ~30k cosmos block gas. Because the
block gas limit only sees ~30k per tx, it does not bound how many fit: an attacker packs
thousands per block → tens of billions of EVM-gas-equivalent of CPU per block → validators
cannot execute/finalize within the block time → the network stalls and cannot finalize new
transactions. This is a permissionless, zero-cost, repeatable consensus-level DoS.

Not a duplicate of public issue #287 (that concerns `fees.go CalculateGasCost` ignoring
`MaxFeePerGas` — a user *overcharge*); this is the *under*-metering of the cosmos gas meter
on the `call_evm.go` failure branch. Also distinct from the disclosed derived-call findings
F-2026-17738 (bloom-on-revert) and F-2026-17736 (failed-execution-commit), which do not
touch gas metering.

---

## VALIDATION STEPS (runnable PoC)

The attached `test_gas_metering_poc.go` runs on the fork's own integration harness and
proves the accounting flaw directly: it deploys a pure-compute infinite-loop contract
(runtime `5b600056` = `JUMPDEST PUSH1 0 JUMP`), calls it via `DerivedEVMCallWithData` with
an 8,000,000 gas limit so it runs out of gas and reverts, and compares the EVM `res.GasUsed`
to the surrounding `ctx.GasMeter().GasConsumed()` delta.

Place the file at `tests/integration/x/vm/test_gas_metering_poc.go` in the `push-chain-evm`
checkout (@ `96231e7`) and run from the nested `evmd` module:

```bash
cd evmd
go test -tags=test ./tests/integration/ \
  -run 'TestKeeperTestSuite/TestPoCDerivedCallCosmosGasNotMetered' -v -count=1
```

Observed output:

```text
[SUCCESS] balanceOf: EVM res.GasUsed=24302    cosmos delta=94850    (metered: cosmos >= EVM)
[SUCCESS] deploy:    EVM res.GasUsed=1883312  cosmos delta=2246460  (metered: cosmos >= EVM)
[REVERT/OOG] EVM res.GasUsed=8000000  cosmos ctx.GasMeter delta=27637
>>> 7,972,363 gas of EVM CPU went UNMETERED (free)
--- PASS: TestKeeperTestSuite/TestPoCDerivedCallCosmosGasNotMetered
```

On the two success paths the cosmos meter correctly charges ≥ the EVM gas (line 329 runs).
On the failure path, 8,000,000 gas of EVM CPU is charged only 27,637 gas to the cosmos block
meter (99.65% unmetered) — matching the code: `res.Failed()` returns before the `ConsumeGas`
call. The reachability chain (gasless + permissionless `MsgExecutePayload` →
`CallUEAExecutePayload` → `DerivedEVMCallWithData` with attacker `GasLimit`) is shown from
the in-scope handler code cited above.

---

## SUGGESTED FIX

Charge the EVM gas to the cosmos meter regardless of execution result — move `ConsumeGas`
above the `res.Failed()` return (mirroring how `ApplyTransaction` meters failed EVM txs):

```go
ctx.GasMeter().ConsumeGas(res.GasUsed, "apply evm message")
if res.Failed() {
    return res, errorsmod.Wrapf(types.ErrVMExecution, "%s: ret 0x%x", res.VmError, res.Ret)
}
return res, nil
```

---

## SUPPORTING FILES

- `test_gas_metering_poc.go` — the runnable PoC (place under
  `tests/integration/x/vm/` in the `push-chain-evm` checkout).
- `RESULT.txt` — captured passing test output.
