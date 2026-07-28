# Push Chain EVM Gateway — permissionless-surface sweep (verdict: hardened)

Target: `contracts/evm-gateway` in `pushchain/push-chain-gateway-contracts`
@ `5a23518e934cae186c3929f5e5bb736e7e11b574`. HackenProof "EVM Gateway SC",
$10k pool, 11 submissions at time of sweep.

Method (same as SVM/Tare): read the project's own `docs/THREAT_MODELLING_DOC.md`
first (40+ documented scenarios), then hunt the dimension it does not cover —
looking specifically for the SVM-winning shape: a permissionless writer to a
slot keyed by public/predictable data that gates a fund flow with no reset, or a
one-way state an unprivileged party trips.

## In-scope contracts read in full
- `src/UniversalGateway.sol` (1099 L) — inbound EVM entry
- `src/Vault.sol` (287 L) — inbound custody / finalize
- `src/UniversalGatewayPC.sol` (294 L) — outbound on Push Chain
- `src/VaultPC.sol` (113 L) — fee custody on Push Chain

## Why the SVM squat twin is CLOSED here
The SVM Critical was a permissionless `init` of a PDA keyed by public
`sub_tx_id`, closable-and-refundable → permanent lockout. The EVM analogue would
be a permissionless writer to `isExecuted[subTxId]` letting an outsider
pre-block a legitimate revert/rescue.

`isExecuted[subTxId]` (`UniversalGateway.sol:114`) is written **only** in
`_validateRevertParams` (`:681`), reachable **only** from `revertUniversalTx`
(`:633`) and `rescueFunds` (`:655`), both `onlyRole(VAULT_ROLE)`. No
permissionless path sets it. The squat/front-run does not exist on EVM. Dead.

## Every crook-shaped lever found — and why each is not a permissionless Critical
1. **`updateEpochDuration` global rate-limit reset** (`:294`) — admin-gated
   (`UG_ADMIN_ROLE`), and even self-documented in the NatSpec as an implicit
   reset. Same shape as SVM Lead 1 (closed as admin-gated). Not permissionless.
2. **Per-token epoch rate-limit exhaustion** (`_consumeRateLimit :855`) —
   permissionless, but (a) explicitly documented as threat scenario §4.2, (b)
   requires actually bridging `threshold` of real value (recoverable on the
   other side, not free), (c) only a **temporary** per-epoch (6h) DoS, not a
   permanent lock. Not Critical, and known.
3. **Per-block USD cap exhaustion** (`_checkBlockUSDCap :834`) — permissionless
   but resets every block; documented §4.2. Temporary. Not Critical.
4. **Vault finalize replay** (§5.9, `Vault.finalizeUniversalTx :149`) — the doc
   itself admits no on-chain subTxId guard for finalisation. **But** it is
   `onlyRole(TSS_ROLE)`. Critical requires "no privileged role." TSS is
   privileged. Real gap, but not Critical by the programme's own bar, and
   already documented.
5. **`VaultPC.receive()` open deposit** (`:112`) — accumulates fees only;
   withdraw is `VPC_ADMIN_ROLE`. No theft/lock. Documented §7.2.
6. **CEA path** (`sendUniversalTxFromCEA`) — gated by `CEAFactory.isCEA`, which
   is a trusted-external dependency and explicitly out of scope (§2).

## Verdict
The four in-scope EVM contracts are materially more hardened than the SVM
gateway was. The permissionless permanent-lock / theft shape that paid on SVM
has no live twin here. Nothing survives to a Critical submission on a
known-shape pass.

Remaining unexamined angle (lower probability, higher effort): the fee/routing
math in `_routeUniversalTx` / `_sendTxWithFunds` / `_fetchTxType` and the
native-vs-ERC20 batching cases (Case 2.1–2.3) — a value-conservation bug there
could be real, but it is not the quick crook-shaped win and would need a full
differential/fuzz pass.

## Recommendation
Higher expected value is **Core Contracts SC** (7 submissions vs 11): it is the
`UniversalCore` / PRC20 / UEA / CEAFactory layer that this gateway repeatedly
marks "trusted-external" and leans its whole security on. Under-audited trusted
core = exactly where the "obviously dumb, nobody looks" bug hides. Requires
pulling the Push Chain core repo (separate from the gateway monorepo).
