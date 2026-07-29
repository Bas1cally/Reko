# Push Chain L1 — door sweep round 3: TSS networking pipeline (universalClient/tss/*)

Deepest and most promising remaining surface: the libp2p-based TSS coordination
network that every validator's `universalClient` runs to coordinate DKLS threshold
signing. Checked because a panic here, reachable by an unauthenticated network
peer, would be about as strong a permissionless/zero-funding Critical as exists —
"widespread node crashes" is explicit in-scope L1 impact.

## The entry point — genuinely unauthenticated at the transport layer

`universalClient/tss/networking/libp2p/network.go:handleStream` — libp2p's
`SetStreamHandler` accepts a stream from **any peer that can dial the host and
knows the protocol ID**, with **no peer allowlist/authentication check** before
reading the frame and dispatching to the registered handler
(`n.handler(stream.Conn().RemotePeer().String(), data)`). Framing is bounded
(`MaxFrameSize = 1 MiB`, explicit length-prefix check, defense-in-depth via
`io.LimitReader`) — no allocation-DoS via oversized length prefix.

`tss.go:onReceive` (the registered handler) does `json.Unmarshal(data, &msg)` —
errors are caught and logged, no panic on malformed JSON. Dispatches
`MessageTypeACK` → `coordinator.HandleIncomingMessage`, everything else (including
attacker-controlled unknown types) → `sessionManager.HandleIncomingMessage`.

## Every downstream handler re-authenticates before doing anything sensitive

Read in full: `coordinator/msg_handler.go` and `sessionmanager/sessionmanager.go`
(handleSetupMessage, handleBeginMessage, handleStepMessage,
handleSignatureBroadcast) plus their support functions (`GetPartyIDFromPeerID`,
`GetPeerIDFromPartyID`, `IsPeerCoordinator`, `validateParticipants`).

Consistent, defense-in-depth pattern — every message type checks the sender
**before** any state mutation or cryptographic FFI call:
- **ACK** (`coordinator.validateIncomingRequest`): sender must resolve (via
  `GetPartyIDFromPeerID`, a simple safe string-equality scan over the on-chain
  validator snapshot — no panic) to a partyID that is a listed participant of a
  *tracked* event.
- **Setup** (`handleSetupMessage`): sender must be `IsPeerCoordinator` (checked
  against on-chain validator set for the current block) before a session is even
  created; `validateParticipants` then checks every participant against the
  eligible-validator set fetched from chain state, with correct-count / threshold
  checks per protocol type (keygen/refresh/quorum-change require exact match;
  sign/fund-migrate require >= computed threshold).
- **Begin** (`handleBeginMessage`): sender must equal the session's stored
  `state.coordinator` exactly.
- **Step** (`handleStepMessage`): sender's partyID must be in `state.participants`
  — checked **before** `session.InputMessage(msg.Payload)` (the DKLS FFI call).
  Raw attacker bytes never reach the cryptographic library unless the sender is a
  verified session participant.
- **SignatureBroadcast** (`handleSignatureBroadcast`): "sender is NOT trusted"
  per the code's own comment — the signature is independently re-verified
  (`VerifySignedData`: rebuilds the expected signing hash from local event data,
  ECDSA-verifies against the correct TSS pubkey) before anything is persisted.

## Verdict

No panic or authentication-bypass found despite a full, systematic pass over the
entire unauthenticated-reachable TSS networking surface — from the raw libp2p
stream handler down through every message-type handler. This is the most
security-sensitive subsystem in the whole node (protects the threshold-signing
keys that control all outbound funds) and it shows it: every sensitive operation
is gated against the on-chain-registered validator set before it runs. Genuinely
hardened; no new Critical here.

## Standing item for the already-submitted finding

`MsgMigrateUEA` shares the exact same `DerivedEVMCallWithData` root cause as the
submitted unmetered-gas Critical (confirmed in round 2) — both gasless,
permissionless entry points into the same unmetered-EVM-CPU-on-revert bug. Prepared
as a supplementary comment for the existing HackenProof report (broadens blast
radius / reachability, not a separate submission — same file, same fix).

## Session status

Three full door-sweep rounds completed on push-chain-node + push-chain-evm beyond
the submitted Critical: uvalidator/utss voting (clean + 2 confirmed public dupes),
universalClient event parsers (1 hardening note, not exploitable in-scope),
ante_evm/state_transition (confirmed isolation of submitted bug), and now the full
TSS networking pipeline (clean). No second submittable Critical found. This
matches the pattern from push-chain-core-contracts earlier in the engagement:
one real, deep flaw existed and was found and submitted; the surrounding surface
is deliberately hardened.
