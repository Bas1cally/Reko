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

## Honest severity read
Real, permissionless, zero-cost, repeatable — fits the L1 DoS Critical wording.
BUT gasless is a deliberate feature; triage may treat "gasless msgs can be
spammed" as known/accepted unless the PoC shows blocks are actually saturated by
one cheap attacker (→ clear Critical) or a halt is found. Do NOT submit until the
PoC quantifies it. No fantasy — this is a real lead, severity pending measurement.
