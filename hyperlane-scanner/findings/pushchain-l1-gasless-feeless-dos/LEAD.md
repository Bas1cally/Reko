# LEAD — Push Chain L1: feeless block-space DoS via gasless msg types

Program: HackenProof "Push Chain — L1" ($70k pool, up to $15k/critical).
Repo: `pushchain/push-chain-node` @ `0648551281dada6e300f51baca0e7464cb210eef`.
Impact class targeted: **DoS — "overload nodes to the point they cannot
participate" / "inability to process and finalize new transactions"** (explicit
Critical criteria for this L1 program). Permissionless, zero funding.

## The door
`app/txpolicy/gasless.go :IsGaslessTx` marks these msg types **fee-exempt**:
`MsgMigrateUEA`, `MsgExecutePayload`, `MsgVoteInbound`, `MsgVoteOutbound`,
`MsgVoteChainMeta`, `MsgVoteTssKeyProcess`, `MsgVoteFundMigration` (and
`authz.MsgExec` wrapping only these).

`app/ante/fee.go :DeductFeeDecorator.AnteHandle` (lines 60-64): if
`IsGaslessTx(tx)` → **skip fee deduction entirely** (`return next(...)`), for ANY
account (new or existing). The only guard is line 50: `GetGas()==0` rejected, so
the tx is gas-*metered* but pays **no fee**.

`app/ante/account_init_decorator.go`: for a gasless tx from a **not-yet-existing**
account it verifies the sig over (accNum=0, seq=0), creates the account, and
`return ctx, nil` — bypassing the rest of the ante chain. => an attacker can mint
infinitely many fresh accounts, each getting free txs.

## Why the vote msgs are (mostly) safe but ExecutePayload is not
Vote* handlers gate on `IsBondedUniversalValidator(signer)`
(`x/uexecutor/keeper/msg_server.go:83`) — a non-validator vote is rejected after a
cheap state read.

`MsgExecutePayload` is NOT validator-gated. `ValidateBasic`
(`x/uexecutor/types/msg_execute_payload.go`) checks only non-nil/structure; auth
is delegated to the UEA contract *inside* the EVM (Step 3). The handler
`x/uexecutor/keeper/msg_execute_payload.go :ExecutePayload` does real work BEFORE
that auth:
- Step 1: hex-decode, `GetChainConfig` (rejects unregistered chains cheaply).
- Step 2: `CallFactoryToGetUEAAddressForOrigin` — a **factory EVM call**
  (`getUEAForOrigin`) — runs for any registered chain + attacker-chosen owner.
- If UEA not deployed & zero balance → reject *after* that EVM call.

So with a **registered** chain CAIP2 (e.g. real Ethereum) + arbitrary owner, an
attacker reaches at least one factory EVM call per tx, **for free**, and repeats.
Failed txs still consume block gas; block gas is the shared scarce resource that
fees normally protect. Feeless txs let one attacker fill blocks at zero cost →
fee-paying users are starved. Sustained → "inability to process new txs."

## Panic vectors checked in this path (all currently defended — recorded, not assumed)
- `ExecutePayload` line 91 calls `DeductGasFeesFromReceipt(..., receipt, ...)`
  unconditionally with the possibly-nil `receipt` from `CallUEAExecutePayload`.
  **Defended:** `fees.go:104` `if receipt == nil || receipt.GasUsed == 0 { return nil }`.
- `CallFactoryToGetUEAAddressForOrigin` `results[0].(common.Address)` /
  `results[1].(bool)` unchecked assertions — **defended** by ABI `Outputs.Unpack`
  which enforces arity/type (err-checked at line 46).
- usigverifier precompile: `ed25519.Verify` pubkey-length panic — **defended**
  (`query.go:45,86` length-check before Verify).

## Status / open questions (drill next)
1. **Quantify**: measure per-tx compute reachable for free (Step 2 factory call)
   vs block gas limit — is a single attacker enough to saturate blocks? Needs a
   local devnet PoC (the program requires a runnable PoC).
2. **Sharper variant**: hunt an amplification (disproportionate work per declared
   gas) or an outright panic/halt in the gasless-reachable path
   (`MsgMigrateUEA` handler, the auto-deploy path, outbound creation).
3. Confirm `cosmosante.NewMinGasPriceDecorator` also skips gasless (else 0-fee
   gasless txs would be rejected there first — which would *reduce* the surface).

## The amplification thread (raises this from "spam" to clean Critical)

The EVM work in the gasless path runs through the fork's derived-tx primitive
(`push-chain-evm` @ `96231e7`, in scope):
`x/vm/keeper/call_evm.go :DerivedEVMCallWithData`.

- It builds a `core.Message{GasLimit: gasCap, GasFeeCap:0, GasTipCap:0, GasPrice:0}`
  and runs `ApplyMessageWithConfig(tmpCtx, msg, ...)` where `tmpCtx` is a
  `ctx.CacheContext()`.
- `gasCap` for `CallUEAExecutePayload` = the payload's `GasLimit` (line 193-195),
  and for module-sender writes = estimate/DefaultGasCap.
- **Open, decisive question:** is the EVM gas consumed by `ApplyMessageWithConfig`
  charged back to the *outer cosmos block gas meter* of the (gasless, ~0-fee)
  `MsgExecutePayload`? Standard `MsgEthereumTx` bills EVM gas via its ante; a
  **derived** call bypasses that ante. If the EVM compute is NOT billed to the
  cosmos block meter, then:
  - a gasless `MsgExecutePayload` consumes ~0 cosmos block gas but triggers a real
    EVM call → the block gas limit does **not** bound how many fit per block →
    an attacker packs thousands of free EVM-triggering txs into one block → real
    node CPU far exceeds the gas-implied budget → blocks miss their time budget →
    **consensus can't finalize = Critical DoS/halt**, permissionless, zero cost.
- Even without full un-metering, note `GasFeeCap/GasTipCap/GasPrice = 0` on every
  derived message — derived EVM work is intrinsically fee-free at the EVM layer;
  the only cost gate is whatever the *cosmos* meter charges the outer tx, which for
  gasless msgs is not fee-backed.

### The decisive experiment (the PoC the program requires)
On a local devnet: submit N gasless `MsgExecutePayload` txs in one block, each with
a *small declared cosmos gas* + a registered-chain CAIP2 + arbitrary owner (so each
reaches the Step-2 factory EVM call and then rejects). Measure (a) cosmos block gas
consumed vs (b) wall-clock block execution time / CPU. If block time scales with N
while reported block gas stays low → un-metered amplification confirmed → Critical.

## Fork surface still to mine (push-chain-evm @ 96231e7, in scope)
`DerivedEVMCall` is custom fork code with fragile invariants flagged in the repo's
own `DERIVED_TRANSACTIONS.md`:
- **synthetic module-sender signer** (`isModuleSender=true`, no real key) — if a
  user-reachable path can set `isModuleSender` or forge the synthetic signer, a
  user could execute EVM txs *as the uexecutor module account* (which mints PRC20,
  writes chain-meta) → theft/inflation. Verify the signer construction in the fork.
- **`manualNonce` trusted verbatim** — nonce collision → "confusing replays"
  (repo's own words). Check every module-sender call site for nonce-stomp.
- **`gasless=true`** suppresses the receipt gas field (accounting blind spot).

## Honest severity read
Real, permissionless, zero-cost, repeatable — fits the L1 DoS Critical wording.
BUT gasless is a deliberate feature; triage may treat "gasless msgs can be
spammed" as known/accepted unless the PoC shows blocks are actually saturated by
one cheap attacker (→ clear Critical) or a halt is found. Do NOT submit until the
PoC quantifies it. No fantasy — this is a real lead, severity pending measurement.
