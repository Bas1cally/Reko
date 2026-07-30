# StarkNet (HackenProof) — scope verdict after a real read

**Date:** 30 Jul 2026. **Program:** StarkNet Blockchain/DLT, Critical up to $250k
(permanent freeze / direct loss of funds). Open bounty, no deadline, no visible
competition. **Rule that dominates everything:** *"AI-generated reports without
runnable PoC are not accepted"* + *"Exploits as a result of a malicious
operator, with the exception of malicious verifier, until Starknet is fully
decentralized"* is out of scope.

This is a documented **turn-away**, decided the way METHOD-NOTE says to decide
it: reachability-first, against the actual code, not from the gut.

## What was actually read

Cloned `starkware-libs/cairo-lang` (sparse) and read the only part of the scope
where our edge (Solidity PoC discipline) applies — the L1 core contracts:

- `starknet/solidity/Starknet.sol` (474 L) — state update + proof consumption
- `starknet/solidity/StarknetMessaging.sol` (219 L) — L1↔L2 message bridge
- `starknet/solidity/Output.sol`, `StarknetState.sol`, `StarknetGovernance.sol`,
  `StarknetOperator.sol`
- `solidity/interfaces/ProxySupport.sol` — proxy init / upgrade machinery
- (`solidity/{libraries,components}` skimmed; `tokens/` is **not** in scope)

The other ~35 scope entries are the Cairo common library + Starknet OS Cairo
program (zk-VM soundness). That is not our demonstrated lane and is where
"reading == median finding" would be worst — every zk researcher is already
there.

## Reachability walk — who can actually call the money paths

| Path | Gate | Reachable by us? |
|---|---|---|
| `updateState` / `updateStateKzgDA` (state root, message registration, DA) | `onlyOperator` | **No** — malicious operator explicitly out of scope until decentralized |
| `setProgramHash` / `setConfigHash` / `setVerifierAddress` / fee collector | `onlyGovernance` / `notFinalized` | **No** — privileged-address attacks out of scope |
| `initialize` / `safeAddImplementation` (proxy) | `notCalledDirectly` (delegatecall via proxy) + governance-gated `addImplementation` | **No** — first-init front-run needs to beat governance at deploy; upgrades are governance-gated |
| Verifier check `IFactRegistry(verifier()).isValid(...)` | external SHARP/GPS verifier contract | **Out of this scope's repo** — the "malicious verifier" carve-in points at code not listed here |
| `sendMessageToL2` / `consumeMessageFromL2` / `startL1ToL2MessageCancellation` / `cancelL1ToL2Message` | **permissionless** | **Yes** — but ~200 lines, mature, no fresh critical visible |

The entire high-value surface (everything that moves the state root or registers
bridge messages) sits behind `onlyOperator`, and processMessages / Output parsing
are only reached from that operator path. The program's own carve-out removes
that whole class before any math matters — the Kamino lesson exactly: a real bug
there is not a bug until a non-privileged party can supply the input, and here
they can't.

## The only permissionless surface, examined

`StarknetMessaging` public functions:

- `sendMessageToL2`: `require(msg.value > 0 && <= 1 ether)`, global monotonic
  nonce folded into `msgHash`, so `l1ToL2Messages()[msgHash] = msg.value + 1`
  cannot collide across sends. Fine.
- `consumeMessageFromL2`: keyed on `l2ToL1MsgHash(fromAddress, msg.sender, payload)`
  — only the intended `toAddress` consumes; no external call, no reentrancy;
  decrements after emit. Fine.
- `cancel` flow: `startL1ToL2MessageCancellation` → `cancelL1ToL2Message` after
  `messageCancellationDelay` (5 days default), hash bound to `msg.sender` so you
  cannot cancel another sender's message. Overflow check on the delay is present.
  Fine. (Note: cancel zeroes the fee slot without an on-L1 ETH refund in this
  file — long-standing design, and it is the canceller's own ≤1 ETH fee, so not a
  fresh permissionless critical.)

Nothing here is a fresh, provable, permissionless permanent-freeze / loss-of-funds.

## Verdict

**Do not invest hunting time here.** This confirms — from the real code, not the
gut — the strategic read: our edge touches only 4 of ~40 scope entries, those 4
are the most-audited bridge contracts in the space, and the program's operator
carve-out plus governance-exclusion remove essentially the entire reachable
high-value surface. It is an open bounty with no deadline and no competition —
the exact profile METHOD-NOTE flags as "sunk cost, no natural stop."

The zk/Cairo majority ($250k dream) is a real target for a zk-soundness
specialist with a Cairo PoC harness. It is not our differentiated lane, and a
reading-only pass there produces the median finding at best.

**Recommendation:** hold for the next running *contest* (deadline + competition +
our Solidity edge aligned), rather than grind this. Same call we made on Vesu,
same reasoning, now backed by an actual read of the in-scope contracts.
