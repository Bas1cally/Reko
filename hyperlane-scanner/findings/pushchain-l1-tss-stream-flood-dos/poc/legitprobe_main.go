// legitprobe simulates an honest validator peer: repeatedly Connect + open a
// TSS stream + send a COMPLETE valid frame, and reports how long that takes and
// whether it succeeds. Run it while a flood saturates the victim's CPU to see if
// legitimate TSS stream setup is starved (=> quorum DoS, RAM-independent).
package main

import (
	"context"
	"encoding/binary"
	"fmt"
	"os"
	"strconv"
	"time"

	libp2p "github.com/libp2p/go-libp2p"
	"github.com/libp2p/go-libp2p/core/peer"
	"github.com/libp2p/go-libp2p/core/protocol"
	"github.com/multiformats/go-multiaddr"
)

func main() {
	if len(os.Args) < 5 {
		fmt.Fprintln(os.Stderr, "usage: legitprobe <peerID> <protocolID> <iterations> <addr>")
		os.Exit(1)
	}
	vID, _ := peer.Decode(os.Args[1])
	pid := protocol.ID(os.Args[2])
	iters, _ := strconv.Atoi(os.Args[3])
	addr, _ := multiaddr.NewMultiaddr(os.Args[4])
	vInfo := peer.AddrInfo{ID: vID, Addrs: []multiaddr.Multiaddr{addr}}

	frame := make([]byte, 8)
	binary.BigEndian.PutUint32(frame[0:4], 4)
	copy(frame[4:], []byte{9, 9, 9, 9})

	var okCount, failCount int
	var totLatency time.Duration
	for i := 0; i < iters; i++ {
		start := time.Now()
		ok := func() bool {
			// fresh host each iteration = honest peer establishing a connection
			h, err := libp2p.New(libp2p.ListenAddrStrings("/ip4/127.0.0.1/tcp/0"))
			if err != nil {
				return false
			}
			defer h.Close()
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			if err := h.Connect(ctx, vInfo); err != nil {
				return false
			}
			s, err := h.NewStream(ctx, vID, pid)
			if err != nil {
				return false
			}
			if _, err := s.Write(frame); err != nil {
				return false
			}
			_ = s.CloseWrite()
			return true
		}()
		lat := time.Since(start)
		if ok {
			okCount++
			totLatency += lat
			fmt.Printf("probe %2d: OK   in %v\n", i+1, lat.Round(time.Millisecond))
		} else {
			failCount++
			fmt.Printf("probe %2d: FAIL (timeout/refused) after %v\n", i+1, lat.Round(time.Millisecond))
		}
		time.Sleep(700 * time.Millisecond)
	}
	avg := time.Duration(0)
	if okCount > 0 {
		avg = totLatency / time.Duration(okCount)
	}
	fmt.Printf("SUMMARY ok=%d fail=%d avgLatency(ok)=%v\n", okCount, failCount, avg.Round(time.Millisecond))
}
