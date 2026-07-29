// tssvictim is a standalone binary running the REAL, unmodified
// universalClient/tss/networking/libp2p.Network exactly as production code
// does (same New(), same Config defaults, same handleStream). It exists so we
// can run "a validator's TSS node" as its own OS process under a hard,
// realistic memory ceiling (via `ulimit -v` in the parent shell) and observe
// whether an external, unauthenticated flood can actually kill it -- not just
// grow its heap within a shared test process.
package main

import (
	"context"
	"fmt"
	"os"
	"runtime"
	"time"

	"github.com/rs/zerolog"

	libp2p "github.com/pushchain/push-chain-node/universalClient/tss/networking/libp2p"
)

func main() {
	logger := zerolog.Nop()
	// Explicit ProtocolID (matches the real default) so the separate attacker
	// process knows what to dial without reaching into unexported fields.
	cfg := libp2p.Config{IOTimeout: 15 * time.Second, ProtocolID: "/push/tss/1.0.0"}

	net, err := libp2p.New(context.Background(), cfg, logger)
	if err != nil {
		fmt.Fprintf(os.Stderr, "FATAL: failed to create network: %v\n", err)
		os.Exit(1)
	}

	if err := net.RegisterHandler(func(peerID string, data []byte) {}); err != nil {
		fmt.Fprintf(os.Stderr, "FATAL: failed to register handler: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("PEERID %s\n", net.ID())
	fmt.Printf("PROTOCOL %s\n", cfg.ProtocolID)
	for _, a := range net.ListenAddrs() {
		fmt.Printf("ADDR %s\n", a)
	}
	fmt.Println("READY")

	// Periodically report our own resource usage to stdout so the harness can
	// see exactly how far we got before dying.
	go func() {
		ticker := time.NewTicker(500 * time.Millisecond)
		defer ticker.Stop()
		for range ticker.C {
			var m runtime.MemStats
			runtime.ReadMemStats(&m)
			fmt.Printf("STATS goroutines=%d heap=%d bytes (%.1f MiB) sys=%d bytes (%.1f MiB)\n",
				runtime.NumGoroutine(), m.HeapAlloc, float64(m.HeapAlloc)/(1024*1024),
				m.Sys, float64(m.Sys)/(1024*1024))
		}
	}()

	select {}
}
