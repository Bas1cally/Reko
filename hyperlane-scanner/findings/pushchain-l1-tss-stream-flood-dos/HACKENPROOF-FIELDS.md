# HackenProof submission — copy/paste per field

---

## TITLE

```text
Unauthenticated, unbounded libp2p stream flooding lets any internet peer exhaust every validator's TSS node with zero funding and no privileged role
```

---

## TARGET

`https://github.com/pushchain/push-chain-node/tree/0648551281dada6e300f51baca0e7464cb210eef/universalClient`

---

## CATEGORY / IMPACT

L1 — Denial of Service / network disruption: "DoS attacks that overload nodes
to the point where they cannot participate" + "widespread node crashes".
Likelihood: no privileged role, no funding, no extended attacker compute
(a handful of TCP connections + 4 bytes each per stream).

---

## VULNERABILITY DETAILS

**Scope:** `universalClient/` (explicitly listed in-scope asset — "Universal
Client"), specifically `universalClient/tss/networking/libp2p/network.go`.

**Root cause.** The TSS coordination network's libp2p host is created with no
resource/connection limits configured:

```go
host, err := libp2p.New(
    libp2p.Identity(priv),
    libp2p.ListenAddrStrings(cfg.ListenAddrs...),
)
...
host.SetStreamHandler(n.protocolID, n.handleStream)
```

`handleStream` accepts a stream from **any peer** that can dial the host and
knows the protocol ID (default `/push/tss/1.0.0`), with no authentication
before reading the frame:

```go
func (n *Network) handleStream(stream network.Stream) {
	defer stream.Close()
	_ = stream.SetReadDeadline(time.Now().Add(n.cfg.IOTimeout)) // default 15s
	data, err := readFramed(stream)
	if err != nil { ... ; return }
	go n.handler(stream.Conn().RemotePeer().String(), data)
}

func readFramed(r io.Reader) ([]byte, error) {
	br := bufio.NewReader(io.LimitReader(r, int64(MaxFrameSize)+4))
	var length uint32
	binary.Read(br, binary.BigEndian, &length)
	if length > MaxFrameSize { return nil, ... }  // MaxFrameSize = 1 MiB
	buf := make([]byte, length)      // up to 1 MiB allocated per stream
	_, err = io.ReadFull(br, buf)    // blocks up to IOTimeout if body never arrives
	...
}
```

All the message-level authentication in this codebase (ACK/Setup/Begin/Step/
SignatureBroadcast handlers, all correctly validated against the on-chain
validator set — verified in a separate pass) sits **downstream** of this
point and never runs if the frame body never completes. An attacker holds
`handleStream` blocked for up to `IOTimeout` per opened stream, each costing
them only a connection + 4 bytes, with no cap anywhere in Push Chain's own
code on how many concurrent streams a single peer (or many) may hold open.

Validator P2P addresses are on-chain public data (`NetworkInfo.MultiAddrs`,
read by this same codebase's `Coordinator.GetMultiAddrsFromPeerID`) — an
attacker can enumerate every registered universal validator and flood all of
them simultaneously with the identical script.

**Why Critical, not just node-level noise:** if enough validators are
resource-degraded at once, the TSS threshold-signing quorum (requires `>2/3`
of eligible validators to coordinate a DKLS session per
`sessionmanager.go:validateParticipants`/`CalculateThreshold`) cannot form —
outbound bridge transactions (fund releases, TSS fund migrations) stall
network-wide. This is the concrete path from a transport-layer Go bug to loss
of chain liveness / stuck funds.

---

## VALIDATION STEPS (runnable PoC)

Place `flood_poc_test.go` at
`universalClient/tss/networking/libp2p/flood_poc_test.go` in the
`push-chain-node` checkout (@ `0648551`) and run:

```bash
go test ./universalClient/tss/networking/libp2p/ \
  -run TestPoC_UnauthenticatedStreamFlood_Escalation -v -count=1
```

The test creates a victim `Network` via the real, unmodified `New()` (same
code as production) and a separate attacker libp2p host (representing any
outside peer; its own resource manager is disabled via
`libp2p.ResourceManager(&network.NullResourceManager{})` since a real
attacker controls their own process). The attacker opens 6 overlapping waves
of 800 concurrent streams (4,800 total): connect, write a valid `MaxFrameSize`
length prefix, send nothing further, hold the stream open.

Observed output:

```text
BASELINE: goroutines=51 heap=1403896 bytes (1.34 MiB)
PEAK goroutines=4923 (baseline 51, delta +4872)
PEAK heap=96019080 bytes (91.6 MiB) (baseline 1.34 MiB, delta +90.2 MiB)
AFTER drain: goroutines=51 heap=4817704 bytes (4.59 MiB)
ESCALATION RESULT: attempted=4800 opened=4800
```

**100% of the 4,800 attacker-opened streams were accepted — zero rejections
from the victim of any kind.** Resource usage grew in lock-step with attacker
effort across all 6 waves with no plateau or backpressure, and fully drained
only after `IOTimeout` elapsed. `RESULT_throttled_attacker_baseline.txt`
(included) shows the same test *before* disabling the attacker's own
resource manager — there, only 143/4,800 succeeded, and every failure was
`"transient: cannot reserve outbound stream"`, which is libp2p's rejection on
the attacker's own dialing side, not any defense by the victim — included to
show clearly that the victim never rejects a stream in either configuration.

---

## SUGGESTED FIX

1. **Connection gating** (`libp2p.ConnectionGater(...)`): reject inbound
   connections/streams from peer IDs not in the on-chain registered
   universal-validator set before a stream is even accepted. The codebase
   already resolves peerID ↔ validator identity elsewhere
   (`Coordinator.GetPartyIDFromPeerID`) — reuse it at connect time.
2. **Explicit `libp2p.ResourceManager`/`ConnectionManager`** with a small
   per-peer concurrent-stream/connection cap (e.g. 1-2), instead of relying on
   un-tuned library defaults.
3. Authenticate the sender's peer identity (already known from
   `stream.Conn().RemotePeer()` at accept time) before allocating the
   `MaxFrameSize` buffer / before starting the frame read.

---

## SUPPORTING FILES

- `flood_poc_test.go` — the runnable PoC (place under
  `universalClient/tss/networking/libp2p/` in the `push-chain-node` checkout).
- `RESULT_unthrottled.txt` — captured output: attacker's own throttling
  disabled, 4,800/4,800 streams accepted by the victim.
- `RESULT_throttled_attacker_baseline.txt` — captured output with the
  attacker's default (self-)throttling still enabled, included to show the
  earlier 143/4,800 figure was the attacker's own resource manager, not a
  victim-side defense.
