# Push Chain L1 — door sweep round 2 (post-submission)

Continuing the hunt after submitting the derived-call unmetered-gas Critical. Same
discipline: read first, form a hypothesis, verify against code/tests before treating
anything as a finding.

## Doors opened, verdicts

1. **`x/uvalidator` ballot/voting (ballot.go, voting.go, types/ballot.go)** — read in
   full. `GetVoterIndex`/`AddVote`/`IsFinalizingVote`/`ExpireBallotsBeforeHeight` are all
   properly bounds-checked and err-wrapped. No panic surface found.
2. **`RecomputeBallotQuorum`** (the quorum-formula computation at `ballot.go:283`,
   `newThreshold = (2*newEligibleCount)/3 + 1`) — **same off-by-one formula already
   publicly reported in `pushchain/push-chain-node` issue #287** ("Consensus quorum bug
   halts bridge at N%3==0"). Confirmed duplicate; not submittable. Also, the msg handler
   (`msg_server.go:160`) is admin-gated (`params.Admin != msg.Signer` check) — not
   permissionless regardless.
3. **`fees.go:CalculateGasCost`** — confirmed **exact duplicate** of the same public
   issue #287's second half ("Gas overcharge ignores MaxFeePerGas"): the EIP-1559 tip/cap
   logic is commented out (lines 68-77), `effectiveGasPrice` is validator-controlled
   `baseFee` only. Not submittable (already publicly disclosed).
4. **`universalClient/chains/evm/event_parser.go`** — genuine code fragility found:
   `dataOffset := new(big.Int).SetBytes(word).Uint64()` truncates an untrusted 256-bit
   word to 64 bits; `readDynamicBytes`'s bound check `absOff+32 > uint64(len(data))` can
   itself overflow (wrap) for `absOff` near `MaxUint64`, defeating the guard, and the
   subsequent `data[absOff:absOff+32]` slice panics (`slice bounds out of range`).
   **Reachability check:** the EVM event listener filters `ethereum.FilterQuery{
   Addresses: [gatewayAddress, vaultAddress]}` — only logs from the real, audited
   `UniversalGateway.sol`/`Vault.sol` are parsed. Solidity's ABI encoder always computes
   dynamic-type offsets correctly and boundedly for a legitimate `emit UniversalTx(...)`;
   an attacker's `req.payload` content cannot corrupt the offset word itself (we already
   fully audited `UniversalGateway.sol` this session and found no way to emit an
   arbitrarily-shaped event). Reaching this parser bug would require either (a) a
   compromised/malicious Gateway contract at the configured address, or (b) an admin
   registering a non-audited chain — both are privileged/rogue-actor preconditions,
   explicitly out of scope ("Human-based errors and rogue privileged users are
   considered to be not valid vulnerabilities"). **Recorded as a hardening
   recommendation, not submitted as a vulnerability** — no fantasy finding without a
   permissionless trigger.
5. **`universalClient/chains/svm/event_parser.go`** — by contrast, thoroughly
   bounds-checked: every `data[offset:offset+N]` read is preceded by an explicit
   `len(data) < offset+N` check, and all lengths are `uint32`-derived (safe from `int`
   overflow on 64-bit hosts). Clean.
6. **`app/ante/ante_evm.go`** — a thin 43-line wrapper; the actual EVM ante logic lives
   in the fork's `evmante.NewEVMMonoDecorator` (upstream cosmos-evm baseline code, not
   Push Chain-specific). No new surface.
7. **`x/vm/keeper/state_transition.go:ApplyTransaction`** (the canonical `MsgEthereumTx`
   entry point) — confirmed it correctly charges gas **unconditionally** at the end
   (`AddTransientGasUsed` + `ResetGasMeterAndConsumeGas`, no early return on
   `res.Failed()`), unlike the fork's `DerivedEVMCallWithData`. This **confirms our
   submitted finding is an isolated defect specific to the Push Chain-added derived-call
   path**, not a broader systemic gap in the EVM fork — strengthens rather than dilutes
   the existing submission.
8. **`x/uexecutor/keeper/handler.go:depositPRC20`** — `SetString` result properly checked
   (`ok`), clean.

## Additional reachability for the already-submitted finding (not a new unique)

`MsgMigrateUEA` (`x/uexecutor/keeper/msg_migrate_uea.go`) routes through
`CallUEAMigrateUEA` → the same `DerivedEVMCallWithData` primitive as `MsgExecutePayload`.
It is *also* gasless (listed in `app/txpolicy/gasless.go`) and not validator-gated. This
means the submitted unmetered-gas bug has a **second independent, permissionless, gasless
trigger** — worth adding as a supplementary comment on the existing report (broadens
blast radius / strengthens severity), not a separate submission (same root cause, same
file, same fix).

## Honest status

No new submittable Critical found in this round. Two strong-looking candidates were
tested and correctly rejected: one for lacking a permissionless trigger (parser overflow
behind an audited gateway), one for being a confirmed public duplicate (gas-fee-cap
bug, issue #287). Continuing the hunt in `x/utss` (TSS key/fund-migration voting) and
`universalClient/tss/*` (off-chain signing coordination) next.
