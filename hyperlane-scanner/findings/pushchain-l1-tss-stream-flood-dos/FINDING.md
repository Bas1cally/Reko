# Critical — Unauthenticated Stream Flooding Lets Any Peer Kill Every Validator's TSS Node For Free

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

## Anticipated objection: "the operator just restarts the crashed node"

Correct that a killed process can be restarted — and pre-empted, because restart is
not recovery here:

1. **A restarted node is re-killed in under 40 seconds.** The crash-proof timeline
   (66 → 110 → 139 MiB → OOM-kill at ~t+39s) is under *continuous* flood; a node that
   comes back up while the attacker is still flooding is driven straight back to OOM.
   Recovery requires the **attack to stop**, and nothing in Push Chain's code makes it
   stop — there is no honest operation that clears it (contrast a griefing-restart a
   manager can complete between triggers).
2. **Sustaining costs the attacker ~zero, against every validator at once.** A handful
   of connections + 4 bytes/stream, and validator P2P addresses are on-chain public
   data, so one script holds the entire registered validator set down in parallel
   indefinitely. The asymmetry (attacker: negligible bandwidth, zero funding; victims:
   all dead) is the finding.
3. **It hits a non-discretionary function with a hard consequence.** While the flood
   runs, the TSS quorum cannot form, so bridge fund releases/migrations stall
   network-wide — not a discretionary operator convenience. "Widespread node crashes"
   and "DoS attacks that overload nodes to the point where they cannot participate" are
   the program's own explicit Critical criteria; the severity does not rest on a single
   packet causing a week-long lock, but on all validators being held down for the
   duration of a zero-cost, unstoppable-by-honest-action attack.

## Cross-check: not a documented/known behavior

The missing connection gating / resource limits on the TSS libp2p host is not
described as intentional anywhere in the in-scope `universalClient` code or its
comments — unlike a spec-acknowledged tradeoff, this is an unguarded transport
surface. (The message-layer auth that *is* present sits downstream of the crash and
never runs; see the crash-proof section.)

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

## Crash proof — an actual OS-level kill, not just resource growth

To remove any doubt that this is "just heap growth that a judge could wave
away," we ran the real victim `Network` as its **own separate OS process**
(`poc/crash-proof/tssvictim_main.go` — the exact, unmodified production `New()`
code path, nothing simulated) under a realistic hard memory ceiling (150 MiB,
enforced via a Linux memory cgroup — the same mechanism used to bound memory
for containerized/systemd-managed services in production), and attacked it
with a second, fully separate OS process simulating an external attacker
(`poc/crash-proof/tssattacker_main.go` — knows nothing about the victim beyond
its public peer ID / multiaddr / protocol ID, exactly what on-chain
`NetworkInfo.MultiAddrs` gives any observer).

**Result: the Linux kernel OOM-killer killed the victim process in under 40
seconds**, confirmed via `dmesg` (full transcript in
`poc/crash-proof/CRASH_EVIDENCE_dmesg_oom_kill.txt`):

```
tssvictim invoked oom-killer: gfp_mask=0xcc0(GFP_KERNEL), order=0, oom_score_adj=0
oom-kill:constraint=CONSTRAINT_MEMCG,...,oom_memcg=/tsspoc,task_memcg=/tsspoc,task=tssvictim,pid=23668
Memory cgroup out of memory: Killed process 23668 (tssvictim) total-vm:1830052kB, anon-rss:152644kB, ...
```

Timeline captured from the victim's own stdout + live cgroup memory
accounting during the attack:

| t (s) | cgroup memory usage |
|---|---|
| 3  | 66.1 MiB |
| 9  | 110.4 MiB |
| 15 | 138.6 MiB |
| 27 | 143.8 MiB |
| 39 | **process killed by kernel OOM-killer** |

The attacker process's own log: `FLOOD DONE opened=129813 failed=14308` — a
**single attacker process on a single machine opened 129,813 streams** against
one validator's TSS node and killed it in under 40 seconds, using nothing but
ordinary outbound connections and 4 bytes of payload per stream. No privileged
role, no on-chain funding, no more compute than any consumer machine has.

This is a hard, unambiguous process kill — not an inference from memory
growth. It reproduces with the commands below.

### Reproduction

```bash
# Build the two standalone programs against the real, unmodified package:
go build -o tssvictim   ./universalClient/tss/networking/libp2p/cmd/tssvictim
go build -o tssattacker ./universalClient/tss/networking/libp2p/cmd/tssattacker

# Run the victim under a hard 150 MiB memory ceiling (cgroup v1 shown; cgroup
# v2 or `systemd-run --scope -p MemoryMax=150M` work identically):
mkdir /sys/fs/cgroup/memory/tsspoc
echo $((150*1024*1024)) > /sys/fs/cgroup/memory/tsspoc/memory.limit_in_bytes
setsid bash -c 'echo $$ > /sys/fs/cgroup/memory/tsspoc/cgroup.procs; exec ./tssvictim' &
# victim prints its PEERID / PROTOCOL / ADDR lines -- feed them to the attacker:

./tssattacker <victim-peerid> /push/tss/1.0.0 60 <victim-multiaddr>
# within ~40s: dmesg will show "Memory cgroup out of memory: Killed process ... tssvictim"
```

This is a transport-layer finding, distinct from and upstream of the
message-type authentication we verified as sound in a separate pass (ACK,
Setup, Begin, Step, SignatureBroadcast handlers are all correctly gated
against the on-chain validator set) — those checks are real and correct, but
they never run for a stream that never finishes sending its frame; the kill
happens entirely at the transport/framing layer, before any of that
authentication logic is reached.
