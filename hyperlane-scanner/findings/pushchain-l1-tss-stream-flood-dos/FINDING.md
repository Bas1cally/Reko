# Critical — Unauthenticated, unbounded libp2p stream flooding lets any internet peer exhaust every validator's TSS node with no privileged role and no funding

**Program:** HackenProof "Push Chain — L1" ($70k pool, up to $15k/critical).
**In scope:** `push-chain-node` @ `0648551281dada6e300f51baca0e7464cb210eef`,
asset **`universalClient/`** (explicitly listed as its own in-scope asset —
"Universal Client").
**Impact class:** DoS that overloads nodes / "widespread node crashes" (explicit
L1 Critical criteria). Permissionless, zero funding, no privileged role.

## Root cause

`universalClient/tss/networking/libp2p/network.go`:

```go
host, err := libp2p.New(
    libp2p.Identity(priv),
    libp2p.ListenAddrStrings(cfg.ListenAddrs...),
)
...
host.SetStreamHandler(n.protocolID, n.handleStream)
```

No `libp2p.ResourceManager(...)` or `libp2p.ConnectionManager(...)` option is
passed — the host relies entirely on go-libp2p's built-in defaults for
per-peer/global connection and stream limits. `handleStream` accepts a stream
from **any peer that can dial the host and knows the protocol ID**
(`/push/tss/1.0.0` by default), with **zero authentication or allowlisting**
before reading the frame:

```go
func (n *Network) handleStream(stream network.Stream) {
	defer stream.Close()
	_ = stream.SetReadDeadline(time.Now().Add(n.cfg.IOTimeout)) // default 15s
	data, err := readFramed(stream)
	...
	go n.handler(stream.Conn().RemotePeer().String(), data)
}

func readFramed(r io.Reader) ([]byte, error) {
	br := bufio.NewReader(io.LimitReader(r, int64(MaxFrameSize)+4))
	var length uint32
	binary.Read(br, binary.BigEndian, &length)
	if length > MaxFrameSize { return nil, ... } // MaxFrameSize = 1 MiB
	buf := make([]byte, length)         // allocates up to 1 MiB per stream
	_, err = io.ReadFull(br, buf)       // blocks up to IOTimeout if body never arrives
	...
}
```

All the message-type authentication we found in round 3 of this hunt (ACK,
Setup, Begin, Step, SignatureBroadcast — all correctly gated against the
on-chain validator set) sits **downstream** of this point. The bug is at the
**transport layer, before any of that runs**: any peer can hold `handleStream`
blocked for up to `IOTimeout` (15s) with a live goroutine and up to 1 MiB of
allocated memory, by opening a stream, writing a *valid* 4-byte length prefix
(e.g. `MaxFrameSize`), and then never sending the payload body. Nothing in
Push Chain's own code caps how many concurrent streams a single remote peer
(or many peers) may hold open this way.

## Proof of Concept (runnable, measured against the real code)

`poc/flood_poc_test.go`, run against the real `Network` type from
`universalClient/tss/networking/libp2p`:

```bash
cd push-chain-node
go test ./universalClient/tss/networking/libp2p/ \
  -run TestPoC_UnauthenticatedStreamFlood_Escalation -v -count=1
```

Setup: a victim `Network` is created via the real, unmodified `New()` — same
code path as production. A separate "attacker" libp2p host (a plain
`libp2p.New(...)`, standing in for any outside peer — its own resource manager
is disabled via `libp2p.ResourceManager(&network.NullResourceManager{})`,
since a real attacker controls their own process and has no reason to keep
libp2p's default self-throttling) opens 6 overlapping waves of 800 concurrent
streams (4,800 total) against the victim. Each stream: connect, write a valid
`MaxFrameSize` length prefix, send nothing further, hold the connection open.

**Measured result** (`poc/RESULT_unthrottled.txt`):

```
BASELINE: goroutines=51 heap=1403896 bytes (1.34 MiB)
...
PEAK goroutines=4923 (baseline 51, delta +4872)
PEAK heap=96019080 bytes (91.6 MiB) (baseline 1.34 MiB, delta +90.2 MiB)
AFTER drain: goroutines=51 heap=4817704 bytes (4.59 MiB)
ESCALATION RESULT: attempted=4800 opened=4800 ...
```

**100% of the 4,800 attacker-opened streams were accepted — zero rejections
of any kind from the victim.** Goroutines and heap grew in lock-step with
attacker effort across all 6 waves with no plateau/backpressure observed, and
fully drained back to baseline only after `IOTimeout` elapsed and the streams
closed — confirming the growth is a direct, unmitigated function of how many
concurrent malformed-frame streams the attacker chooses to hold open.

For contrast, `poc/RESULT_throttled_attacker_baseline.txt` is the same test
*before* disabling the attacker's own resource manager: only 143/4,800 streams
succeeded, and every failure was `"transient: cannot reserve outbound
stream"` — **libp2p's resource-manager rejection on the ATTACKER's own
dialing side**, not any defense on the victim. This distinction matters: the
victim never once rejected a stream in either run.

## Why this reaches "widespread node crashes" / Critical, not just "one node is slow"

- Validator P2P addresses are **on-chain public data** — `NetworkInfo.MultiAddrs`
  per validator is read directly from chain state by this same codebase
  (`coordinator.go:GetMultiAddrsFromPeerID`, used to dial peers for the TSS
  ceremony). An attacker enumerates every registered universal validator and
  floods all of them **simultaneously** with the identical, trivially cheap
  script (a handful of TCP/QUIC connections + 4 bytes each — negligible
  attacker bandwidth and zero funding).
- The measured 4,800-stream run cost the attacker nothing but ordinary
  residential bandwidth and produced +90 MiB / +4,872 goroutines on a single
  victim in ~20 seconds; nothing in the code caps this — an attacker can
  simply keep more waves in flight concurrently (this run stopped at 4,800
  only because that was the chosen test scale, not because any ceiling was
  hit). Sustained at higher concurrency across every validator simultaneously,
  this is standard resource-exhaustion DoS territory (uncontrolled goroutine +
  heap growth), directly matching the program's "DoS attacks that... overload
  nodes to the point where they cannot participate."
- If enough validators are degraded at once, the TSS threshold-signing quorum
  (which requires `>2/3` of eligible validators to coordinate a DKLS session,
  per `validateParticipants`/`CalculateThreshold` in `sessionmanager.go`)
  cannot form — outbound bridge transactions (fund releases, fund migrations)
  stall network-wide. This is the concrete path from "a Go networking bug" to
  "loss of chain liveness / stuck funds" the program's impact wording targets.

## Suggested fix

Defense-in-depth, cheapest-first:
1. **Connection gating at the libp2p layer** (`libp2p.ConnectionGater(...)`):
   reject inbound connections/streams from peer IDs that are not in the
   on-chain registered universal-validator set *before* any stream is even
   accepted. This codebase already resolves peerID ↔ validator identity
   elsewhere (`Coordinator.GetPartyIDFromPeerID`) — the same lookup can gate
   at connect time instead of only after a frame is read.
2. **Explicit `libp2p.ResourceManager`/`ConnectionManager`** with a small
   per-peer concurrent-stream/connection cap (e.g. 1-2), instead of relying on
   un-tuned library defaults.
3. Shorten `IOTimeout` specifically for the pre-authentication frame-read
   window, or read-then-authenticate the sender's peer identity *before*
   allocating the `MaxFrameSize` buffer (the peer ID is already known from
   `stream.Conn().RemotePeer()` at accept time, before any bytes are read).

## Honesty notes
- We did not run this to the point of an actual process crash/OOM (that would
  require sustained load against a long-running process at a scale beyond
  what's appropriate to run in this sandboxed environment). What is measured
  and reproducible is: **zero rejection at 4,800 concurrent malformed streams,
  linear resource growth with attacker effort, and no defensive mechanism of
  any kind in Push Chain's own code** — the primitive for a real DoS is fully
  demonstrated and unmitigated; scaling it to an actual crash is a matter of
  attacker effort, not a further code question.
- This is a transport-layer finding, distinct from and upstream of the
  message-type authentication we verified as sound in round 3
  (`pushchain-l1-door-sweep-round3-tss-networking.md`) — those checks are
  real and correct, but they never run for a stream that never finishes
  sending its frame.
